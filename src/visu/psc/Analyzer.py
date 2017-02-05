#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.Analyzer.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import Parser
#import collections
#import re
#import random
#import codecs
import sys


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


def pretty_print(line1, line2):
	"""
	print difference in textline as human-readable table
	"""
	parts1 = line1.split(u';')
	parts2 = line2.split(u';')

	nof_parts = max(len(parts1), len(parts2))
	# normalize lists: include empty parts if one PSC line has more CSV fields
	# (help from http://stackoverflow.com/questions/12550929/how-to-make-all-lists-in-a-list-of-lists-the-same-length-by-adding-to-them )
	for curr_parts_list in [parts1, parts2]:
		length = len(curr_parts_list)
		if length < nof_parts:
			curr_parts_list.extend([u'' for _ in xrange(nof_parts - length)])

	# indent for better readability
	out_header = u'\t'
	out_stars = u'\t'
	out_line1 = u'\t'
	out_line2 = u'\t'
	out_marker = u'\t'

	for idx in range(nof_parts):
		headerpart = u'Part ' + unicode(idx)

		# every cell is printed with same length
		nof_chars = max(len(headerpart), len(parts1[idx]), len(parts2[idx]))
		# appending to end of all output lines...
		out_header += headerpart + u' ' * (nof_chars - len(headerpart)) + u'| '
		out_stars += u'*' * (nof_chars + 2)
		out_line1 += parts1[idx] + u' ' * (nof_chars - len(parts1[idx])) + u'| '
		out_line2 += parts2[idx] + u' ' * (nof_chars - len(parts2[idx])) + u'| '

		# marker line: has an "X" in the column with the different PSC part
		cell_middle = nof_chars / 2 - 1
		markercell_as_list = list(u' ' * (nof_chars + 2))
		if parts1[idx] != parts2[idx]:
			markercell_as_list[cell_middle] = u'X'
		out_marker += u''.join(markercell_as_list)

	for line in (out_header, out_stars, out_line1, out_line2, out_marker):
		my_print(line)
	print(u'')


def main(argv=None):
	file1 = r'C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\scr\file1.psc'
	file2 = r'C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\scr\file2.psc'
	files = (file1, file2)

	my_print(u'PSC Analyzer')
	my_print(u'************')
	my_print(u'File1:\t' + files[0])
	my_print(u'File2:\t' + files[1])
	my_print(u'*' * len(files[1]))

	curr_files = {}
	for f in files:
		curr_files[f] = Parser.PscFile(f)
		my_print(u'Parsing file "' + f + '"...')
		curr_files[f].parse_file()
		my_print(u'Done.')

	my_print(u'Comparing PSC window definition:')
	lines = {}
	for f in files:
		lines[f] = curr_files[f]._psc_window.get_raw_lines()

	assert len(lines[file1]) == len(lines[file2]), 'comparison of different amount of lines is not implemented!'
	for idx, line in enumerate(lines[file1]):
		if line != lines[file2][idx]:
			my_print(u'\t=>difference found in line number ' + unicode(idx) + u':')
			pretty_print(line, lines[file2][idx])



	my_print(u'Comparing PSC graphic elements definition:')
	# walking through all PSC graphic elements and compare them with second file
	# (comparing PSC files with different arranging of elements is not supported and possibly will crash this code!)
	for elem_idx, elem in enumerate(curr_files[file1]._visu_elems):
		lines = {}

		lines[file1] = elem.get_raw_lines()
		lines[file2] = curr_files[file2]._visu_elems[elem_idx].get_raw_lines()

		assert len(lines[file1]) == len(lines[file2]), 'comparison of different amount of lines is not implemented!'
		for idx, line in enumerate(lines[file1]):
			if line != lines[file2][idx]:
				my_print(u'\t=>difference found in element line number ' + unicode(idx) + u':')
				pretty_print(line, lines[file2][idx])


	return 0        # success


if __name__ == '__main__':
	get_encoding()
	status = main()
	# sys.exit(status)