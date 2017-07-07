#!/usr/bin/env python
# encoding: utf-8
"""
misc.Blinkenlights_Emulator.py

emulates display for Blinkenlights movies in Grafikeditor
(this script needs its counterparts in DMS and a special PSC file)

ideas for improvements:
-Blinkenlights file selection via dropdown GUI element in PSC file
-implement all four specified Blinkenlights movie file formats
 [OK]    blm - BlinkenLights Movie
 [TBD]   bmm - BlinkenMini Movie
 [TBD]   bml - Blinkenlights Markup Language
 [TBD]   bbm - Binary Blinken Movie
 ==>currently we have only a monochrome "display" with one bit per pixel, no grayscale or RGB...


How does the monochrome display work?
In "Grafikeditor" it's possible to change color by a binary DMS key. This way we got a monochrome display,
where we use one BIT value in DMS for each pixel (transmitted as 32bit integer).
The visibility of each pixel is controlled by enable bits in two 32bit integers,
this gives a maximal dimension of 32 rows and 32 columns.


=>URLs for more information:
general info:
https://de.wikipedia.org/wiki/Projekt_Blinkenlights
http://wiki.blinkenarea.org/index.php/Blinkenlights_Movie

technical specification:
http://blinkenlights.net/project/developer-tools
http://oldwiki.blinkenarea.org/bin/view/Blinkenarea/DateiFormate

examples:
http://www.apo33.org/pub/puredata/luc/degoyon/blinkenlights/blm/raumschiff_enterprise.blm
http://dpnc.unige.ch/users/meunier/DATA/src/iowarrior/SDK/MacOSX/Sources/BlinkenWarrior/BlinkenLights%20Movies/Scrolltext.blm
http://s23.org/wiki/Blinkenlights/Movies



Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import sys
import locale
import os
import time
import re
import argparse



ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = True

NOF_ROWS = 32
NOF_COLUMNS = 32

def get_encoding():
	global ENCODING_STDOUT1
	# following code seems only to work in IDE...
	ENCODING_STDOUT1= sys.stdout.encoding or sys.getfilesystemencoding()

	# hint from http://stackoverflow.com/questions/9226516/python-windows-console-and-encodings-cp-850-vs-cp1252
	# following code doesn't work in IDE because PyCharm uses UTF-8 and not encoding from Windows command prompt...
	global ENCODING_STDOUT2
	ENCODING_STDOUT2 = locale.getpreferredencoding()

	# another try: using encoding-guessing of IDE "IDLE"
	# hint from https://mail.python.org/pipermail/tkinter-discuss/2010-December/002602.html
	global ENCODING_LOCALE
	import idlelib.IOBinding
	ENCODING_LOCALE = idlelib.IOBinding.encoding
	print(u'Using encoding "' + ENCODING_LOCALE + u'" for input and trying "' + ENCODING_STDOUT1 + u'" or "' + ENCODING_STDOUT2 + u'" for STDOUT')

def my_print(line):
	"""
	wrapper for print()-function:
	-does explicit conversion from unicode to encoded byte-string
	-when parameter is already a encoded byte-string, then convert to unicode using "encoding cookie" and then to encoded byte-string
	"""
	unicode_line = u''
	if type(line) == str:
		# conversion byte-string -> unicode -> byte-string
		# (first encoding is source file encoding, second one is encoding of console)
		if not ENCODING_LOCALE:
			get_encoding()
		unicode_line = line.decode(ENCODING_LOCALE)
	else:
		# assuming unicode-string (we don't care about other situations, when called with wrong datatype then print() will throw exception)
		unicode_line = line

	if not (ENCODING_STDOUT1 and ENCODING_STDOUT2):
		get_encoding()
	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	try:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT1, errors='strict')
	except UnicodeEncodeError:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT2, errors='strict')
	print(bytestring_line)


class BlmFrame(object):
	def __init__(self):
		self.row_list = []  # one integer per row represents 32 pixels per row
		self.row_length = None

	def set_duration(self, duration_int):
		self.duration_int = duration_int

	def append_row(self, row_str):
		if not self.row_length:
			self.row_length = len(row_str)
		elif self.row_length != len(row_str):
			print('WARNING: row "' + row_str + '" has wrong length, is this BLM-file corrupted?')
		# constructor of integer accepts string
		# (help from http://stackoverflow.com/questions/8928240/convert-base-2-binary-number-string-to-int )
		self.row_list.append(int(row_str, 2))

	def get_size(self):
		return self.row_length, len(self.row_list)

	def get_rows(self):
		for row in self.row_list:
			yield row

	def get_duration_in_secs(self):
		# time to show this frame in seconds
		return self.duration_int / 1000.0


class BlmFile(object):
	def __init__(self, filename_str):
		self.frames_list = []
		self.filename_str = filename_str
		self._parsefile()

	def _parsefile(self):
		with open(self.filename_str, 'r') as f:
			duration_pattern = r'^@(\d+)'
			pixel_pattern = r'^([01]+)'
			curr_frame = None
			for line in f:
				m = re.match(duration_pattern, line)
				if m:
					# found a new frame: add old one to our list, create new one
					if curr_frame:
						self.frames_list.append(curr_frame)
					curr_frame = BlmFrame()
					curr_frame.set_duration(int(m.group(1)))

				m = re.match(pixel_pattern, line)
				if m:
					curr_frame.append_row(m.group(1))
			# handle last frame
			if curr_frame:
				self.frames_list.append(curr_frame)

	def play(self, emulator_frame_callback):
		for frm in self.frames_list:
			width, height = frm.get_size()
			if DEBUGGING:
				my_print(u'current frame: width=' + str(width) + u', height=' + str(height))

			emulator_frame_callback(width, height, frm.get_rows())

			time.sleep(frm.get_duration_in_secs())



class Blinkenlights_Emulator(object):

	EMULATOR_DMS_KEY = "BlinkenlightsEmulator"

	def __init__(self, filename_str, curr_dms, endless_movie=True):
		self.blmovie = BlmFile(filename_str=filename_str)
		self.endless_movie = endless_movie
		self.curr_dms = curr_dms
		self.curr_width = 0
		self.curr_height = 0
		self._check_consistence()
		self._blank_display()

	def _check_consistence(self):
		if DEBUGGING:
			my_print('checking consistency of DMS tree...')
		is_valid = True

		# all row raw values
		for x in range(NOF_ROWS):
			curr_dp = self._get_dp_for_row(x)
			if self.curr_dms.is_dp_available(curr_dp):
				if DEBUGGING:
					my_print('DEBUG: DMS key "' + curr_dp + '" is available.')
			else:
				if DEBUGGING:
					my_print('ERROR: missing DMS key "' + curr_dp + '"!')
				is_valid = False

		# row and column enable bits
		row_dms_key = ':'.join([Blinkenlights_Emulator.EMULATOR_DMS_KEY, "Row:EnableBitfield"])
		column_dms_key = ':'.join([Blinkenlights_Emulator.EMULATOR_DMS_KEY, "Column:EnableBitfield"])
		for curr_dp in [row_dms_key, column_dms_key]:
			if self.curr_dms.is_dp_available(curr_dp):
				if DEBUGGING:
					my_print('DEBUG: DMS key "' + curr_dp + '" is available.')
			else:
				if DEBUGGING:
					my_print('ERROR: missing DMS key "' + curr_dp + '"!')
				is_valid = False

		if is_valid:
			if DEBUGGING:
				my_print('DMS tree seems ready for Blinkenlights...')
		else:
			my_print('\nERROR: DMS tree for Animation seems corrupted...! Quitting...')
			raise RuntimeError


	def _blank_display(self):
		self._set_dimension(NOF_ROWS, NOF_COLUMNS)

		# reset whole image
		for x in range(NOF_ROWS):
			curr_dp = self._get_dp_for_row(x)
			self.curr_dms.pyDMS_WriteDWUEx(curr_dp, 0)

		if DEBUGGING:
			my_print(u'display is ready for Blinkenlights... :-)')


	def show_frame(self, width_int, height_int, row_integers_list):
		''' callback function for showing one Blinkenlights movie frame '''
		self._set_dimension(width_int, height_int)

		# 32 pixels in a row are stored and transmitted as one integer value
		for column, row_rawvalue in enumerate(row_integers_list):
			if DEBUGGING:
				my_print(u'current row: ' + bin(row_rawvalue)[2:].zfill(width_int))
			dms_key = self._get_dp_for_row(column)
			self.curr_dms.pyDMS_WriteDWUEx(dms_key, row_rawvalue)


	def _set_dimension(self, width_int, height_int):
		''' activate rows and columns on our "display" '''
		if self.curr_width != width_int:
			dms_key = ':'.join([Blinkenlights_Emulator.EMULATOR_DMS_KEY, "Column:EnableBitfield"])
			self.curr_dms.pyDMS_WriteDWUEx(dms_key, self._get_enable_bitmask(width_int, NOF_COLUMNS))
			self.curr_width = width_int

		if self.curr_height != height_int:
			dms_key = ':'.join([Blinkenlights_Emulator.EMULATOR_DMS_KEY, "Row:EnableBitfield"])
			self.curr_dms.pyDMS_WriteDWUEx(dms_key, self._get_enable_bitmask(height_int, NOF_ROWS))
			self.curr_height = height_int


	def _get_enable_bitmask(self, nof_visible_pixels, nof_max_pixels):
		bitstring = '1' * min(nof_visible_pixels, nof_max_pixels)
		return int(bitstring, 2)

	def _get_dp_for_row(self, row_int):
		''' DMS tree where Animation rows are stored (one 32bit value as bitmap per row) '''
		return ':'.join([Blinkenlights_Emulator.EMULATOR_DMS_KEY, 'Row', str(row_int).zfill(2), 'Raw'])


	def play_moviefile(self):
		# help from http://stackoverflow.com/questions/13180941/how-to-kill-a-while-loop-with-a-keystroke
		try:
			play_movie = True
			while play_movie:
				self.blmovie.play(self.show_frame)

				play_movie = self.endless_movie
		except KeyboardInterrupt:
			pass
		print('Quitting "misc.Animation"...')


def main(blm_filename, argv=None):
	get_encoding()

	my_print(u'misc.Blinkenlights_Emulator.py')
	my_print(u'******************************')

	curr_dms = dms.dmspipe.Dmspipe()
	if DEBUGGING:
		my_print(u'INFO: Currently this project is running:')
		prj = curr_dms.pyDMS_ReadSTREx('System:Project')
		computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
		my_print(u'\t"System:Project"=' + prj)
		my_print(u'\t"System:NT:Computername"=' + computer)

	curr_emulator = Blinkenlights_Emulator(blm_filename, curr_dms)

	if DEBUGGING:
		my_print('\nstarting Blinkenlights movie... :-)')
	try:
		curr_emulator.play_moviefile()
	except RuntimeError:
		return 1
	return 0        # success

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Blinkenlights emulator for ProMoS NT(c).')

	parser.add_argument('BLM_FILENAME', help='filename of Blinkenlights movie (usually *.blm)')

	args = parser.parse_args()
	status = main(blm_filename=args.BLM_FILENAME)
	sys.exit(status)