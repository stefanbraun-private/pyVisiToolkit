#!/usr/bin/env python
# encoding: utf-8
"""
misc.Visi_Snake.py

"Snake"-game implemented in ProMos NT(c).

Based on code from https://gist.github.com/sanchitgangwar/2158089
with special thanks to Sanchit Gangwar | https://github.com/sanchitgangwar

notes:
-textfields in GE can simulate a character-based display:
 -font "Courier New" is monospaced (every character uses same space)
 -direction of text "center justified" (only this way you get multiline text)
 -initialisation is a DMS-key with datatype STR and formatstring "%s"
 -every row is a substring(filled with space for getting same length),
  these rows were separated by "\n" for getting the whole string representing the whole display
-researches showed that it's possible to store a lot of data in a DMS-datapoint with type STR:
 -maximal 999 characters gets serialized in DMS file, but it seems that 79 chars + \NULL is maximum by design.
 -during runtime it can store much more
 -GE crashes when you're trying to display more than 8k characters in a textfield




Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import misc.Curses_emulator as curses
import sys
import locale
import argparse
import random



ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = True

# floating point precision in ProMoS NT(c)
NOF_DECIMAL_DIGITS = 6

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



class VisiSnake(object):

	VISISNAKE_DMS_KEY = "Visi_Snake"




def main(filename, argv=None):
	get_encoding()

	my_print(u'misc.Visi_Snake.py')
	my_print(u'******************')

	curr_snake = VisiSnake()


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Snake game for ProMoS NT(c).')

	args = parser.parse_args()
	status = main()
	sys.exit(status)