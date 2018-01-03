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


import dms.dmswebsocket
import argparse
import logging
import yaml

# modules for usage in given expressions
from math import *
import random


# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger
logger = logging.getLogger('tools.DMS_Controlfunction')
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class DMSDatapoint(object):
	def __init__(self, dms_ws, key_str):
		self._dms_ws = dms_ws
		self.key_str = key_str
		self._value = None
		self._datatype = None


	def is_available(self):
		response = self._dms_ws.dp_get(path=self.key_str)[0]
		self._value = response[u'value']
		self._datatype = response[u'type']
		return self._datatype is not None

	def get_value(self):
		return self._value


class DMSDatapoint_Result(DMSDatapoint):
	def __init__(self, dms_ws, key_str):
		super(DMSDatapoint_Result, self).__init__(dms_ws, key_str)

	def write_to_dms(self, newval):
		# synchronize to DMS
		if newval != self._value:
			logger.debug('DMSDatapoint_Result.write_to_dms(): updating DMS key "' + self.key_str + '" with value ' + repr(newval))
			# FIXME: should we check if we're sending value with correct datatype to DMS?
			self._value = newval
			resp = self._dms_ws.dp_set(path=self.key_str,
			                           value=self._value,
			                           create=False)
			if resp[0][u'message']:
				logger.error('DMSDatapoint_Result.write_to_dms(): DMS returned error "' + resp[0][u'message'] + '" for DMS key "' + self.key_str + '"')


class DMSDatapoint_Var(DMSDatapoint):

	# for better performance we allow only one variable per datapoint (only one subscription in DMS)
	_instances_dict = {}

	def __new__(cls, dms_ws, curr_func, key_str):
		# => __new__() allows custom creation of a new instance, hints from:
		# http://spyhce.com/blog/understanding-new-and-init
		# https://infohost.nmt.edu/tcc/help/pubs/python/web/new-new-method.html
		if not key_str in DMSDatapoint_Var._instances_dict:
			# unknown datapoint =>create a new variable-instance
			DMSDatapoint_Var._instances_dict[key_str] = super(DMSDatapoint_Var, cls).__new__(cls, dms_ws, key_str)
		return DMSDatapoint_Var._instances_dict[key_str]

	def __init__(self, dms_ws, curr_func, key_str):
		self._curr_func = curr_func
		super(DMSDatapoint_Var, self).__init__(dms_ws, key_str)

	# callback function for DMS event
	def _cb_set_value(self, event):
		logger.debug('DMSDatapoint_Var._cb_set_value(): callback for DMS key "' + self.key_str + '" was fired...')
		self._value = event[u'value']
		# inform Controlfunction of changed value
		self._curr_func.evaluate()


	def subscribe(self):
		if self.is_available():
			logger.debug('DMSDatapoint_Var.subscribe(): trying to subscribe DMS key "' + self.key_str + '"...')
			self._sub_obj = self._dms_ws.get_dp_subscription(path=self.key_str,
			                                                 event=dms.dmswebsocket.ON_CHANGE)
			logger.debug('DMSDatapoint_Var.subscribe(): trying to add callback for DMS key "' + self.key_str + '"...')
			self._sub_obj += self._cb_set_value
			logger.info('DMSDatapoint_Var.subscribe(): monitoring of DMS key "' + self.key_str + '" is ready.')


class Controlfunction(object):
	def __init__(self, expr_str, result_var, do_dryrun):
		self._var_dict = {}
		self._expr_str = expr_str
		self._result_var = result_var
		self._do_dryrun = do_dryrun

	def add_variable(self, var_name, var_obj):
		self._var_dict[var_name] = var_obj

	def subscribe_vars(self):
		for var_obj in self._var_dict.items():
			var_obj.subscribe()

	def evaluate(self):
		# evaluate given expression with current variable values
		# set environment for eval(): building local variables dictionary
		mylocals = {}
		for var_name in self._var_dict:
			mylocals[var_name] = self._var_dict[var_name].get_value()
		# include allowed modules into local variables dictionary
		mylocals['math'] = math
		mylocals['random'] = random

		result_value = None
		try:
			# calling eval() mostly safe (according to http://lybniz2.sourceforge.net/safeeval.html )
			result_value = eval(self._expr_str, {}, mylocals)
		except Exception as ex:
			# current expression contains errors...
			logger.error('Controlfunction.evaluate(): expression ' + repr(self._expr_str) + ' throwed exception ' + repr(ex) + ' with values ' + repr(mylocals))
		if result_value:
			if self._do_dryrun:
				# only print to console
				logger.info('Controlfunction.evaluate(): expression ' + repr(self._expr_str) + ' has result ' + repr(result_value))
			else:
				# synchronize to DMS
				self._result_var.write_to_dms(result_value)



class Runner(object):
	def __init__(self, dms_ws, configfile, only_check=None, only_dryrun=None):
		self._dms_ws = dms_ws
		self._configfile = configfile
		self._only_check = only_check
		self._only_dryrun = only_dryrun
		self._functions_dict = {}


	def load_config(self):
		self._config_dict = yaml.load(self._configfile)
		logger.info('successfully loaded configfile "' + repr(self._configfile))
		logger.debug('content of internal config_dict: ' + repr(self._config_dict))

		# create all objects
		for func_name, func_def in self._config_dict['functions'].items():
			if func_def['activated']:
				curr_expr = func_def['expr']
				curr_result_var = DMSDatapoint_Result(dms_ws=self._dms_ws,
				                                  key_str=func_def['result'])
				curr_ctrlfunc = Controlfunction(expr_str=curr_expr,
				                                result_var=curr_result_var,
				                                do_dryrun=self._only_dryrun)
				for var_name, var_dp in func_def['vars'].items():
					curr_var = DMSDatapoint_Var(dms_ws=self._dms_ws,
					                            curr_func=curr_ctrlfunc,
					                            key_str=var_dp)
					curr_ctrlfunc.add_variable(var_name=var_name,
					                           var_obj=curr_var)
				self._functions_dict[func_name] = curr_ctrlfunc
				logger.info('successfully added function "' + func_name + '"...')
			else:
				logger.info('ignoring function "' + func_name + '"...')






def main(dms_server, dms_port, only_check, only_dryrun, configfile):
	dms_ws = dms.dmswebsocket.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.DMS_Controlfunction',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port)
	logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])
	runner = Runner(dms_ws=dms_ws, configfile=configfile)
	runner.load_config()



	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Python as external Controlfunction (Leitfunktion).')

	parser.add_argument('--check', '-c', dest='only_check', default=False, type=bool, help='only check configurationfile and exit (default: False)')
	parser.add_argument('--dryrun', '-d', dest='only_dryrun', default=False, type=bool, help='no write into DMS, only print result (default: False)')
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