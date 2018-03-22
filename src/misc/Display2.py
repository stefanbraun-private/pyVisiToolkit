#!/usr/bin/env python
# encoding: utf-8
"""
misc.Display2.py      v0.0.1
Driver for a Display in GE (Grafikeditor)

one PSC-rectangle object per pixel,
it's visibility is controlled by addressing an element in an array stored in STR datapoint in DMS
=>ressource hogging, but faster than display1: needs only 100 DMS write operations for a 100x100 pixel display...


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
logger = logging.getLogger('misc.Display2')
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
	DMS_BASEKEY = 'System:Display2'
	SCREEN_WIDTH = 100
	SCREEN_HEIGHT = 100

	def __init__(self, dms_ws):
		self._dms_ws = dms_ws

		# storing bitfield: one row is a 100 bit integer, storing a list of integers
		# (attention: bit order is reversed compared to display position!)
		# inspired by:
		# https://wiki.python.org/moin/BitwiseOperators
		# https://wiki.python.org/moin/BitArrays
		self._bitfield = [0] * Display.SCREEN_HEIGHT

		# every row has a dirty flag
		self._dirty_rows = [True] * Display.SCREEN_HEIGHT

		self._last_update = 0
		self.update()


	def _test_bit(self, x, y):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position'
		row = self._bitfield[y]
		mask = 1 << x
		return bool(row & mask)

	def _set_bit(self, x, y):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position'
		mask = 1 << x
		old_row = self._bitfield[y]
		self._bitfield[y] = old_row | mask
		if old_row != self._bitfield[y]:
			self._dirty_rows[y] = True

	def _clear_bit(self, x, y):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position'
		mask = ~(1 << x)
		old_row = self._bitfield[y]
		self._bitfield[y] = old_row & mask
		if old_row != self._bitfield[y]:
			self._dirty_rows[y] = True

	def _inv_bit(self, x, y):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position'
		mask = 1 << x
		old_row = self._bitfield[y]
		self._bitfield[y] = old_row ^ mask
		if old_row != self._bitfield[y]:
			self._dirty_rows[y] = True


	def show_random_pixels(self):
		for x in range(Display.SCREEN_WIDTH):
			for y in range(Display.SCREEN_HEIGHT):
				if random.choice([True, False]):
					self._set_bit(x, y)
				else:
					self._clear_bit(x, y)
		self.update()


	def invert_pixels(self):
		for x in range(Display.SCREEN_WIDTH):
			for y in range(Display.SCREEN_HEIGHT):
				if self._test_bit(x, y):
					self._clear_bit(x, y)
				else:
					self._set_bit(x, y)
		self.update()


	def blank_screen(self):
		for y in range(Display.SCREEN_HEIGHT):
			if self._bitfield[y] != 0:
				self._bitfield[y] = 0
				self._dirty_rows[y] = True
		self.update()


	def lightup_screen(self):
		for y in range(Display.SCREEN_HEIGHT):
			allbits = (2**Display.SCREEN_WIDTH) - 1
			if self._bitfield[y] != allbits:
				self._bitfield[y] = allbits
				self._dirty_rows[y] = True
		self.update()



	def update(self):
		''' redraw changed lines '''
		# randomly update row for smoother screen redrawing
		# (with help from https://stackoverflow.com/questions/9252373/random-iteration-in-python )
		#
		# =>conversion of bitfield into a string-array of chars representing every pixel with "0" or "1"
		row_idx_list = range(Display.SCREEN_HEIGHT)
		random.shuffle(row_idx_list)
		for y in row_idx_list:
			if self._dirty_rows[y]:
				bits_list = []
				for x in range(Display.SCREEN_WIDTH):
					if self._test_bit(x, y):
						bits_list.append('1')
					else:
						bits_list.append('0')
				bits_str = ','.join(bits_list)
				curr_dmskey = Display.DMS_BASEKEY + ':' + str(y).zfill(3) + ':cells_array'
				resp = self._dms_ws.dp_set(path=curr_dmskey,
				                           value=''.join(['{', bits_str, '}']),
				                           create=True)
				self._dirty_rows[y] = False


def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'misc.Display2',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		disp = Display(dms_ws)

		# some tests:
		for x in range(1):
			begin_time = time.time()
			disp.blank_screen()
			end_time = time.time()
			logger.info('disp.blank_screen() needed ' + str(end_time - begin_time) + 's')

			time.sleep(4)

			begin_time = time.time()
			disp.show_random_pixels()
			end_time = time.time()
			logger.info('disp.show_random_pixels() needed ' + str(end_time - begin_time) + 's')

			time.sleep(4)

			begin_time = time.time()
			disp.invert_pixels()
			end_time = time.time()
			logger.info('disp.invert_pixels() needed ' + str(end_time - begin_time) + 's')

			time.sleep(4)

			begin_time = time.time()
			disp.invert_pixels()
			end_time = time.time()
			logger.info('disp.invert_pixels() needed ' + str(end_time - begin_time) + 's')

			time.sleep(4)

			begin_time = time.time()
			disp.lightup_screen()
			end_time = time.time()
			logger.info('disp.lightup_screen() needed ' + str(end_time - begin_time) + 's')

			time.sleep(4)

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