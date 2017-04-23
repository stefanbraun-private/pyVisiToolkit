#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.Parser.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import codecs
import collections
import random
import sys

import ParserConfig
from visu.psc.ParserVars import *

DEBUGGING = False
ENCODING_FILES_PSC = 'cp1252'
ENCODING_SRC_FILE = 'utf-8'
ENCODING_STDOUT = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

PARSERCONFIGFILE = u'config.yml'

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


class PscParser(object):
	# class variable, one instance for all PSC objects
	cfg = None

	@classmethod
	def load_config(cls, filename=PARSERCONFIGFILE):
		cls.cfg = ParserConfig.ParserConfig(filename)


class PscFile(object):
	def __init__(self, filename):
		self._filename = filename
		self._visu_elems = []
		self._psc_window = None


	def parse_file(self):
		"""
		Separation line-by-line into graphic objects "PSC window" and every "PSC element",
		handing all sourcecode lines to the fresh created objects
		"""
		# reading textfile: example from
		# https://docs.python.org/2/tutorial/inputoutput.html#methods-of-file-objects
		# http://stackoverflow.com/questions/8009882/how-to-read-large-file-line-by-line-in-python
		# http://stackoverflow.com/questions/3277503/python-read-file-line-by-line-into-array
		with codecs.open(self._filename, encoding=ENCODING_FILES_PSC, mode=u'r') as f:
			curr_elem = collections.OrderedDict()
			curr_window = collections.OrderedDict()
			for line in f:
				curr_line = line.rstrip(u'\n\r')
				property_str = curr_line.split(u';')[0]
				if property_str in PscWindow.LINE_PREFIXES:
					# found window definition
					curr_window[property_str] = curr_line
				else:
					if property_str == u'ID' and len(curr_elem) != 0:
						# this is begin of new graph element =>process last element, prepare for next element
						self._add_graph_elem(curr_elem)
						curr_elem = collections.OrderedDict()
					curr_elem[property_str] = curr_line

			# process last element and window properties
			if curr_elem:
				self._add_graph_elem(curr_elem)
			self._psc_window = PscWindow(curr_window)


	def _add_graph_elem(self, lines_dict):
		# generate psc object according to it's ID
		# expected line in PSC file:
		# ID;0;Editbox
		curr_ID = lines_dict[u'ID'].split(u';')[2]
		if DEBUGGING:
			my_print(u'Parsed PSC element "' + curr_ID + u'"')
		new_elem = OBJ_DICT[curr_ID](lines_dict)
		self._visu_elems.append(new_elem)

	def get_psc_elem_list(self):
		return self._visu_elems

	def get_elem_list_at_coordinate(self, pos_x, pos_y):
		curr_list = []
		for elem in self._visu_elems:
			if elem.is_obj_at_coordinate(pos_x, pos_y):
				curr_list.append(elem)
		return curr_list

	def get_psc_window(self):
		return self._psc_window

	def write_file(self, filename=None):
		"""
		write PSC file. When no filename is given then it will overwrite current file.
		"""
		if filename == None:
			filename_str = self._filename
		else:
			filename_str = filename
		with codecs.open(filename_str, encoding=ENCODING_FILES_PSC, mode='w') as f:
			# first the window definition
			for line in self._psc_window.get_raw_lines():
				f.write(line + u'\r\n')

			# then all graphic elements according to their draworder
			# idea from https://wiki.python.org/moin/HowTo/Sorting
			for elem in sorted(self._visu_elems, key=lambda psc_elem: psc_elem.get_property(u'draw-order')):
				for line in elem.get_raw_lines():
					f.write(line + u'\r\n')


