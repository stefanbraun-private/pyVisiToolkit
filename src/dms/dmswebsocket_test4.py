#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017 Stefan Braun


current state august 6th 2017:
=>test with WebSocket library https://ws4py.readthedocs.io/en/latest/ using it's internal threaded loop
(without using complicated huge frameworks)
==>result: with Wireshark I see DMS systemtime every second, but it seems than "received_message()"-callback gets never fired...


This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""




import json
import time
import uuid
from ws4py.client.threadedclient import WebSocketClient
import thread
import sys


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
		self.tag = None
		# dict of lists, containing all pending commands
		self._cmd_dict = {}
		self._cmd_deferred_list = []
		_DMSFrame.__init__(self)

	def addCmd(self, *args):
		for cmd in args:
			curr_type = cmd.get_type()
			if not curr_type in self._cmd_dict:
				self._cmd_dict[curr_type] = []
			# include this command into request and update list with message tags
			self._cmd_dict[curr_type].append(cmd)
			self._cmd_deferred_list.append(cmd._deferred)
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

	def get_deferred_list(self):
		""" returns all deferred objects from included commands """
		return self._cmd_deferred_list

	def send(self, sendfunc):
		# send whole request via given send function

		# create valid JSON
		# (according to https://docs.python.org/2/library/json.html : default encoding is UTF8)
		req_str = json.dumps(self.as_dict())

		sendfunc.sendMessage(req_str)


class _DMSCmdGet(object):
	""" one unique "get" request, parsed from **kwargs """

	CMD_TYPE = u'get'

	def __init__(self, dmsclient, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.dmsclient = dmsclient
		self.path = u'' + path
		self.query = {}
		self.histData = {}
		self.showExtInfos = None
		self.tag, self._deferred = dmsclient.generate_tag()

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



class _DMSCmdResponse(_DMSFrame):
	def __init__(self):
		_DMSFrame.__init__(self)


class _MessageHandler(object):
	def __init__(self, *args, **kwargs):
		pass


class _SocketClient(WebSocketClient):
	# based on example on http://ws4py.readthedocs.io/en/latest/sources/clienttutorial/#built-in
	def __init__(self, *args, **kwargs):
		super(_SocketClient, self).__init__(*args, **kwargs)
		self.ready = False

	def handshake_ok(self):
		self.ready = True
		print("handshake_ok() -> starts client's thread")
		sys.stdout.flush()

	def opened(self):
		print('opened()')
		sys.stdout.flush()

	def closed(self, code, reason=None):
		self.ready = False
		print("closed(): code=" + str(code) + ", reason=" + str(reason))
		sys.stdout.flush()

	def received_message(self, m):
		# FIXME: it seems that this callback method gets never executed... why?!?!
		print("received_message(): " + repr(m))
		sys.stdout.write("received_message(): " + str(m.data.decode()))
		sys.stdout.flush()
		self._dmsclient.print_to_stdout(repr(m))
		self._dmsclient.testvar += 1



class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._whois_str = whois_str
		self._user_str = user_str
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int

		self.testvar = 0



		ws_URI = u"ws://" + self._dms_host_str + u':' + str(self._dms_port_int) + DMS_BASEPATH
		print('trying to connect to "' + ws_URI + '"...')

		self._ws = _SocketClient(ws_URI, protocols=['http-only', 'json'])
		self._ws._dmsclient = self

		# executing WebSocket eventloop in background
		#self._ws_thread = thread.start_new_thread(self._ws.connect, ())
		self._ws.connect()
		print("WebSocket connection will be established in background...")

	def send_testmessage(self):
		""" communication test: get DMS systemtime """
		if self._ws.ready:
			print('\tsending message...')
			self._ws.send(TESTMSG)

	def print_to_stdout(self, msg):
		"""" test: print from thread to stdout via DMSClient main thread """
		print(msg)


	def __del__(self):
		"""" closing websocket connection on object destruction """
		self._ws.close()
		time.sleep(1)
		self._ws_thread.exit()



if __name__ == '__main__':

	myClient = DMSClient(u'test', u'user',  dms_host_str='192.168.10.181')

	while True:
		time.sleep(1)
		print('"myClient.testvar" is now ' + str(myClient.testvar) + ')')
		myClient.send_testmessage()

	# print('\nTesting creation of Request command:')
	# print('"get":')
	# response = myClient.dp_get(path="System:Time")
	# print(repr(response))
	# print('\n=>quitting...')
