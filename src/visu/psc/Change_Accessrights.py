#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.Change_Accessrights.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import os
import sys
import Parser

DIR_VLO = r'D:\Temp\VLO_changes'

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

	if not ENCODING_STDOUT:
		get_encoding()
	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	print(unicode_line.encode(ENCODING_STDOUT, errors='replace'))





def main(argv=None):
	# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
	Parser.PscParser.load_config(Parser.PARSERCONFIGFILE)

	for filename in os.listdir(DIR_VLO):
		if filename.endswith(u'.psc'):
			my_print(u'processing file "' + filename + u'"...')

			psc_fullpath = os.path.join(DIR_VLO, filename)
			curr_file = Parser.PscFile(psc_fullpath)
			curr_file.parse_file()

			input_elements = [u'Button', u'Checkbox', u'Combobox', u'Editbox', u'Icon', u'Radio Button']
			rights_list = map(lambda x: u'accessrights-userlevel' + unicode(x).zfill(2), range(1, 17))
			for elem in curr_file.get_psc_elem_list():
				curr_id = elem.get_property(u'id')
				if curr_id in input_elements:
					curr_rights_set = set()
					try:
						for right in rights_list:
							if elem.get_property(right):
								curr_rights_set.add(right)
						cutting_func = lambda x: x[-2:]
						userlevels_list = map(cutting_func, sorted(curr_rights_set))
						my_print(u'\tPSC element "' + curr_id + u'" has access rights:\t\t\t' + u', '.join(userlevels_list))
					except KeyError as ex:
						my_print(u'\tignoring PSC element "' + curr_id + u'" (does not have initialisation)')
			my_print(u'*' * 20 + u'\n\n')
	# write changes to new file
	#curr_file.write_file(filename2)



	return 0        # success


if __name__ == '__main__':
	get_encoding()
	status = main()
	# sys.exit(status)