#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017 Stefan Braun


current state august 6th 2017:
=>this file is discontinued, these were further steps with WebSocket, twisted, autobahn and crochet
(result: WebSocket handshake happens via HTTP/1.1, then TCP connection gets immediatly closed without any reason.
Perhaps these huge frameworks are too complicated to learn in short time...?!?)
==>CORRECTION: during tests the URI started with wss:// instead of ws://, perhaps without SSL it had worked...?

used technologies for DMS communication with JSON:
-WebSocket: "autobahn"
-asynchronous datatransfer: "twisted"
https://autobahn.readthedocs.io/en/latest/websocket/programming.html

handling of JSON messages like a database:
http://tinydb.readthedocs.io/en/latest/

hide internal asynchronous details of twisted:
https://crochet.readthedocs.io/en/1.7.0/using.html#hide-twisted-and-crochet

ideas:
-reconnection when connection is lost:
https://github.com/crossbario/autobahn-python/tree/master/examples/twisted/websocket/reconnecting

example for clean connection establishment and closing
https://stackoverflow.com/questions/31078728/exiting-python-program-after-closing-connection-in-twisted


This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



from autobahn.twisted.websocket import WebSocketClientProtocol
from autobahn.twisted.websocket import WebSocketClientFactory
from twisted.python import log
from twisted.internet import reactor, defer
import json
import time
import uuid
import logging

from crochet import wait_for, run_in_reactor, setup
setup()


#TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')
TESTMSG = (u'{"get":[{"path":"System:Time"}]}')

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






# twisted code hidden by crochet
# help from https://crochet.readthedocs.io/en/1.7.0/using.html#hide-twisted-and-crochet
class _DMSClientProtocol(WebSocketClientProtocol):
	def __init__(self, *args, **kwargs):
		super(_DMSClientProtocol, self).__init__(*args, **kwargs)
		# dict for pending task (key: cmd-tag, value: twisted defer object)
		self._pending_deferred_dict = {}
		print('INIT of _DMSClientProtocol()')

	def onOpen(self):
		print("_DMSClientProtocol: onOpen() was called...")
		self.sendMessage(TESTMSG.encode('utf8'))
		# update instance reference in client
		self.dmsclient.protocol_obj = self

	def onClose(self, wasClean, code, reason):
		# based on https://github.com/crossbario/autobahn-python/blob/master/examples/twisted/websocket/echo/client.py
		print("_DMSClientProtocol: onClose: {0}".format(reason))
		# remove instance reference in client
		self.dmsclient.protocol_obj = None

	def onMessage(self, payload, isBinary):
		if isBinary:
			print("Binary message received: {0} bytes".format(len(payload)))
			print("=>ignoring...")
		else:
			print("Text message received: {0}".format(payload.decode('utf8')))
			print("=>parsing it's content...")

			# parsing of payload as JSON and extract some values

			print("\nas Python dictionary:")
			payload_dict = json.loads(payload.decode('utf8'))
			print(repr(payload_dict))


			# message handler
			if u'get' in payload_dict:
				# handling responses to "get"
				for get_resp in payload_dict[u'get']:
					if u'tag' in get_resp:
						curr_tag = get_resp[u'tag']
						if curr_tag in self._pending_deferred_dict:
							print('\tidentified response to our request.')
							# FIXME: handling response, creating "res_obj"
							curr_deferred = self._pending_deferred_dict[curr_tag]
							# giving back result and "fire" this deferred
							# FIXME: what is correct?
							#curr_deferred.addCallback(lambda ignored: res_obj)
							curr_deferred.callback(get_resp)
						else:
							print('\tignoring unexpected response...')
					else:
						print('\tignoring untagged response...')

			# FIXME: test this idea: // but we have to share "_pending_defers_dict" somehow...
			# 1) message handler parses incoming messages
			# 2) if it's an answer to a known message tag, then add a callback to this Deferred() object
			#    d.addcallback(lambda notused: DMSResponse(args))
			# 3) fire this callback
			#    d.callback(args)

	def get_deferred(self, tag):
		if not tag in self._pending_deferred_dict:
			self._pending_defers_dict[tag] = defer.Deferred()
		return self._pending_defers_dict[tag]


