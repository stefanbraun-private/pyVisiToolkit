#!/usr/bin/env python
# encoding: utf-8
"""
tools.DMS_Controlfunction.py      v0.0.1
Using Python as external Controlfunction (Leitfunktion)
 -monitors a set of datapoints
 -doing calculations with Python's eval() when one value changed
 -write result to another datapoint

Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

## bug-hunting when every DMS event started a new thread while old threads didn't die...
## (it seems bug is in Axel Events or the way how I use it's event handling in dmswebsocket.py)
#DEBUGGING_LEAK = True


import dms.dmswebsocket as dms
import argparse
import logging
import yaml
import time
import threading
import collections

# modules for usage in given expressions
import math
import random
import string

# ### DEBUGGING memory leak
# # help from https://stackoverflow.com/questions/1641231/python-working-around-memory-leaks/1641280#1641280
# # and https://stackoverflow.com/questions/1396668/get-object-by-id
# import gc


# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('tools.DMS_Controlfunction')
logger.setLevel(logging.INFO)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)

# mapping between DMS datatypes used via JSON Data Exchange and Python builtin datatypes
TYPE_MAPPING = {u'int': int,
	            u'double': float,
	            u'string': unicode,
	            u'bool': bool}

# function result caching
CACHING_MAX_NOF_ELEMS = 1000


class DMSDatapoint(object):
	def __init__(self, dms_ws, key_str):
		self._dms_ws = dms_ws
		self.key_str = str(key_str)
		self._value = None
		self._datatype = None


	def is_available(self):
		response = self._dms_ws.dp_get(path=self.key_str)[0]
		self._value = response.value
		self._datatype = response.type
		return self._datatype in TYPE_MAPPING

	def get_value(self):
		return self._value


class DMSDatapoint_Result(DMSDatapoint):
	def __init__(self, dms_ws, key_str):
		super(DMSDatapoint_Result, self).__init__(dms_ws, key_str)
		self._cached_val = None

	def write_to_dms(self, newval):
		# synchronize to DMS
		if self.is_available():
			if self._cached_val and self._cached_val != self._value:
				logger.warn('DMSDatapoint_Result.write_to_dms(): unexpected value change of DMS key "' + self.key_str + '" [cached:' + repr(self._cached_val) + ' | current:'  + repr(self._value) + '] ... others are writing to this key!')
			if newval != self._value:
				logger.debug('DMSDatapoint_Result.write_to_dms(): updating DMS key "' + self.key_str + '" with value ' + repr(newval) + ' converted to ' + self._datatype)
				try:
					# send correct datatype to DMS (prevents errors with wrong datatype of DMS-key or incorrect Python expression)
					python_cls = TYPE_MAPPING[self._datatype]
					self._value = python_cls(newval)
				except Exception as ex:
					logger.error('DMSDatapoint_Result.write_to_dms(): type mismatch, got exception "' + repr(ex) + '" while convert new result ' + repr(newval) + ' to ' + self._datatype + '!')
					# leave function (help from https://stackoverflow.com/questions/6190776/what-is-the-best-way-to-exit-a-function-which-has-no-return-value-in-python-be )
					raise ex
				resp = self._dms_ws.dp_set(path=self.key_str,
				                           value=self._value,
				                           create=False)
				if resp[0].code == 'ok':
					self._cached_val = resp[0].value
				else:
					logger.error('DMSDatapoint_Result.write_to_dms(): DMS returned error "' + resp[0].message + '" for DMS key "' + self.key_str + '"')
					raise Exception()
		else:
			logger.error('DMSDatapoint_Result.write_to_dms(): DMS key "' + self.key_str + '" must exist and must not have datatype NONE!')
			raise Exception()


class DMSDatapoint_Var(DMSDatapoint):

	# for better performance we allow only one variable per datapoint (only one subscription in DMS)
	_instances_dict = {}

	def __new__(cls, dms_ws, key_str):
		# => __new__() allows custom creation of a new instance, hints from:
		# http://spyhce.com/blog/understanding-new-and-init
		# https://infohost.nmt.edu/tcc/help/pubs/python/web/new-new-method.html
		if not key_str in DMSDatapoint_Var._instances_dict:
			# unknown datapoint =>create a new variable-instance
			DMSDatapoint_Var._instances_dict[key_str] = super(DMSDatapoint_Var, cls).__new__(cls, dms_ws, key_str)
		return DMSDatapoint_Var._instances_dict[key_str]

	def __init__(self, dms_ws, key_str):
		if not hasattr(self, '_curr_func_list'):
			self._curr_func_list = []
		self._sub_obj = None
		super(DMSDatapoint_Var, self).__init__(dms_ws, key_str)
		# monitoring of a datapoint allows us to cache it's state
		self._is_available_cached = False
		self._val_lock = threading.RLock()

	def add_function(self, curr_func):
		# backreference to function where this variable is used
		self._curr_func_list.append(curr_func)


	# callback function for DMS event
	def _cb_changed_value(self, event):
		if event.path == self.key_str:
			with self._val_lock:
				logger.debug('DMSDatapoint_Var._cb_changed_value(): callback for DMS key "' + self.key_str + '" was fired... [event.value=' + repr(event.value)+']')

				# interpretation of current datapoint state
				if event.code in (dms.DMSEvent.CODE_SET, dms.DMSEvent.CODE_CREATE):
					is_available = True
				elif event.code is dms.DMSEvent.CODE_DELETE:
					is_available = False
				else:
					logger.error('internal error: DMSDatapoint_Var._cb_changed_value(): callback for DMS key "' + self.key_str + '" contains unexpected code "' + repr(event.code) + ', check subscribe().')

				self._update_value(value=event.value,
				                   datatype=event.type,
				                   is_available=is_available)

				logger.debug('DMSDatapoint_Var._cb_changed_value(): callback for DMS key "' + self.key_str + '" is done.')
		else:
			logger.error('DMSDatapoint_Var._cb_changed_value(): subscription error: callback for DMS key "' + self.key_str + '" was fired with event.path=' + event.path + '!')
		event = None


	def _update_value(self, value, datatype, is_available=True):
		with self._val_lock:
			self._value = value
			self._datatype = datatype
			self._is_available_cached = is_available
			logger.debug('DMSDatapoint_Var._update_value(): update for "' + self.key_str + '" [value=' + repr(value) + ', datatype=' + repr(datatype) + ']')


		# inform all Controlfunctions of changed value
		# =>main thread will check this
		# (in an older version this callback directly called evaluate(),
		#  this leaded to deadlock in dmswebsocket:
		#  executing _MessageHandler._send_message() in _MessageHandler.handle() while firing SubscriptionES() is not possible...)
		for func_obj in self._curr_func_list:
			func_obj.result_dirty.set()


	def subscribe(self):
		if not self._sub_obj:
			logger.debug('DMSDatapoint_Var.subscribe(): trying to subscribe DMS key "' + self.key_str + '"...')
			self._sub_obj = self._dms_ws.get_dp_subscription(path=self.key_str,
			                                                 event=dms.ON_SET + dms.ON_CREATE + dms.ON_DELETE)
			logger.debug('DMSDatapoint_Var.subscribe(): trying to add callback for DMS key "' + self.key_str + '"...')
			msg = self._sub_obj.sub_response.message
			if not msg:
				self._sub_obj += self._cb_changed_value
				self._update_value(value=self._sub_obj.sub_response.value,
				                   datatype=self._sub_obj.sub_response.type,
				                   is_available=True)
				logger.info('DMSDatapoint_Var.subscribe(): monitoring of DMS key "' + self.key_str + '" is ready.')
			else:
				logger.error('DMSDatapoint_Var.subscribe(): monitoring of DMS key "' + self.key_str + '" failed! [message: ' + msg + '])')
				raise Exception('subscription failed!')
		else:
			logger.debug('DMSDatapoint_Var.subscribe(): DMS key "' + self.key_str + '" is already subscribed...')


	def is_available(self):
		# override of function in superclass: using cached datapoint state if possible
		with self._val_lock:
			return self._is_available_cached or super(DMSDatapoint_Var, self).is_available()


class Controlfunction(object):

	# class attribute: cache results for all functions (improving performance if possible)
	# =>we use an OrderedDict for getting a FIFO cache with a maximum number of elements
	_caching_ordereddict = collections.OrderedDict()


	def __init__(self, name_str, expr_str, result_var, do_caching, do_dryrun):
		self._var_dict = {}
		self._name = str(name_str)
		self._expr_str = str(expr_str)
		self._result_var = result_var
		self._cache_result = bool(do_caching)
		self._do_dryrun = bool(do_dryrun)
		self.result_dirty = threading.Event()

	@staticmethod
	def _get_cached_result(expr_str, locals_dict):
		""" retrieves cached result (or None when expression was evaluated with new arguments) """
		# we have to sort keyword arguments for always getting same hash value as key in our dict
		# =>only tuples can be hashed (we get a tuple of expr and tuples)
		# (help from https://stackoverflow.com/questions/10220599/how-to-hash-args-kwargs-for-function-cache )
		key_tuple = (expr_str, ) + tuple(sorted(locals_dict.items()))
		try:
			return Controlfunction._caching_ordereddict[key_tuple]
		except KeyError:
			logger.debug('Controlfunction._get_cached_result(): found no value for key "' + str(key_tuple) + '"')
			return None

	@staticmethod
	def _set_cached_result(expr_str, locals_dict, result):
		""" store expression, it's result and all function arguments  """
		key_tuple = (expr_str,) + tuple(sorted(locals_dict.items()))
		if key_tuple in Controlfunction._caching_ordereddict:
			# for insertion of new result in front we need to remove if from original position
			# https://docs.python.org/2/library/collections.html#collections.OrderedDict
			del(Controlfunction._caching_ordereddict[key_tuple])
		# insertion in front
		Controlfunction._caching_ordereddict[key_tuple] = result

		if len(Controlfunction._caching_ordereddict) > CACHING_MAX_NOF_ELEMS:
			# removing oldest result for keeping size
			logger.debug('Controlfunction._set_cached_result(): _caching_ordereddict reached maximum length, removing oldest element...')
			Controlfunction._caching_ordereddict.popitem(last=False)


	def add_variable(self, var_name, var_obj):
		self._var_dict[var_name] = var_obj

	def check_datapoints(self):
		everything_ok = True
		vars_tuple_list = self._var_dict.items()
		if not self._do_dryrun:
			# check result datapoint if needed
			vars_tuple_list.append(('result', self._result_var))
		for var_name, var_obj in vars_tuple_list:
			if var_obj.is_available():
				logger.debug('Controlfunction.check_datapoints(): [name: ' + self._name + '] variable "' + var_name + '": ok. [key: ' + var_obj.key_str + ']')
			else:
				everything_ok = False
				logger.error(
					'Controlfunction.check_datapoints(): [name: ' + self._name + '] variable "' + var_name + '": is missing or has datatype NONE! [key: ' + var_obj.key_str + ']')
		return everything_ok


	def subscribe_vars(self):
		everything_ok = True
		for var_name, var_obj in self._var_dict.items():
			try:
				var_obj.subscribe()
				logger.debug('Controlfunction.subscribe_vars(): [name: ' + self._name + '] variable "' + var_name + '": done. [key: ' + var_obj.key_str + ']')
			except Exception as ex:
				everything_ok = False
				logger.error(
					'Controlfunction.subscribe_vars(): [name: ' + self._name + '] variable "' + var_name + '": subscription failed! [key: ' + var_obj.key_str + ']' + repr(ex))
		return everything_ok


	def evaluate(self):
		# evaluate given expression with current variable values
		# set environment for eval(): building local variables dictionary
		mylocals = {}
		for var_name in self._var_dict:
			mylocals[var_name] = self._var_dict[var_name].get_value()

		result_value = None
		if self._cache_result:
			result_value = Controlfunction._get_cached_result(expr_str=self._expr_str, locals_dict=mylocals)

		if result_value == None:
			# we need to evaluate the expression
			# FIXME: currently we evaluate wrong expressions again and again...
			#  =>should we exclude it? then we should cleanup subscriptions and references variable->functions, ...
			#
			#  include allowed modules into local variables dictionary
			mylocals['math'] = math
			mylocals['random'] = random
			mylocals['string'] = string
			try:
				# calling eval() mostly safe (according to http://lybniz2.sourceforge.net/safeeval.html )
				result_value = eval(self._expr_str, {}, mylocals)
			except Exception as ex:
				# current expression contains errors...
				logger.error('Controlfunction.evaluate(): [name: ' + self._name + '] expression "' + repr(self._expr_str) + '" throwed exception ' + repr(ex) + ' with values ' + repr(mylocals))

			# prepare message for logging, removing unwanted parts
			del(mylocals['math'])
			del(mylocals['random'])
			del (mylocals['string'])

		if result_value != None:
			msg = 'Controlfunction.evaluate(): [name: ' + self._name + '] expression ' + repr(self._expr_str) + ' = ' + repr(result_value) + '   // ' + repr(mylocals)
			if self._do_dryrun:
				# only print to console
				logger.info(msg)
			else:
				logger.debug(msg)
				# synchronize to DMS
				try:
					self._result_var.write_to_dms(result_value)
				except Exception as ex:
					logger.error('Controlfunction.evaluate(): [name: ' + self._name + '] could not store result in DMS!')

			if self._cache_result:
				# store result in cache
				Controlfunction._set_cached_result(expr_str=self._expr_str, locals_dict=mylocals, result=result_value)
		# now we say we're done.
		self.result_dirty.clear()



