#!/usr/bin/env python
# encoding: utf-8
"""
misc.Curses_emulator.py

"curses"-lookalike emulator in ProMos NT(c) for character-based terminal applications.

Idea:
Using a textfield in GE and one STR-datapoint in DMS.
Implementation of all character-relevant methods of https://docs.python.org/2/library/curses.html
(sorry, no possibility for color and mouse interaction)


notes:
-textfields in GE can simulate a character-based display:
 -font "Courier New" is monospaced (every character uses same space)
 -direction of text "center justified" (only this way you get multiline text)
 -initialisation is a DMS-key with datatype STR and formatstring "%s"
 -every row is a substring(filled with space for getting same length),
  these rows were separated by "\n" for getting the whole string representing the whole display
-researches showed that it's possible to store a lot of data in a DMS-datapoint with type STR:
 -maximal 999 characters gets serialized in DMS file
 -during runtime it can store much more
 -GE crashes when you're trying to display more than 8k characters in a textfield
-for responsive user interaction we should implement event-based callbacks in DMS pipe... Otherwise it's only polling...


differences to "curses":
=>it seems that Python "curses" library doesn't follow class name capitalization convention, but we do...
https://stackoverflow.com/questions/14973963/if-the-convention-in-python-is-to-capitalize-classes-why-then-is-list-not-cap

=>Hmm, in Python's "curse" it seems that there exists only ONE terminal screen at the same time...
==>I want to allow multiple screens, so we have different classes and instances.

==>"show stopper": it seems that DMS-datapoint "STR" written by pyDMS_WriteSTREx has a maximum length of 80 characters,
 while in DMS executable it's possible to include much more... :-(
 =>dirty hack: we have to start "SetDMSVal.exe" and send the huge string (this way it WILL work!), look in BMO_Tiepoint_Info)


Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import sys
import locale
import argparse
import random

ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = True


SCREEN_MAX_LINES = 25
SCREEN_MAX_COLS = 80



def get_encoding():
	global ENCODING_STDOUT1
	# following code seems only to work in IDE...
	ENCODING_STDOUT1 = sys.stdout.encoding or sys.getfilesystemencoding()

	# hint from http://stackoverflow.com/questions/9226516/python-windows-console-and-encodings-cp-850-vs-cp1252
	# following code doesn't work in IDE because PyCharm uses UTF-8 and not encoding from Windows command prompt...
	global ENCODING_STDOUT2
	ENCODING_STDOUT2 = locale.getpreferredencoding()

	# another try: using encoding-guessing of IDE "IDLE"
	# hint from https://mail.python.org/pipermail/tkinter-discuss/2010-December/002602.html
	global ENCODING_LOCALE
	import idlelib.IOBinding
	ENCODING_LOCALE = idlelib.IOBinding.encoding
	print(
	u'Using encoding "' + ENCODING_LOCALE + u'" for input and trying "' + ENCODING_STDOUT1 + u'" or "' + ENCODING_STDOUT2 + u'" for STDOUT')


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


class Error(Exception):
	''' custom exception when an error occours in curses-emulator '''
	# based on help from https://stackoverflow.com/questions/1319615/proper-way-to-declare-custom-exceptions-in-modern-python
	def __init__(self, message):
		# Call the base class constructor with the parameters it needs
		Exception.__init__(message)


class _CharMatrix(object):
	''' two-dimensional array as list of lists for organizing characters '''
	def __init__(self, nlines, ncols):
		self._nlines = nlines
		self._ncols = ncols
		line_list = ['*'] * ncols
		self._matrix = [line_list] * nlines

	def as_multiline_string(self):
		lines = []
		for line_list in self._matrix:
			lines.append(''.join(line_list))
		return '\\n'.join(lines)


class Screen(object):
	''' whole "display" '''
	def __init__(self, curr_dms, dms_key_str, nlines=SCREEN_MAX_LINES, ncols=SCREEN_MAX_COLS):
		self._curr_dms = curr_dms
		self._dms_key = dms_key_str
		self._nlines = nlines
		self._ncols = ncols
		self._stdscr = None
		self._window_list = []
		self._display = _CharMatrix(nlines, ncols)

	def _write_display(self):
		self._curr_dms.pyDMS_WriteSTREx(self._dms_key, self._display.as_multiline_string())

	def initscr(self):
		''' setup and return standard window object (representation of whole screen) '''
		self._write_display()
		self._stdscr = Window(self, nlines=SCREEN_MAX_LINES, ncols=SCREEN_MAX_COLS, begin_y=0, begin_x=0)
		return self._stdscr

	def newwin(self, nlines, ncols, begin_y=0, begin_x=0):
		''' returns a window object '''
		win = Window(self, nlines, ncols, begin_x, begin_y)
		self._window_list.append(win)
		return win

	def refresh(self):
		''' redraw current window '''
		self._write_display()


class Window(object):
	''' a subarea inside the screen area '''

	def __init__(self, curr_screen, nlines, ncols, begin_y, begin_x):
		self._curr_screen = curr_screen
		self._nlines = nlines
		self._ncols = ncols
		self._begin_y = begin_y
		self._begin_x = begin_x
		self._curr_pos_y = 0
		self._curr_pos_x = 0

	def refresh(self):
		''' redraw current window '''
		self._curr_screen.refresh()


class Pad(Window):
	''' an area greater than actual screen '''




def main():
	get_encoding()

	curr_dms = dms.dmspipe.Dmspipe()
	if DEBUGGING:
		my_print(u'INFO: Currently this project is running:')
		prj = curr_dms.pyDMS_ReadSTREx('System:Project')
		computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
		my_print(u'\t"System:Project"=' + prj)
		my_print(u'\t"System:NT:Computername"=' + computer)

	curr_screen = Screen(curr_dms, 'Testval2', 8, 8)
	stdscr = curr_screen.initscr()


if __name__ == '__main__':

	status = main()
	sys.exit(status)