class PscCommon(object):
	"""
	implements common methods for PSC window and all PSC elements
	"""
	def __init__(self):
		# properties were parsed from the raw "self._lines_dict"
		self._properties_mapping_dict = {}

		# metadata properties which aren't stored or read in PSC files
		self._metadata_dict = {}

		# initialization of parser
		# FIXME: how to implement this a better way? Importing at runtime against import loops...
		if not PscParser.cfg:
			PscParser.load_config(PARSERCONFIGFILE)

		# extract properties from the loaded PSC file
		self._parse_properties()


	def _parse_properties(self):
		"""
		Grab all relevant properties from the raw sourcecode lines
		"""
		# FIXME: how to handle different PSC fileformat versions? Hmmmm...
		if DEBUGGING:
			my_print(u'Preparing parsing of PSC element "' + self.psc_elem_str + u'"')
		VER = u'v15'
		self._properties_mapping_dict = PscParser.cfg.get_property_mapping_dict(self.psc_elem_str, version_str=VER)
		if DEBUGGING:
			my_print(u'->it has to contain ' + unicode(len(self._properties_mapping_dict)) + u' properties...')


	def get_raw_lines(self):
		my_list = []
		for key in self._lines_dict:
			my_list.append(self._lines_dict[key])
		return my_list


	def get_property(self, prop_str):
		"""
		Retrieve PSC graphic element property ("prop_str" is a dictionary key =>case-sensitive!)
		"""

		my_prop = None
		try:
			# lookup key first in metadata properties
			my_prop = self._metadata_dict[prop_str]
		except KeyError:
			if DEBUGGING:
				my_print(u'get_property() was called for property "' + prop_str + '"')
			assert (prop_str in self._properties_mapping_dict), u'ERROR: property "' + prop_str + u'" is unknown for PSC element "' + self.psc_elem_str + u'"!'
			curr_mapping_obj = self._properties_mapping_dict[prop_str]
			if DEBUGGING:
				my_print(u'\ttype(curr_mapping_obj)=' + repr(type(curr_mapping_obj)))

			if isinstance(curr_mapping_obj, ParserConfig.Multipos_mapping):
				# this property has multiple storage locations... take the first one as original (while ignoring others)
				# =>dereference this link
				curr_prop_original_str = curr_mapping_obj.get_first_prop_string()
				if DEBUGGING:
					my_print(u'get_property() follows link to property "' + curr_prop_original_str + '"')
					assert (
						curr_prop_original_str in self._properties_mapping_dict), u'ERROR: property "' + curr_prop_original_str + u'" is unknown for PSC element "' + self.psc_elem_str + u'"!'
				curr_mapping_obj = self._properties_mapping_dict[curr_prop_original_str]
				if DEBUGGING:
					my_print(u'\ttype(curr_mapping_obj)=' + repr(type(curr_mapping_obj)))
				prop_str = curr_prop_original_str

			# extract wanted values from raw PSC line
			try:
				curr_raw_line = self._lines_dict[curr_mapping_obj.linemark]
			except KeyError:
				# PSC raw lines don't contain a line with requested linemark...
				raise KeyError(u'PSC element "' + self.psc_elem_str + u'" does not contain line with linemark "' + curr_mapping_obj.linemark + u'", property is "' + prop_str + u'"')
			if DEBUGGING:
				my_print(u'\tcurr_raw_line=' + repr(curr_raw_line))
			my_prop = curr_mapping_obj.get_property_obj(curr_raw_line)
			if DEBUGGING:
				my_print(u'\tmy_prop=' + repr(my_prop) + u' , type(my_prop)=' + repr(type(my_prop)))
		return my_prop


	def set_property(self, prop_str, new_val, new_key=False):
		"""
		Set PSC graphic element property ("prop_str" is a dictionary key =>case-sensitive!)

		=>when "new_key" is set, then we expect adding a new property (minimal protection against wrong spelling or overwriting)
		"""
		if new_val != None:
			if new_key:
				# only adding properties into metadata is possible
				assert prop_str not in self._metadata_dict, u'new property expected!'
				self._metadata_dict[prop_str] = new_val
			else:
				assert (prop_str in self._properties_mapping_dict) or (prop_str in self._metadata_dict), u'ERROR: property "' + prop_str + u'" is unknown for PSC element "' + self.psc_elem_str + '"!'
				assert prop_str != u'id', u'changing of PSC ID is not supported!'

				if prop_str in self._metadata_dict:
					self._metadata_dict[prop_str] = new_val
				else:
					if DEBUGGING:
						my_print(u'set_property() was called for property "' + prop_str + '"')
					mapping_obj = self._properties_mapping_dict[prop_str]
					if DEBUGGING:
						my_print(u'\ttype(mapping_obj)=' + repr(type(mapping_obj)))

					# prepare list of all storage locations of this property
					if isinstance(mapping_obj, ParserConfig.Multipos_mapping):
						# this property has multiple storage locations... write changes to all locations
						# =>dereference all link
						curr_mapping_obj_list = []
						for curr_prop in mapping_obj.get_prop_strings():
							if DEBUGGING:
								my_print(u'set_property() follows link to property "' + curr_prop + '"')
							assert (curr_prop in self._properties_mapping_dict), u'ERROR: property "' + curr_prop + u'" is unknown for PSC element "' + self.psc_elem_str + u'"!'
							curr_mapping_obj = self._properties_mapping_dict[curr_prop]
							if DEBUGGING:
								my_print(u'\ttype(curr_mapping_obj)=' + repr(type(curr_mapping_obj)))
							curr_mapping_obj_list.append(curr_mapping_obj)
					else:
						curr_mapping_obj_list = [mapping_obj]

					# serialize property into all storage locations
					for curr_mapping_obj in curr_mapping_obj_list:
						curr_raw_line = self._lines_dict[curr_mapping_obj.linemark]
						if DEBUGGING:
							my_print(u'\tcurr_raw_line=' + repr(curr_raw_line))


						if DEBUGGING:
							my_print(u'\tcurr_mapping_obj._update_value() is called with new_val=' + repr(new_val))
						# set wanted value in raw PSC line
						new_raw_line = curr_mapping_obj.update_value(curr_raw_line, new_val)
						self._lines_dict[curr_mapping_obj.linemark] = new_raw_line
						if DEBUGGING:
							my_print(u'\tnew_raw_line=' + repr(new_raw_line))

						# test: read same value again
						my_prop = curr_mapping_obj.get_property_obj(new_raw_line)
						if DEBUGGING:
							my_print(u'\tmy_prop=' + repr(my_prop) + u' , type(my_prop)=' + repr(type(my_prop)))
						# FIXME: a cleaner way to really compare two objects would be overriding further internal methods:
						# http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
						assert repr(new_val) == repr(my_prop), u'ERROR: storing and reloading property failed! new_val=' + repr(new_val) + u', my_prop=' + repr(my_prop)



	def get_properties_list(self):
		"""
		Get a list of all available properties of this PSC graphic element
		"""
		return self._properties_mapping_dict.keys()


