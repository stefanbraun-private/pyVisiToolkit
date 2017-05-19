#!/usr/bin/env python
# encoding: utf-8
"""
misc.Animation.py

show some useless animation in Grafikeditor
(this script needs its counterparts in DMS and a special PSC file)


Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import sys
import locale
import os
import random
import time



ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = False

NOF_ROWS = 32
NOF_COLUMNS = 32
PAUSE_SECONDS = 0.2

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


def get_dp_for_row(row):
	''' DMS tree where Animation rows are stored (one 32bit value as bitmap per row) '''
	return "Animation:Row:" + str(row).zfill(2) + ':Raw'


def main(argv=None):
	get_encoding()

	my_print(u'misc.Animation.py')
	my_print(u'*****************')

	curr_dms = dms.dmspipe.Dmspipe()


	prj = curr_dms.pyDMS_ReadSTREx('System:Project')
	computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
	my_print(u'"System:Project"=' + prj)
	my_print(u'"System:NT:Computername"=' + computer)

	curr_ge_instance = None
	for running_ge in curr_dms.get_DMS_sons_list_by_key('System:Prog:GE'):
		ge_up_bit = ':'.join(['System:Prog:GE', running_ge[0], 'UP'])
		if ge_up_bit:
			my_print(u'GE instance with flag "' + ge_up_bit + u'" seems to be in use...')
			curr_ge_instance = running_ge[0]

	if not curr_ge_instance:
		my_print(u'\nERROR: Grafikeditor is not running!!!')
		return 1

	my_print('checking consistency of DMS tree...')
	is_valid = True
	for x in range(NOF_ROWS):
		curr_dp = get_dp_for_row(x)
		if not curr_dms.is_dp_available(curr_dp):
			is_valid = False
			break
	if is_valid:
		my_print('\nstarting Animation... :-)')

		# reset whole image
		for x in range(NOF_ROWS):
			curr_dp = get_dp_for_row(x)
			curr_dms.pyDMS_WriteDWUEx(curr_dp, 0)

		# following a road: bitshift a bit pattern randomly to the left or rigth
		rows_list = NOF_ROWS * [0]
		# our "road": some bits are set (hint: preview pattern with "bin(xyz)")
		bit_pattern = 2047

		# help from http://stackoverflow.com/questions/13180941/how-to-kill-a-while-loop-with-a-keystroke
		try:
			while True:
				if rows_list[0] == 0:
					# we got an empty road, it's our first run...
					# setting row somewhere into middle of screen
					new_value = bit_pattern << (NOF_COLUMNS / 2 - 2)
				else:
					# insert a new road row on top
					previous_value = rows_list[0]

					if random.choice([True, False]):
						# change position of road in first row with random bitshift
						direction = random.choice(["LEFT", "RIGHT"])
						if direction == "LEFT":
							if previous_value < 2 ** (NOF_COLUMNS - 1):
								# road is still on the screen...
								new_value = previous_value << 1
						else:
							if previous_value > bit_pattern:
								# road is still on the screen...
								new_value = previous_value >> 1
					else:
						# default: draw road at the same position as last time
						new_value = previous_value

				# doing insertion on top
				rows_list.insert(0, new_value)

				# write all rows to screen and remove last element
				for x in range(NOF_ROWS):
					curr_row_value = rows_list[x]

					curr_dp = get_dp_for_row(x)
					if DEBUGGING:
						my_print('\twriting value "' + str(curr_row_value) + '" into DMS datapoint ' + curr_dp)
						my_print('\t(datatype: ' + repr(type(curr_row_value)))
					curr_dms.pyDMS_WriteDWUEx(curr_dp, curr_row_value)

				if len(rows_list) > NOF_ROWS:
					rows_list = rows_list[:NOF_ROWS]

				# help from http://stackoverflow.com/questions/699866/python-int-to-binary
				my_print('drawn road "' + "{0:b}".format(new_value).zfill(NOF_COLUMNS))
				time.sleep(PAUSE_SECONDS)
		except KeyboardInterrupt:
			pass
		print('Quitting "misc.Animation"...')

	else:
		my_print('\nDMS tree for Animation seems corrupted... Quitting...')
		return 1

	return 0        # success


if __name__ == '__main__':
	status = main()
	# sys.exit(status)