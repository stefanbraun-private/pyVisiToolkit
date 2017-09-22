#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017 Stefan Braun

current state september 21th 2017:
=>successful communication after merging working part of "dmswebsocket.py" into this mini-test!
  (it's based on a example from https://pypi.python.org/pypi/websocket-client )

current state august 6th 2017:
=>test with WebSocket library https://github.com/websocket-client/websocket-client
(without using complicated huge frameworks)
==>it seems that this library does only WebSocket communication,
   but DMS needs first a HTTP/1.1 request with WebSocket connection upgrade/handshake... :-(
==>CORRECTION: during tests the URI started with wss:// instead of ws://, perhaps without SSL it had worked...?


This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""




import json
import time
import uuid
import websocket
import thread


TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')


# according "ProMoS DMS JSON Data Exchange":
DMS_PORT = 9020             # cleartext HTTP or WebSocket
DMS_HOST = "127.0.0.1"      # local connection: doesn't need authentification
DMS_BASEPATH = "/json_data" # default for HTTP and WebSocket







class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._whois_str = whois_str
		self._user_str = user_str
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int

		# based on example on https://github.com/websocket-client/websocket-client
		# websocket.enableTrace(True)
		ws_URI = u"ws://" + self._dms_host_str + u':' + str(self._dms_port_int) + DMS_BASEPATH
		self._ws = websocket.WebSocketApp(ws_URI,
		                                  on_message=self._cb_on_message,
		                                  on_error=self._cb_on_error,
		                                  on_open=self._cb_on_open,
		                                  on_close=self._cb_on_close)
		# executing WebSocket eventloop in background
		self._ws_thread = thread.start_new_thread(self._ws.run_forever, ())
		# FIXME: how to return caller a non-reachable WebSocket server?
		print("WebSocket connection will be established in background...")


	def _cb_on_message(self, ws, message):
		print("_on_message(): " + repr(message))

	def _cb_on_error(self, ws, error):
		print("_on_error(): " + error)

	def _cb_on_open(self, ws):
		print("_on_open()")

		def sendertest():
			print('Testing creation of Request command five times:')
			for x in range(5):
				print('sending "' + TESTMSG + '"')
				self._ws.send(TESTMSG)
				time.sleep(1)
			self._ws.close()
		# putting sendertest() into background
		self._sendertest_thread = thread.start_new_thread(sendertest, ())


	def _cb_on_close(self, ws):
		print("_on_close()")

	def __del__(self):
		"""" closing websocket connection on object destruction """
		self._ws.close()
		time.sleep(1)
		self._ws_thread.exit()



if __name__ == '__main__':

	myClient = DMSClient(u'test', u'user') #,  dms_host_str='192.168.10.181')
	print('\n=>WebSocket connection runs now in background...')

	while True:
		# mainthread is running in endless loop, allowing processing of background threads...
		time.sleep(0.001)