class PscWindow(PscCommon):
	LINE_PREFIXES = [u'WPL', u'WIN', u'UMI']
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = ParserConfig.LIT_WINDOW
		PscCommon.__init__(self)



class PscElem(PscCommon):
	cnt_int = 0

	def __init__(self):
		PscCommon.__init__(self)

		# get draw order
		PscElem.cnt_int = PscElem.cnt_int + 1
		self.set_property(u'draw-order', PscElem.cnt_int, new_key=True)


	def is_obj_at_coordinate(self, pos_x, pos_y):
		sel_Area = self.get_property(u'selection-area')
		return sel_Area.is_point_in_area(int(pos_x), int(pos_y))


	def __repr__(self):
		myStr = u''
		for currProp in self._properties_mapping_dict:
			try:
				prop_value = self.get_property(currProp)
			except KeyError:
				# property doesn't have a value
				prop_value = None
			myStr = myStr + u'\t' + currProp + u'=' + repr(prop_value)
		return myStr


class PscLine(PscElem):
	ID = u'Line'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscLine.ID
		PscElem.__init__(self)



class PscButton(PscElem):
	ID = u'Button'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscButton.ID
		PscElem.__init__(self)


class PscCheckbox(PscElem):
	ID = u'Checkbox'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscCheckbox.ID
		PscElem.__init__(self)


class PscCircle(PscElem):
	ID = u'Circle'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscCircle.ID
		PscElem.__init__(self)


class PscCombobox(PscElem):
	ID = u'Combobox'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscCombobox.ID
		PscElem.__init__(self)


class PscEditbox(PscElem):
	ID = u'Editbox'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscEditbox.ID
		PscElem.__init__(self)


