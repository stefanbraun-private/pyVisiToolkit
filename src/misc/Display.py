#!/usr/bin/env python
# encoding: utf-8
"""
misc.Display.py      v0.0.1
Driver for a Display in GE (Grafikeditor)

one PSC-rectangle object per pixel,
it's visibility is controlled by a BIT datapoint in DMS
=>ressource hogging and very slow: needs 10'000 DMS write operations for a 100x100 pixel display...


Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



import dms.dmswebsocket as dms
import logging
import argparse
import random
import time



# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('misc.Display')
logger.setLevel(logging.DEBUG)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)



class Display(object):
	DMS_BASEKEY = 'System:Display'
	SCREEN_WIDTH = 100
	SCREEN_HEIGHT = 100

	def __init__(self, dms_ws):
		self._dms_ws = dms_ws

	def show_random_points(self):
		for y in range(Display.SCREEN_HEIGHT):
			for x in range(Display.SCREEN_WIDTH):
				resp = self._dms_ws.dp_set(path=Display.DMS_BASEKEY + ':' + str(x).zfill(3) + ':' + str(y).zfill(3),
			                           value=random.choice([False, True]),
			                           create=True)



def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'misc.Display',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		disp = Display(dms_ws)

		# some tests:
		begin_time = time.time()
		disp.show_random_points()
		end_time = time.time()
		logger.info('disp.show_random_points() needed ' + str(end_time - begin_time) + 's')


	logger.info('Quitting "Display"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Driver for a Display in GE (Grafikeditor)')

	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port)
	#sys.exit(status)