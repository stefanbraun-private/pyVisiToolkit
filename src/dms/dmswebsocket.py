#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017 Stefan Braun


current state august 8th 2017:
=>test with WebSocket library https://github.com/websocket-client/websocket-client
(without using complicated huge frameworks)
==>this works well! :-)
currently only cleartext WebSocket (URL "ws" instead of "wss"/SSL) is implemented


Based on this documentation:
https://github.com/stefanbraun-private/stefanbraun-private.github.io/tree/master/ProMoS_dev_docs



This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

DEBUGGING = True


import json
import time
import uuid
import websocket
import thread
import collections
import dateutil.parser, datetime


TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')


# according "ProMoS DMS JSON Data Exchange":
DMS_PORT = 9020             # cleartext HTTP or WebSocket
DMS_HOST = "127.0.0.1"      # local connection: doesn't need authentification
DMS_BASEPATH = "/json_data" # default for HTTP and WebSocket







class _DMSFrame(object):
	def __init__(self):
		pass


class _DMSRequest(_DMSFrame):
	def __init__(self, whois, user):
		self.whois = u'' + whois
		self.user = u'' + user
		self.tag = None # we don't tag the whole request, since we tag all single commands inside request
		# dict of lists, containing all pending commands
		self._cmd_dict = {}
		self._cmd_tags_list = []
		_DMSFrame.__init__(self)

	def addCmd(self, *args):
		for cmd in args:
			curr_type = cmd.get_type()
			if not curr_type in self._cmd_dict:
				self._cmd_dict[curr_type] = []
			# include this command into request and update list with message tags
			self._cmd_dict[curr_type].append(cmd)
			self._cmd_tags_list.append(cmd.tag)
		return self

	def as_dict(self):
		# building complete request
		# (all request commands contain a list of commands,
		# usually we send only one command per request)
		curr_dict = {}
		curr_dict[u'whois'] = self.whois
		curr_dict[u'user'] = self.user
		for cmdtype in self._cmd_dict:
			curr_list = []
			for cmd in self._cmd_dict[cmdtype]:
				curr_list.append(cmd.as_dict())
			if curr_list:
				curr_dict[cmdtype] = curr_list
		return curr_dict

	def get_tags(self):
		""" returns all messagetags from included commands """
		return self._cmd_tags_list