class PscIcon(PscElem):
	ID = u'Icon'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscIcon.ID
		PscElem.__init__(self)


class PscPolyline(PscElem):
	ID = u'Polyline'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscPolyline.ID
		PscElem.__init__(self)


class PscRadiobutton(PscElem):
	ID = u'Radio Button'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscRadiobutton.ID
		PscElem.__init__(self)


class PscRectangle(PscElem):
	ID = u'Rectangle'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscRectangle.ID
		PscElem.__init__(self)




class PscRoundRectangle(PscElem):
	ID = u'Round Rectangle'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscRoundRectangle.ID
		PscElem.__init__(self)


class PscRuler(PscElem):
	ID = u'Ruler'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscRuler.ID
		PscElem.__init__(self)

class PscText(PscElem):
	ID = u'Text'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscText.ID
		PscElem.__init__(self)


	def __repr__(self):
		my_print(u'PROBLEM with repr() on text "' + self.get_property(u'text') + u'"')
		return PscElem.__repr__(self) + u'\ttext: "' + unicode(self.get_property(u'text')) + u'"\ttextcolor: ' + unicode(repr(self.get_property(u'text-color')))


class PscTrend(PscElem):
	ID = u'Trend'
	def __init__(self, lines_dict):
		self._lines_dict = lines_dict
		self.psc_elem_str = PscTrend.ID
		PscElem.__init__(self)



OBJ_DICT = {    PscLine.ID:     PscLine,
                PscButton.ID:	PscButton,
                PscCheckbox.ID:	PscCheckbox,
                PscCircle.ID:	PscCircle,
                PscCombobox.ID:	PscCombobox,
                PscEditbox.ID:	PscEditbox,
                PscIcon.ID:	PscIcon,
                PscPolyline.ID:	PscPolyline,
                PscRadiobutton.ID:	PscRadiobutton,
                PscRectangle.ID:	PscRectangle,
                PscRoundRectangle.ID:	PscRoundRectangle,
                PscRuler.ID:	PscRuler,
                PscText.ID:     PscText,
                PscTrend.ID:	PscTrend
                }