class Runner(object):
	def __init__(self, dms_ws, configfile, only_dryrun=None):
		self._dms_ws = dms_ws
		self._configfile = configfile
		self._only_dryrun = bool(only_dryrun)
		self._functions_dict = {}


	def load_config(self):
		self._config_dict = yaml.load(self._configfile)
		logger.info('Runner.load_config(): successfully loaded configfile ' + repr(self._configfile))
		logger.debug('Runner.load_config(): content of internal config_dict: ' + repr(self._config_dict))

		# create all objects
		for func_name, func_def in self._config_dict['functions'].items():
			if func_def['activated']:
				curr_prefix = func_def['key_prefix']
				curr_result_var = DMSDatapoint_Result(dms_ws=self._dms_ws,
				                                  key_str=curr_prefix + func_def['result'])
				curr_ctrlfunc = Controlfunction(name_str=func_name,
				                                expr_str=func_def['expr'],
				                                result_var=curr_result_var,
				                                do_caching=func_def['do_caching'],
				                                do_dryrun=self._only_dryrun)
				for var_name, var_dp in func_def['vars'].items():
					curr_var = DMSDatapoint_Var(dms_ws=self._dms_ws,
					                            key_str=curr_prefix + var_dp)
					curr_var.add_function(curr_func=curr_ctrlfunc)
					curr_ctrlfunc.add_variable(var_name=var_name,
					                           var_obj=curr_var)
				self._functions_dict[func_name] = curr_ctrlfunc
				logger.info('Runner.load_config(): successfully added function "' + func_name + '"...')
			else:
				logger.info('Runner.load_config(): ignoring function "' + func_name + '"...')
		logger.debug('Runner.load_config(): reading of configfile is done.')


	def check_datapoints(self):
		logger.info('Runner.check_datapoints(): check availability of datapoints in DMS...')
		for func_name, func_obj in self._functions_dict.items():
			if func_obj.check_datapoints():
				logger.info('Runner.check_datapoints(): function "' + func_name + '" is complete.')
			else:
				logger.error('Runner.check_datapoints(): function "' + func_name + '" is incomplete!')

	def subscribe_datapoints(self):
		logger.info('Runner.subscribe_datapoints(): subscription of DMS datapoints...')
		for func_name, func_obj in self._functions_dict.items():
			if func_obj.subscribe_vars():
				logger.info('Runner.subscribe_datapoints(): function "' + func_name + '" is complete.')
			else:
				logger.error('Runner.subscribe_datapoints(): function "' + func_name + '" is incomplete!')


	def evaluate_functions(self):
		# loop once through all functions and evaluate when dirty
		# FIXME: we should implement a more efficient method...
		for func_name, func_obj in self._functions_dict.items():
			if func_obj.result_dirty.is_set():
				logger.debug('Runner.evaluate_functions(): function "' + func_name + '" needs refreshing of result')
				func_obj.evaluate()

				for t_info in threading.enumerate():
					logger.debug('Runner.evaluate_functions(): active thread: ' + repr(t_info))




