#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket_test2.py

Copyright (C) 2017 Stefan Braun

current state august 6th 2017:
=>this file is discontinued, these were first steps with WebSocket, twisted, autobahn and TinyDB
(result: DMS answered JSON request. This seemed the way to go...)


used technologies for DMS communication with JSON:
-WebSocket: "autobahn"
-asynchronous datatransfer: "twisted"
https://autobahn.readthedocs.io/en/latest/websocket/programming.html

handling of JSON messages like a database:
http://tinydb.readthedocs.io/en/latest/


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
from twisted.internet import reactor
import json
from tinydb import TinyDB, Query, where
from tinydb.storages import MemoryStorage

TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')


# according "ProMoS DMS JSON Data Exchange":
DMS_PORT = 9020             # cleartext HTTP or WebSocket
DMS_HOST = "127.0.0.1"      # local connection: doesn't need authentification
DMS_BASEPATH = "/json_data" # default for HTTP and WebSocket


class MyClientProtocol(WebSocketClientProtocol):
	def onOpen(self):
		print("MyClientProtocol: onOpen() was called...")
		self.sendMessage(TESTMSG.encode('utf8'))

	def onMessage(self, payload, isBinary):
		if isBinary:
			print("Binary message received: {0} bytes".format(len(payload)))
		else:
			print("Text message received: {0}".format(payload.decode('utf8')))

			# parsing of payload as JSON and extract some values
			# based on example from http://pythonmonthly.com/tinydb-intro.html
			print("\nas Python dictionary:")
			payload_dict = json.loads(payload.decode('utf8'))
			print(repr(payload_dict))

			print("\nextract of some values")
			db = TinyDB(storage=MemoryStorage)
			for get in payload_dict['get']:
				print("trying to insert " + repr(get) + " into TinyDB...")
				db.insert(get)

			print('TinyDB contains now: ' + repr(db.all()))

			#Dp = Query()
			#for attr in ["path", "code", "type", "value", "stamp", "hasChild"]:
			#print("path:\t" + str(db.search(where('path'))))


		# stopping twisted reactor loop after this message...
		# idea from https://stackoverflow.com/questions/6526923/stop-twisted-reactor-on-a-condition
		reactor.callFromThread(reactor.stop)




if __name__ == '__main__':

	import sys

	#log.startLogging(sys.stdout)

	# since we want to access another path than "/" we need to use a "wss"-URI
	# (seen on https://github.com/crossbario/autobahn-python/blob/master/examples/twisted/websocket/ping/server.py )
	factory = WebSocketClientFactory(u"wss://" + DMS_HOST + u':' + str(DMS_PORT) + DMS_BASEPATH)
	factory.protocol = MyClientProtocol

	# creation of TCP connection: timeout is in seconds
	reactor.connectTCP(DMS_HOST, DMS_PORT, factory, timeout=10)
	reactor.run()