def main(argv=None):
	# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
	PscParser.load_config(PARSERCONFIGFILE)

	filename = r'C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\scr\file1.psc'
	filename2 = r'C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\scr\file_changed.psc'

	curr_file = PscFile(filename)

	curr_file.parse_file()

	for elem in curr_file.get_psc_elem_list():
		curr_group = elem.get_property(u'group')
		my_print(u'\tgroup: ' + str(curr_group.get_value()))

		if isinstance(elem, PscText):
			curr_string = elem.get_property(u'text_string')
			my_print(u'\t\ttext_string: ' + curr_string.get_value())
			# test: append string to current string
			curr_string.set_value(curr_string.get_value() + u'ADDED_TEXT')
			elem.set_property(u'text_string', curr_string)
			my_print(u'\t\ttext_string (changed): ' + str(elem.get_property(u'text_string').get_value()))

			# font attributes
			my_print(u'\t\ttext_font_name: ' + elem.get_property(u'text_font_name').get_value())
			my_print(u'\t\ttext_font_size: ' + str(elem.get_property(u'text_font_size').get_value()))

		if isinstance(elem, PscButton):
			try:
				rights_list = map(lambda x: u'accessrights-userlevel' + unicode(x).zfill(2), range(1,17))
				for right in rights_list:
					curr_right = elem.get_property(right)
					is_right_set = curr_right.get_value()
					my_print(u'\t\t' + right + u' is now ' + repr(is_right_set))
					# test: invert all bits
					curr_right.set_value(not is_right_set)
					elem.set_property(right, curr_right)
					my_print(u'\t\t' + right + u' changed to ' + repr(elem.get_property(right)))
			except KeyError:
				my_print(u'\t\t=>button does not contain accessrights...')

			# buttons can contain text....
			curr_string = elem.get_property(u'text_string')
			my_print(u'\t\ttext_string: ' + curr_string.get_value())
			# test: append string to current string
			curr_string.set_value(curr_string.get_value() + u'ADDED_TEXT')
			elem.set_property(u'text_string', curr_string)
			my_print(u'\t\ttext_string (changed): ' + elem.get_property(u'text_string').get_value())

			# font attributes
			my_print(u'\t\ttext_font_name: ' + elem.get_property(u'text_font_name').get_value())
			curr_font_size = elem.get_property(u'text_font_size')
			my_print(u'\t\ttext_font_size: ' + str(curr_font_size.get_value()))
			curr_font_size.set_value(24)
			elem.set_property(u'text_font_size', curr_font_size)
			my_print(u'\t\ttext_font_size (changed): ' + str(curr_font_size.get_value()))

		if isinstance(elem, PscLine):
			curr_color = elem.get_property(u'color-fg')
			my_print(u'\t\tcolor-fg is now ' + repr(curr_color))
			new_color = PscVar_RGB(u'#0000FF')
			my_print(u'\t\tTEST: new_color=' + repr(new_color) + u', as tuple: ' + repr(new_color.get_tuple()) + u', as HTML: ' + repr(new_color.get_html()) + u', as int: ' + repr(new_color.get_int()) + u', in serialized from: ' + repr(new_color.get_serialized()))
			elem.set_property(u'color-fg', new_color)
			my_print(u'\t\tcolor-fg changed to ' + repr(elem.get_property(u'color-fg')))

		if isinstance(elem, PscLine):
			curr_sel_area = elem.get_property(u'selection-area')
			my_print(u'\t\tselection-area is now ' + repr(curr_sel_area))
			new_sel_area = PscVar_rectangle(50, 50, 150, 150)
			elem.set_property(u'selection-area', new_sel_area)
			my_print(u'\t\tselection-area changed to ' + repr(elem.get_property(u'selection-area')))

		if isinstance(elem, PscLine):
			curr_line_style = elem.get_property(u'line-style')
			my_print(u'\t\tline-style is now ' + repr(curr_line_style))
			new_line_style = PscVar_line_style(random.randint(0, 4))
			elem.set_property(u'line-style', new_line_style)
			my_print(u'\t\tline-style changed to ' + repr(elem.get_property(u'line-style')))

		if isinstance(elem, PscLine):
			try:
				dmskey = elem.get_property(u'init_color-fg_from-n_dmskey')
				my_print('\t\tinit_color-fg_from-n_dmskey=' + dmskey.get_value())
				has_gradient = elem.get_property(u'init_color-fg_from-n_gradient')
				my_print('\t\tinit_color-fg_from-n_gradient=' + repr(has_gradient))
				rgb_pairs = elem.get_property(u'init_color-fg_from-n_val-rgb-pairs')
				my_print('\t\tinit_color-fg_from-n_val-rgb-pairs=' + repr(rgb_pairs))

			except KeyError:
				my_print(u'\t\t=>line does not contain whole color-fg initialisation...')


	# write changes to new file
	curr_file.write_file(filename2)

	# my_print(u'\n*** coordinate check ***')
	# for x in range(10):
	# 	my_print(u'\ntest no. ' + str(x))
	# 	coord = (random.randrange(0, 1280),random.randrange(0, 1024))
	# 	my_print(u'At coordinate ' + repr(coord) + u' we have:')
	# 	for elem in curr_file.get_elem_list_at_coordinate(coord[0], coord[1]):
	# 		my_print(repr(elem))
	#
	# # some tests:
	# my_print(u'\nPscVar_RGB(123).get_html() = ' + PscVar_RGB(123).get_html() + u'\n')
	# my_print(u'\nPscVar_RGB((255,0,0)).get_html() = ' + PscVar_RGB((255,0,0)).get_html() + u'\n')
	# my_print(u'PscVar_RGB("123").get_html() = ' + PscVar_RGB(u"123").get_html() + u'\n')
	# my_print(u'PscVar_RGB(#FF00FF).get_html() = ' + PscVar_RGB(u'#FF00FF').get_html() + u'\n')
	#
	# # do write tests:
	# curr_file.write_file(r'C:\test.psc')

	return 0        # success


if __name__ == '__main__':
	get_encoding()
	status = main()
	# sys.exit(status)