class _DMSCmdGet(object):
	""" one unique "get" request, parsed from **kwargs """

	CMD_TYPE = u'get'

	def __init__(self, msghandler, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.query = {}
		self.histData = {}
		self.showExtInfos = None
		self.tag = msghandler.generate_tag()

		for key in kwargs:
			# parsing "query" object
			val = None
			if key == u'regExPath':
				val = u'' + kwargs[key]
			elif key == u'regExValue':
				val = u'' + kwargs[key]
			elif key == u'regExStamp':
				val = u'' + kwargs[key]
			elif key == u'isType':
				val = u'' + kwargs[key]
			elif key == u'hasHistData':
				val = bool(kwargs[key])
			elif key == u'hasAlarmData':
				val = bool(kwargs[key])
			elif key == u'hasProtocolData':
				val = bool(kwargs[key])
			elif key == u'maxDepth':
				val = int(kwargs[key])

			if val:
				self.query[key] = val

			# parsing "histData" object
			val = None
			if key == u'start':
				val = u'' + kwargs[key]
			if key == u'end':
				val = u'' + kwargs[key]
			if key == u'interval':
				val = int(kwargs[key])
			if key == u'format':
				val = u'' + kwargs[key]

			if val:
				self.histData[key] = val

			# parsing properties
			if key == u'showExtInfos':
				self.showExtInfos = bool(kwargs[key])

		# checking mandatory fields
		#assert self.path != u'', u'"path" property is mandatory!'  # is null-path allowed?!?
		assert self.histData == {} or u'start' in self.histData, u'field "start" is mandatory when object "histData" is used!'


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.showExtInfos:
			curr_dict[u'showExtInfos'] = self.showExtInfos
		if self.query:
			curr_dict[u'query'] = self.query
		if self.histData:
			curr_dict[u'histData'] = self.histData
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdGet.CMD_TYPE




class _DMSExtInfos(object):
	""" optional extended infos about datapoint """
	def __init__(self, **kwargs):
		keys_tuple = (u'template', u'name', u'accType', u'unit', u'comment')
		for key in keys_tuple:
			if key in kwargs:
				# adding instance attribut and removing keyword
				val = kwargs.pop(key)
				self.__dict__[key] = u'' + val
		if kwargs:
			print('Warning: parsing "extInfos" revealed these unknown fields: ' + repr(kwargs))



# FIXME: how to implement initialisation?
class _DMSHistData_compact(object):
	""" optional history data in compact format """
	def __init__(self, **kwargs):
		pass

# FIXME: how to implement initialisation?
class _DMSHistData_detail(_DMSHistData_compact):
	""" optional history data in detail format """
	def __init__(self, **kwargs):
		super(_DMSHistData_detail, self).__init(**kwargs)


class DMSCmdResponse(object):
	""" all common response fields """

	# inherit from abstract class "Mapping" for getting dictionary-interface
	# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
	# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
	# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )

	# string constants
	CODE_OK = u'ok'
	CODE_NOPERM = u'no perm'
	CODE_NOTFOUND = u'not found'
	CODE_ERROR = u'error'

	# these fields are common for all responses
	_fields = (u'code', )

	def __init__(self, **kwargs):
		# this variable has to be declared in child class...
		for field in DMSCmdResponse._fields:
			try:
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# something went wrong, a mandatory field is missing... =>set error code
				print('constructor of DMSCmdResponse(): ERROR: mandatory field "' + field + '" is missing in current response!')
				self._values_dict[u'code'] = DMSCmdResponse.CODE_ERROR


class DMSCmdGetResponse(DMSCmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'hasChild',
	           u'stamp',
	           u'extInfos',
	           u'message',
	           u'histData',
	           u'tag')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in DMSCmdResponse._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						dateutil.parser.parse(kwargs[field])
					except ValueError:
						self._values_dict[field] = None
				elif field == u'extInfos':
					self._values_dict[field] = _DMSExtInfos(kwargs[field])
				elif field == u'histData':
					# FIXME: should we store ONE histData object containing all trenddata, or a LIST of histData objects?
					# FIXME: implement histData class
					self._values_dict[field] = kwargs[field]
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				self._values_dict[field] = None

		# init all common fields
		super(DMSCmdGetResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)


	def __repr__(self):
		""" developer representation of this object """
		return repr(self._values_dict)


class _MessageHandler(object):
	def __init__(self, dmsclient_obj, whois_str, user_str):
		# backreference for sending messages
		self._dmsclient = dmsclient_obj
		self._whois_str = whois_str
		self._user_str = user_str

		# dict for pending responses (key: cmd-tag, value: list of DMSCmdResponse-objects)
		# =>None means request is sent, but answer is not yet here
		self._pending_response_dict = {}

		# object for assembling response lists
		# (when one "get" command produces more than one response)
		class Current_response(object):
			def __init__(self):
				self.msg_tag = u''
				self.resp_list = []
			def clear(self):
				self.__init__()
		self._curr_response = Current_response()



	def dp_get(self, path, **kwargs):
		""" read datapoint value(s) """

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(_DMSCmdGet(msghandler=self, path=path, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_get(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')

	def dp_set(self):
		""" write datapoint value(s) """
		pass

	def dp_del(self):
		""" delete datapoint(s) """
		pass

	def dp_ren(self):
		""" rename datapoint(s) """
		pass

	def dp_sub(self):
		""" subscribe monitoring of datapoints(s) """
		pass

	def dp_unsub(self):
		""" unsubscribe monitoring of datapoint(s) """
		pass

	def handle(self, msg):
		payload_dict = json.loads(msg.decode('utf8'))

		try:
			# message handler
			if u'get' in payload_dict:
				# handling responses to "get"
				for get_response in payload_dict[u'get']:
					if u'tag' in get_response:
						curr_tag = get_response[u'tag']
						if len(payload_dict[u'get']) == 1:
							# only one response to this request =>bypass listcreation of responses
							# =>save response object
							if curr_tag in self._pending_response_dict:
								if DEBUGGING:
									print('\tidentified one response to our request.')
								resp_obj = DMSCmdGetResponse(**get_response)
								self._pending_response_dict[curr_tag] = [resp_obj]
							else:
								if DEBUGGING:
									print('\tignoring unexpected response...')
							# reset response list
							self._curr_response.clear()
						else:
							# processing array of responses
							if curr_tag == self._curr_response.msg_tag:
								# appending to current list
								self._curr_response.resp_list.append(DMSCmdGetResponse(**get_response))
							else:
								if self._curr_response.msg_tag and self._curr_response.resp_list:
									# need to save last responses
									if curr_tag in self._pending_response_dict:
										if DEBUGGING:
											print('\tidentified multiple responses to our request.')
										print('FOO')
										self._pending_response_dict[curr_tag] = self._curr_response.resp_list
									else:
										if DEBUGGING:
											print('\tignoring unexpected response...')
								# begin of new response list
								self._curr_response.msg_tag = curr_tag
								self._curr_response.resp_list = [DMSCmdGetResponse(**get_response)]
					else:
						if DEBUGGING:
							print('\tignoring untagged response...')
		except Exception as ex:
			print("exception in _MessageHandler.handle(): " + repr(ex))

	def _send_frame(self, frame_obj):
		# send whole request

		# create valid JSON
		# (according to https://docs.python.org/2/library/json.html : default encoding is UTF8)
		req_str = json.dumps(frame_obj.as_dict())
		self._dmsclient._send_message(req_str)

	def _busy_wait_for_response(self, tag):
		# FIXME: can we implement this in a better way?
		found = False
		while not found:
			time.sleep(0.001)
			if self._pending_response_dict[tag]:
				found = True
		return self._pending_response_dict.pop(tag)


	def generate_tag(self):
		# generating random and nearly unique message tags
		# (see https://docs.python.org/2/library/uuid.html )
		curr_tag = str(uuid.uuid4())

		self._pending_response_dict[curr_tag] = None
		return curr_tag


class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int
		self._msghandler = _MessageHandler(dmsclient_obj=self, whois_str=whois_str, user_str=user_str)
		self.ready_to_send = False

		# based on example on https://github.com/websocket-client/websocket-client
		#websocket.enableTrace(True)
		ws_URI = u"ws://" + self._dms_host_str + u':' + str(self._dms_port_int) + DMS_BASEPATH
		self._ws = websocket.WebSocketApp(ws_URI,
		                            on_message = self._cb_on_message,
		                            on_error = self._cb_on_error,
		                            on_open = self._cb_on_open,
		                            on_close = self._cb_on_close)
		# executing WebSocket eventloop in background
		self._ws_thread = thread.start_new_thread(self._ws.run_forever, ())
		# FIXME: how to return caller a non-reachable WebSocket server?
		if DEBUGGING:
			print("WebSocket connection will be established in background...")

	# API
	def dp_get(self, path, **kwargs):
		""" read datapoint value(s) """

		self._busy_wait_until_ready()
		return self._msghandler.dp_get(path, **kwargs)

	def dp_set(self, path, **kwargs):
		""" write datapoint value(s) """
		return self._msghandler.dp_set(path, **kwargs)

	def dp_del(self, path, **kwargs):
		""" delete datapoint(s) """
		return self._msghandler.dp_del(path, **kwargs)

	def dp_ren(self, oldpath, newpath, **kwargs):
		""" rename datapoint(s) """
		return self._msghandler.dp_ren(oldpath, newpath, **kwargs)

	def dp_sub(self, path, **kwargs):
		""" subscribe monitoring of datapoints(s) """
		return self._msghandler.dp_sub(path, **kwargs)

	def dp_unsub(self, path, **kwargs):
		""" unsubscribe monitoring of datapoint(s) """
		return self._msghandler.dp_unsub(path, **kwargs)

	def _busy_wait_until_ready(self):
		# FIXME: is there a better way to do this?
		while not self.ready_to_send:
			time.sleep(0.001)


	def _send_message(self, msg):
		if self.ready_to_send:
			self._ws.send(msg)
		# FIXME: how should we inform user about WebSocket problems?
		# e.g. giving back IOError exception?
		# or raw websocket-exceptions https://github.com/websocket-client/websocket-client/blob/master/websocket/_exceptions.py


	def _cb_on_message(self, ws, message):
		if DEBUGGING:
			print("_on_message(): " + message)
		self._msghandler.handle(message)

	def _cb_on_error(self, ws, error):
		if DEBUGGING:
			print("_on_error(): " + error)

	def _cb_on_open(self, ws):
		if DEBUGGING:
			print("_on_open(): WebSocket connection is established.")
		self.ready_to_send = True

	def _cb_on_close(self, ws):
		if DEBUGGING:
			print("_on_close(): server closed connection =>shutting down client thread")
		self.ready_to_send = False
		self._ws_thread.exit()

	def __del__(self):
		"""" closing websocket connection on object destruction """
		self._ws.close()
		time.sleep(1)
		self._ws_thread.exit()



if __name__ == '__main__':

	myClient = DMSClient(u'test', u'user') #,  dms_host_str='192.168.10.173')
	print('\n=>WebSocket connection runs now in background...')

	# while True:
	# 	time.sleep(1)
	# 	print('sending TESTMSG...')
	# 	myClient._send_message(TESTMSG)

	test_set = set([1])

	if 1 in test_set:
		print('\nTesting creation of Request command:')
		print('"get":')
		for x in range(3):
			response = myClient.dp_get(path="System:Time")
			print('response to our request: ' + repr(response))
			print('*' * 20)

	if 2 in test_set:
		print('\n\nNow doing loadtest:')
		DEBUGGING = False
		nof_tests = 10000
		for x in xrange(nof_tests):
			response = myClient.dp_get(path="System:Time")
		print('We have done ' + str(nof_tests) + ' requests. :-) Does it still work?')
		DEBUGGING = True
		print('*' * 20)
		response = myClient.dp_get(path="System:Time")
		print('response to our request: ' + repr(response))
		print('*' * 20)

	if 3 in test_set:
		print('\nNow testing query function:')
		print('\twithout query: ' + repr(myClient.dp_get(path="")))
		print('\twith query: ' + repr(myClient.dp_get(path="", regExPath=".*", maxDepth=1)))
	print('\n=>quitting...')
