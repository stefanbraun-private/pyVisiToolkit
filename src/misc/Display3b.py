#!/usr/bin/env python
# encoding: utf-8
"""
misc.Display3b.py      v0.0.1
Driver for a Display in GE (Grafikeditor)

using ASCII-art: every row is a textfield containing one character per pixel,
text is stored in STR datapoint in DMS
=>ressource friendly, faster than display2: needs only 100 DMS write operations for a 100x100 pixel display...
=>current implementation: using 8bit grayscale per pixel


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
import numpy as np



# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('misc.Display3b')
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
	DMS_BASEKEY = 'System:Display3'
	SCREEN_WIDTH = 100
	SCREEN_HEIGHT = 100

	# Implementation of a grayscale display
	# examples for conversion of any image to ASCII art:
	# https://www.hackerearth.com/practice/notes/beautiful-python-a-simple-ascii-art-generator-from-images/
	# https://gist.github.com/cdiener/10567484

	# This is a list of characters from low to high "blackness" in order to map the
	# intensities of the image to ascii characters
	# (copied from https://gist.github.com/cdiener/10567484 )
	# FIXME: find a better suited character list for getting good result in GE
	CHARS = list(' .,:;irsXA253hMHGS#9B&@')

	def __init__(self, dms_ws):
		self._dms_ws = dms_ws

		# storing display: using numpy two dimensional array, one 8bit value per pixel
		# help from https://stackoverflow.com/questions/16396141/python-numpy-2d-array-indexing
		# numpy datatypes: https://docs.scipy.org/doc/numpy-1.12.0/reference/arrays.dtypes.html
		self._buffer = np.zeros((Display.SCREEN_HEIGHT, Display.SCREEN_WIDTH), dtype='uint8')

		# every row has a dirty flag
		self._dirty_rows = [True] * Display.SCREEN_HEIGHT

		self._last_update = 0
		self.update()


	def _map_char_to_8bit(self, intensity):
		assert 0 <= intensity <= 255, 'illegal intensity "' + str(intensity) + '", 8bit value expected'
		intensity_per_char = 256.0 / len(Display.CHARS)
		idx = int(intensity / intensity_per_char)
		return Display.CHARS[idx]


	def _get_pixel(self, x, y):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position: "' + str(x) + '"'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position: "' + str(y) + '"'
		return self._buffer[x, y]

	def _set_pixel(self, x, y, intensity):
		assert 0 <= x <= Display.SCREEN_WIDTH, 'illegal x position: "' + str(x) + '"'
		assert 0 <= y <= Display.SCREEN_HEIGHT, 'illegal y position: "' + str(y) + '"'
		assert 0 <= intensity <= 255, 'illegal intensity "' + str(intensity) + '", 8bit value expected'
		if self._get_pixel(x, y) != intensity:
			self._buffer[x, y] = intensity
			self._dirty_rows[y] = True


	def show_random_pixels(self):
		for x in range(Display.SCREEN_WIDTH):
			for y in range(Display.SCREEN_HEIGHT):
				self._set_pixel(x, y, random.randint(0, 255))
		self.update()


	def show_gradient(self):
		for x in range(Display.SCREEN_WIDTH):
			intensity = 255.0 / Display.SCREEN_WIDTH * x
			for y in range(Display.SCREEN_HEIGHT):
				self._set_pixel(x, y, int(intensity))
		self.update()


	def show_function(self, func):
		# users function is getting called with coordinates x, y
		# =>users function has to return a 8 bit pixel intensity as integer
		for x in range(Display.SCREEN_WIDTH):
			for y in range(Display.SCREEN_HEIGHT):
				intensity = max(0, min(255, func(x, y)))
				self._set_pixel(x, y, intensity)
		self.update()


	def white_screen(self):
		for y in range(Display.SCREEN_HEIGHT):
			# indexing/slicing in numpy arrays: help from https://www.tutorialspoint.com/numpy/numpy_indexing_and_slicing.htm
			one_row = self._buffer[y, ...]
			if max(one_row) > 0:
				self._buffer[y, ...] = np.array((0), dtype='uint8')
				self._dirty_rows[y] = True
		self.update()


	def black_screen(self):
		for y in range(Display.SCREEN_HEIGHT):
			# indexing/slicing in numpy arrays: help from https://www.tutorialspoint.com/numpy/numpy_indexing_and_slicing.htm
			one_row = self._buffer[y, ...]
			if min(one_row) < 255:
				self._buffer[y, ...] = np.array((255), dtype='uint8')
				self._dirty_rows[y] = True
		self.update()



	def update(self):
		''' redraw changed lines '''
		# randomly update row for smoother screen redrawing
		# (with help from https://stackoverflow.com/questions/9252373/random-iteration-in-python )
		#
		# =>conversion of bitfield into a string of chars representing every pixel,
		#   it's very similar to Display2

		row_idx_list = range(Display.SCREEN_HEIGHT)
		random.shuffle(row_idx_list)
		for y in row_idx_list:
			if self._dirty_rows[y]:
				chars_list = []
				for x in range(Display.SCREEN_WIDTH):
					intensity = self._get_pixel(x, y)
					chars_list.append(self._map_char_to_8bit(intensity))
				curr_dmskey = Display.DMS_BASEKEY + ':' + str(y).zfill(3)
				resp = self._dms_ws.dp_set(path=curr_dmskey,
				                           value=''.join(chars_list),
				                           create=True)
				self._dirty_rows[y] = False


def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'misc.Display3b',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		disp = Display(dms_ws)

		# some tests (user can choose with dropdown menu)

		# first: write menu constants,
		# currently 10 constants are prepared in dropdown-menu on PSC image
		resp = dms_ws.dp_set(path=':'.join([disp.DMS_BASEKEY, "Dropdown"]),
		                     value=1,
		                     type='int',
		                     create=True)

		dropdown_const_list = []
		for idx, item in enumerate(["white_screen",
		                            "black_screen",
		                            "show_gradient",
		                            "show_random_pixels",
		                            "show_function 1",
		                            "show_function 2",
		                            "show_function 3",
		                            "show_function 4",
		                            "show_function 5",
		                            "STOP Python program"]):
			dropdown_const_list.extend([item, str(idx + 1)])     # first item in arrays in DMS have index 1
		resp = dms_ws.dp_set(path=':'.join([disp.DMS_BASEKEY, "Dropdown", "Constants"]),
		                     value="{" + ','.join(dropdown_const_list) + "}",
		                     create=True)

		# registering callback function when user changes dropdop menu
		# help with function attributes (I had troubles with variable scopes inside of functions)
		# https://stackoverflow.com/questions/5218895/python-nested-functions-variable-scoping
		main.pause = True
		main.choice = 1
		def cb_dropdown_menu(event):
			main.choice = event.value
			logger.debug('cb_dropdown_menu(): choice=' + str(main.choice))
			main.pause = False


		sub_obj = dms_ws.get_dp_subscription(path=':'.join([disp.DMS_BASEKEY, "Dropdown"]),
		                                     event=dms.ON_CHANGE)
		msg = sub_obj.sub_response.message
		if not msg:
			sub_obj += cb_dropdown_menu
			logger.info('main(): monitoring of DMS key "' + sub_obj.sub_response.path + '" is ready.')
		else:
			logger.error('main(): monitoring of DMS key "' + msg.path + '" failed! [message: ' + msg + '])')

		keep_running = True
		while keep_running:
			if main.pause:
				time.sleep(0.1)
			else:
				if main.choice == 1:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					disp.white_screen()
					end_time = time.time()
					logger.info('disp.white_screen() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 2:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					disp.black_screen()
					end_time = time.time()
					logger.info('disp.black_screen() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 3:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					disp.show_gradient()
					end_time = time.time()
					logger.info('disp.show_gradient() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 4:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					disp.show_random_pixels()
					end_time = time.time()
					logger.info('disp.show_random_pixels() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 5:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					import math
					def pixel_intensity(x, y):
						x_intens = math.sin(2 * math.pi / 360.0 * 15 * x)
						y_intens = math.sin(2 * math.pi / 360.0 * 15 * y)
						return int(128 + x_intens * y_intens * 128)

					disp.show_function(func=pixel_intensity)
					end_time = time.time()
					logger.info('disp.show_function() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 6:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					import math
					def pixel_intensity(x, y):
						origx, origy = Display.SCREEN_WIDTH / 2, Display.SCREEN_HEIGHT / 2
						dist_from_origin = math.sqrt(abs(origx - x) ** 2 + abs(origy - y) ** 2)
						intensity = math.sin(2 * math.pi / 360.0 * 10 * dist_from_origin)
						return int(128 + intensity * 128)

					disp.show_function(func=pixel_intensity)
					end_time = time.time()
					logger.info('disp.show_function() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 7:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					import math
					def pixel_intensity(x, y):
						if x == y:
							return 0
						else:
							return 255

					disp.show_function(func=pixel_intensity)
					end_time = time.time()
					logger.info('disp.show_function() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 8:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					import math
					def pixel_intensity(x, y):
						origx, origy = Display.SCREEN_WIDTH / 2, 0
						dist_from_origin = math.sqrt(abs(origx - x) ** 2 + abs(origy - y) ** 2)
						intensity = math.sin(2 * math.pi / 360.0 * 10 * dist_from_origin)
						return int(128 + intensity * 128)

					disp.show_function(func=pixel_intensity)
					end_time = time.time()
					logger.info('disp.show_function() needed ' + str(end_time - begin_time) + 's')

				elif main.choice == 9:
					logger.info('main(): choice=' + str(main.choice))
					begin_time = time.time()
					import math
					def pixel_intensity(x, y):
						intensity = math.sin(2 * math.pi / 360.0 * 10 * x) * (y / 255.0)
						return int(128 + intensity * 128)

					disp.show_function(func=pixel_intensity)
					end_time = time.time()
					logger.info('disp.show_function() needed ' + str(end_time - begin_time) + 's')

				else:
					logger.info('main(): choice=' + str(main.choice))
					keep_running = False

				main.pause = True

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