def main(dms_server, dms_port, only_check, only_dryrun, configfile):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.DMS_Controlfunction',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])
		runner = Runner(dms_ws=dms_ws,
		                configfile=configfile,
		                only_dryrun=only_dryrun)
		runner.load_config()
		runner.check_datapoints()
		if not only_check:
			runner.subscribe_datapoints()

			# help from http://stackoverflow.com/questions/13180941/how-to-kill-a-while-loop-with-a-keystroke
			try:
				logger.info('"DMS_Controlfunction" is working now... Press <CTRL> + C for aborting.')

				# old_objs_set = set()
				# nof_runs = 0

				while True:
					# FIXME: we should implement a more efficient method...
					runner.evaluate_functions()
					time.sleep(0.001)

					# # DEBUGGING thread leak
					# if DEBUGGING_LEAK:
					# 	nof_runs += 1
					# 	if nof_runs == 1000:
					# 		for obj in gc.get_objects():
					# 			key = (id(obj), type(obj))
					# 			old_objs_set.add(key)
					# 	elif (nof_runs % 4000) == 0:
					# 		new_objs_set = set()
					# 		# repeating from while to while
					# 		for obj in gc.get_objects():
					# 			key = (id(obj), type(obj))
					# 			new_objs_set.add(key)
					#
					# 		# detect changes
					# 		added_objs_set = new_objs_set - old_objs_set
					# 		removed_objs_set = old_objs_set - new_objs_set
					#
					# 		types_dict = {}
					# 		if added_objs_set:
					# 			for curr_id, curr_type in added_objs_set:
					# 				try:
					# 					types_dict[curr_type] += 1
					# 				except KeyError:
					# 					types_dict[curr_type] = 1
					# 		if removed_objs_set:
					# 			for curr_id, curr_type in removed_objs_set:
					# 				try:
					# 					types_dict[curr_type] -= 1
					# 				except KeyError:
					# 					types_dict[curr_type] = -1
					# 		# help for dict comprehension: https://stackoverflow.com/questions/2844516/how-to-filter-a-dictionary-according-to-an-arbitrary-condition-function
					# 		logger.info('DEBUGGING: differences in number of objects: ' + repr({k: v for k, v in types_dict.iteritems() if v != 0}))
					#
					# 		# preparing next cycle
					# 		old_objs_set = new_objs_set


			except KeyboardInterrupt:
				pass
	logger.info('Quitting "DMS_Controlfunction"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Python as external Controlfunction (Leitfunktion).')

	# help for commandline switches: https://stackoverflow.com/questions/8259001/python-argparse-command-line-flags-without-arguments

	parser.add_argument('--check', '-c', action='store_true', dest='only_check', default=False, help='only check configurationfile and exit (default: False)')
	parser.add_argument('--dryrun', '-d', action='store_true', dest='only_dryrun', default=False, help='no write into DMS, only print result (default: False)')
	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')
	parser.add_argument('CONFIGFILE', type=argparse.FileType('r'), help='configuration file in YAML format (e.g. DMS_Controlfunction.yml)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port,
	              only_check = args.only_check,
	              only_dryrun = args.only_dryrun,
	              configfile = args.CONFIGFILE)
	#sys.exit(status)