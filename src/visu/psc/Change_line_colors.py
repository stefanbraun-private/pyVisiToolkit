#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.Change_line_colors.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import Parser
import codecs
import sys
import os

import visu.psc.ParserVars

DEBUGGING = False
ENCODING_FILES_PSC = 'cp1252'
ENCODING_SRC_FILE = 'utf-8'
ENCODING_STDOUT = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

def get_encoding():
	global ENCODING_STDOUT
	# following code doesn't work in IDE
	ENCODING_STDOUT = sys.stdout.encoding or sys.getfilesystemencoding()

def my_print(line):
	"""
	wrapper for print()-function:
	-does explicit conversion from unicode to encoded byte-string
	-when parameter is already a encoded byte-string, then convert to unicode using "encoding cookie" and then to encoded byte-string
	"""
	unicode_line = ''
	if type(line) == str:
		# conversion byte-string -> unicode -> byte-string
		# (first encoding is source file encoding, second one is encoding of console)
		unicode_line = line.decode(ENCODING_SRC_FILE)
	else:
		# assuming unicode-string (we don't care about other situations, when called with wrong datatype then print() will throw exception)
		unicode_line = line

	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	print(unicode_line.encode(ENCODING_STDOUT, errors='replace'))

## FIXME: warum funktioniert untenstehender Code nicht?!?! ==>DEBUGGING!!! :-(

def main(argv=None):
	psc_directory = u'D:\Temp\ZH_Tièchestrasse'
	output_directory = u'D:\Temp\ZH_Tièchestrasse_new'

	for filename in os.listdir(psc_directory):
		if filename.endswith(u'.psc'):
			fullpath = os.path.join(psc_directory, filename)

			my_print(u'Parsing filename "' + fullpath + '"')
			curr_file = Parser.PscFile(fullpath)
			curr_file.parse_file()

			for elem in curr_file.get_psc_elem_list():
				if elem.get_property(u'id') == u'Line':
					# Warmwasser Rücklauf:
					# blau -> rot

					#DEBUGGING:
					#my_print(u'color-fg=' + repr(elem.get_property(u'color-fg')))
					#my_print(u'line-style=' + repr(elem.get_property(u'line-style')))

					if repr(elem.get_property(u'color-fg')) == repr(visu.psc.ParserVars.PscVar_RGB(0x0000FF)):
						my_print(u'.')
						if repr(elem.get_property(u'line-style')) == repr(visu.psc.ParserVars.PscVar_line_style.DASHED):
							my_print(u'..')
							#and elem.get_property(u'bmo-library') == u'':
							elem.set_property(u'color-fg', visu.psc.ParserVars.PscVar_RGB(0xFF0000))


			output_fullpath = os.path.join(output_directory, filename)
			# do write tests:
			curr_file.write_file(output_fullpath)

	return 0        # success


if __name__ == '__main__':
	get_encoding()
	status = main()
	# sys.exit(status)