class MyWebSocketClientFactory(WebSocketClientFactory):
	""" this factory creates protocol instances and holds a reference to it """
	# idea from http://twistedmatrix.com/documents/current/core/howto/clients.html#persistent-data-in-the-factory
	def __init__(self, *args, **kwargs):
		super(MyWebSocketClientFactory, self).__init__(*args, **kwargs)

	def buildProtocol(self, addr):
		p = super(MyWebSocketClientFactory, self).buildProtocol(addr)
		# giving protocol backreferences to current instances
		p.factory_obj = self
		p.dmsclient_obj = self.dmsclient
		return p


# twisted code hidden by crochet
class _DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str, dms_port_int):
		self._whois_str = whois_str
		self._user_str = user_str
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int
		# reference to protocol instance
		self.protocol_obj = None


	def start(self):
		""" start background process: twisted event loop """

		# since we want to access another path than "/" we need to use a "wss"-URI
		# (seen on https://github.com/crossbario/autobahn-python/blob/master/examples/twisted/websocket/ping/server.py )
		factory = MyWebSocketClientFactory(u"ws://" + self._dms_host_str + u':' + str(self._dms_port_int) + DMS_BASEPATH)
		factory.protocol = _DMSClientProtocol
		factory.dmsclient = self

		# creation of TCP connection: timeout is in seconds
		reactor.connectTCP(self._dms_host_str, self._dms_port_int, factory, timeout=10)


	def dp_get(self, path, **kwargs):
		""" read datapoint value(s) """

		while not self.protocol_obj:
			# FIXME: busy waiting until protocol has built a WebSocket connection. Improve this code!!!
			time.sleep(0.1)
		print('DEBUG')
		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(_DMSCmdGet(protocol=self.protocol_obj, path=path))
		req.send(self.protocol_obj)

		# this client implementation allows initialisation of only one DMS "get" command per call
		# (handling of more than one should already work)
		deferreds = req.get_deferred_list()
		if len(deferreds) == 1:
			return deferreds[0]
		else:
			return deferreds


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

	def generate_tag(self):
		# generating random and nearly unique message tags
		# (see https://docs.python.org/2/library/uuid.html )
		# and create a twisted deferred object for async handling
		# (see http://twistedmatrix.com/documents/current/core/howto/defer.html#callbacks )
		curr_tag = str(uuid.uuid4())

		curr_deferred = self.protocol_obj.get_deferred(curr_tag)
		return curr_tag, curr_deferred



# blocking wrapper
class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._dmsclient = _DMSClient(whois_str, user_str, dms_host_str, dms_port_int)
		self._start()

	@run_in_reactor
	def _start(self):
		# start background process
		self._dmsclient.start()


	@wait_for(timeout=120)
	def dp_get(self, path, **kwargs):
		""" read datapoint value(s) """
		path_str = u'' + path

		# FIXME: what should we return to external caller?
		return self._dmsclient.dp_get(path=path_str, **kwargs)

	@wait_for(timeout=120)
	def dp_set(self):
		""" write datapoint value(s) """
		pass

	@wait_for(timeout=120)
	def dp_del(self):
		""" delete datapoint(s) """
		pass

	@wait_for(timeout=120)
	def dp_ren(self):
		""" rename datapoint(s) """
		pass

	@wait_for(timeout=120)
	def dp_sub(self):
		""" subscribe monitoring of datapoints(s) """
		pass

	@wait_for(timeout=120)
	def dp_unsub(self):
		""" unsubscribe monitoring of datapoint(s) """
		pass


if __name__ == '__main__':

	import sys

	#log.startLogging(sys.stdout)

	# example for logging on https://crochet.readthedocs.io/en/stable/introduction.html
	logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
	myClient = DMSClient(u'test', u'user', dms_host_str='192.168.10.181')
	print('\n=>WebSocket connection runs now in background...')
	for x in range(3):
		# appending string to current line: https://stackoverflow.com/questions/3249524/print-in-one-line-dynamically
		print '.',
		time.sleep(1)
	print('\nTesting creation of Request command:')
	print('"get":')
	response = myClient.dp_get(path="System:Time")
	print(repr(response))
	print('\n=>quitting...')
