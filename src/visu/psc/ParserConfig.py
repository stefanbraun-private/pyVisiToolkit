#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.ParserConfig.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import yaml
import sys
import re

import Parser
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


# literal strings: these were embedded into configuration file
LIT_VERSION15 =           'v15'
LIT_VERSION16 =           'v16'
LIT_VERSION17 =           'v17'
LIT_LINEMARK =      '_linemark'
LIT_SPLIT =         '_split'
LIT_SPLIT_LISTOBJECT = '_split_listobject'
LIT_SPLIT_BIT =     '_split_bit'
LIT_REGEXPATTERN =  '_regexpattern'
LIT_OBJ =           '_obj'
LIT_WINDOW =        'WINDOW'
LIT_MULTIPOS =      'MULTIPOS'
LIT_REFERENCE =     '_reference'


def write_raw_configfile(fname):
	my_config = {LIT_WINDOW: {LIT_VERSION15: {'WPL': '',
	                                'WIN': '',
	                                'UMI': ''}
	                        },
	             'GENERIC': {LIT_VERSION15: {'id': {LIT_LINEMARK: 'ID', LIT_SPLIT: 2, LIT_OBJ: 'str'},
	                                 'library': {LIT_LINEMARK: 'LIB', LIT_SPLIT: 1, LIT_OBJ: 'str'},
	                                 'bmo-class': {LIT_LINEMARK: 'LIB', LIT_SPLIT: 2, LIT_OBJ: 'str'},
	                                 'bmo-instance': {LIT_LINEMARK: 'LIB', LIT_SPLIT: 3, LIT_OBJ: 'str'},
	                                 'bmo-class-key': {LIT_LINEMARK: 'LIB', LIT_SPLIT: 4, LIT_OBJ: 'str'},
	                                 'selection-area': {LIT_LINEMARK: 'PSDV', LIT_SPLIT: [1,2,3,4], LIT_OBJ: 'rectangle'},
	                                 'group': {LIT_LINEMARK: 'PSDV', LIT_SPLIT: 11, LIT_OBJ: 'int'},
	                                 'fgcolor': {LIT_LINEMARK: 'PEN', LIT_SPLIT: 2, LIT_OBJ: 'RGB'},
	                                 'bgcolor': {LIT_LINEMARK: 'PEN', LIT_SPLIT: 11, LIT_OBJ: 'RGB'},
	                                 }
	                        },
	            }
	with open(fname, u'w') as ymlfile:
		yaml.dump(my_config, ymlfile, default_flow_style=False)


class ParserConfig(object):
	"""
	Manages YAML configuration file for mapping logical names to absolut position in PSC graphic elements
	"""
	def __init__(self, fname):
		get_encoding()
		if DEBUGGING:
			my_print(u'ParserConfig is loading configuration file "' + fname + '"')
		self._filename = fname
		self._config_dict = None
		self._load_config()

	def _load_config(self):
		with open(self._filename, u'r') as ymlfile:
			self._config_dict = yaml.load(ymlfile)


	def get_available_versions(self, psc_graph_elem_str):
		"""
		returns all documented PSC versions for given PSC graph element
		"""
		version_list = []
		for version in self._config_dict[psc_graph_elem_str]:
			version_list.append(unicode(version, encoding=ENCODING_FILES_PSC))
		return version_list


	def get_property_mapping_dict(self, psc_graph_elem_str, property_str=u'', version_str=LIT_VERSION15):
		"""
		returns a dictionary of mapping objects for PSC graphics element
		(e.g. Parser could ask for all "Line" properties)
		=>when called with a specific property then list will contain only this mapping object
		"""
		try:
			mapping_dict = {}
			graph_elem_dict = self._config_dict[psc_graph_elem_str][version_str]
			for prop in graph_elem_dict:
				if property_str == u'' or prop == property_str:
					# include all or only the one property into mapping_list

					# assumption: every property has a LINEMARK
					linemark = graph_elem_dict[prop][LIT_LINEMARK]

					# assumption: every property has an OBJECT
					property_obj = graph_elem_dict[prop][LIT_OBJ]

					# fill the right mapping object, it has to know how to access the properties
					map_obj = None
					if linemark == LIT_MULTIPOS:
						# this property is stored under multiple positions
						if LIT_REFERENCE in graph_elem_dict[prop]:
							map_obj = Multipos_mapping(graph_elem_dict[prop][LIT_REFERENCE])
					else:
						# this property is stored at one position
						if LIT_REGEXPATTERN in graph_elem_dict[prop]:
							map_obj = Mapping_regex(regex_pattern_str = graph_elem_dict[prop][LIT_REGEXPATTERN],
							                        linemark_str = linemark,
						                            property_obj_str = property_obj
						                            )
						elif LIT_SPLIT in graph_elem_dict[prop]:
							map_obj = Mapping_split(split_arg = graph_elem_dict[prop][LIT_SPLIT],
									                        linemark_str = linemark,
									                        property_obj_str = property_obj
									                        )
						elif LIT_SPLIT_LISTOBJECT in graph_elem_dict[prop]:
							map_obj = Mapping_split_listobject(split_arg = graph_elem_dict[prop][LIT_SPLIT_LISTOBJECT],
									                        linemark_str = linemark,
									                        property_obj_str = property_obj
									                        )
						elif LIT_SPLIT_BIT in graph_elem_dict[prop]:
							map_obj = Mapping_split_bit(split_bit_arg = graph_elem_dict[prop][LIT_SPLIT_BIT],
								                        linemark_str = linemark,
								                        property_obj_str = property_obj
								                        )
					if map_obj:
						mapping_dict[prop]=map_obj
			return mapping_dict
		except Exception as ex:
			# FIXME: provide verbose error message for better debugging!!!
			my_print(u'ERROR: bad syntax in configuration file!')
			raise ex


class Multipos_mapping(object):
	"""
	this virtual property mapping contains references to multiple storage locations
	"""
	def __init__(self, ref_prop_list):
		if len(ref_prop_list) == 1:
			self._ref_prop_list = [ref_prop_list]
		else:
			self._ref_prop_list = ref_prop_list

	def get_first_prop_string(self):
		# when reading property: take the first storage location as original (while ignoring others)
		return self._ref_prop_list[0]

	def get_prop_strings(self):
		# when writing property: return all storage locations
		for item in self._ref_prop_list:
			yield item


class Mapping(object):
	"""
	contains mapping information for locating data in PSC files
	"""

	# mapping between parser object specified by string <LIT_OBJ> and real object in Parser.py
	obj_dict = {u'str': visu.psc.ParserVars.PscVar_str,
	            u'int': visu.psc.ParserVars.PscVar_int,
	            u'float': visu.psc.ParserVars.PscVar_float,
	            u'bool': visu.psc.ParserVars.PscVar_bool,
	            u'rectangle': visu.psc.ParserVars.PscVar_rectangle,
	            u'line_style': visu.psc.ParserVars.PscVar_line_style,
	            u'value_rgb_pairs': visu.psc.ParserVars.PscVar_value_rgb_pairs,
	            u'RGB': visu.psc.ParserVars.PscVar_RGB}

	def __init__(self, linemark_str = '', regex_pattern_str = '', property_obj_str = ''):
		self.linemark = unicode(linemark_str, encoding=ENCODING_FILES_PSC)
		self.regex_pattern = unicode(regex_pattern_str, encoding=ENCODING_FILES_PSC)
		self._property_obj_str = unicode(property_obj_str, encoding=ENCODING_FILES_PSC)
		self.property_obj = None


	def get_property_obj(self, line_str):
		"""
		returns a property object instance according to configuration file,
		it's constructor arguments are extracted from rawline
		"""

		# extract constructor arguments
		argument = self._extract_value(line_str)

		if DEBUGGING:
			my_print(u'Mapping.get_property_obj(): argument=' + repr(argument) + u' , self._property_obj_str=' + self._property_obj_str)

		try:
			prop_obj = Mapping.obj_dict[self._property_obj_str]

			# special treatment of rectangle..
			if self._property_obj_str == u'rectangle':
				# assumption: caller gives a list of strings
				constructor_list = map(int, argument)
				return prop_obj(*constructor_list)
			else:
				return prop_obj(argument)

		except KeyError as ex:
			my_print(u'ERROR in configuration file: get_property_obj(): "' + self._property_obj_str + u'" is not a valid property object!!!')
			raise ex


	def is_property_obj_valid(self, obj):
		"""
		Checks correct type of property object, used for correct serialization
		(we should not check too strictly, but things could go horribly wrong when wrong objects were serialized into an existing PSC rawline...)
		"""
		# FIXME: this doesn't work as expected when objects were created under '__main__' in Parser.py...
		# <class 'Parser.PscVar_RGB'> vs. <class '__main__.PscVar_RGB'>
		# ==>here is a similar problem: http://stackoverflow.com/questions/15159854/python-namespace-main-class-not-isinstance-of-package-class
		prop_obj = Mapping.obj_dict[self._property_obj_str]
		if DEBUGGING:
			my_print(u'is_property_obj_valid: prop_obj' + repr(prop_obj))
			my_print(u'is_property_obj_valid: type(obj)=' + repr(type(obj)))

		# first try: check if it's an instance of same class or subclass (ignoring problem mentioned above)
		if isinstance(obj, prop_obj):
			return True
		else:
			# second try: compare classname as fallback (caveat: doesn't work with subclasses...)
			# idea from http://stackoverflow.com/questions/510972/getting-the-class-name-of-an-instance-in-python
			# =>trial and error showed this: '__name__' and '__class__' doesn't work for both types (instances and classes)
			if DEBUGGING:
				my_print(u'type(obj).__name__: ' + str(type(obj).__name__) + u', repr(prop_obj): ' + repr(prop_obj))
			searchpattern = u'.' + type(obj).__name__ + u"'>"
			return searchpattern in repr(prop_obj)


class Mapping_split(Mapping):
	"""
	use split argument to slice PSC line
	"""
	def __init__(self, split_arg, *kargs, **kwargs):
		if DEBUGGING:
			my_print(u'constructor Mapping_split with split_arg=' + unicode(repr(split_arg)))
		self.split_arg = split_arg
		Mapping.__init__(self, *kargs, **kwargs)

	def _extract_value(self, line_str):
		"""
		returns one or more values from PSC line parts at one position or more than one positions
		=>this function expects and returns unicode strings!
		"""

		try:
			# assume request for one split part...
			positions_set = {self.split_arg}
		except TypeError:
			# ok, next assumption: request for a list of indices...
			positions_set = set(self.split_arg)

		try:
			parts = line_str.split(u';')
			ret_list = []
			for curr_pos in range(len(parts)):
				# is this one of the wanted elements?
				if curr_pos in positions_set:
					ret_list.append(parts[curr_pos])

			# when there's only one item, then we return a single value
			if len(ret_list) == 1:
				return ret_list[0]
			else:
				return ret_list
		except IndexError as ex:
			my_print(u'ERROR: wrong positions of split parts in configuration file for linemark "' + self.linemark + u'"')
			raise ex

	def update_value(self, line_str, obj):
		"""
		returns complete PSC line updated with given obj at specific position
		=>this function expects and returns unicode strings!
		"""

		# prevent serialization of wrong objects into PSC rawline...
		# FIXME: can we do this in a cleaner way? (=>we should allow ducktyping...)
		assert self.is_property_obj_valid(obj), u'ERROR: update_value expected object of type "' + repr(Mapping.obj_dict[self._property_obj_str]) + u'", but got type "' + repr(type(obj)) + '"!'

		try:
			# assume request for one split part...
			positions_set = {self.split_arg}
			is_one_value = True
		except TypeError:
			# ok, next assumption: request for a list of indices...
			positions_set = set(self.split_arg)
			is_one_value = False

		try:
			parts = line_str.split(u';')
			ret_list = []
			value_index = -1
			for curr_pos in range(len(parts)):
				if curr_pos in positions_set:
					# this is position where given obj is stored
					try:
						if is_one_value:
							uni_val = obj.get_serialized()
						else:
							value_index = value_index + 1
							uni_val = obj.get_serialized()[value_index]
						ret_list.append(uni_val)
					except AttributeError as ex:
						my_print(u'ERROR: update_value() expects an PscVariable or compatible object, but we got type "' + repr(type(obj)) + u'"!')
						raise ex
				else:
					# leave other positions unchanged
					ret_list.append(parts[curr_pos])
			return u';'.join(ret_list)
		except IndexError as ex:
			my_print(u'ERROR: wrong positions of split parts in configuration file for linemark "' + self.linemark + u'"')
			raise ex

class Mapping_split_listobject(Mapping):
	"""
	use split arguments to fill CSV-parts of PSC line into a variable-length python object,
	containing a list of tuples
	(e.g. used in "foreground color initialisation" with mapping N-colors to N-values of a DMS-key)
	-first element is index where number of tuples is stored
	-second element is start-index where whole Python object structure starts
	-third element is length per tuple)
	"""
	def __init__(self, split_arg, *kargs, **kwargs):
		if DEBUGGING:
			my_print(u'constructor Mapping_split_objects with split_arg=' + unicode(repr(split_arg)))
		assert len(split_arg) == 3, u'Mapping_split_listobject(): wrong syntax in configfile: split_arg=' + unicode(repr(split_arg) + ' [len() is: ' + str(len(split_arg)) + ']')
		self._idx_noftuples = int(split_arg[0])
		self._startindex = int(split_arg[1])
		self._tuple_length = int(split_arg[2])
		Mapping.__init__(self, *kargs, **kwargs)


	def _extract_value(self, line_str):
		"""
		returns list of elements from PSC line parts (used later for assembling of python object)
		=>we don't care about tuples, the python object constructor has to slice them itself!
		=>this function expects and returns unicode strings!
		"""
		try:
			parts = line_str.split(u';')
			noftuples = int(parts[self._idx_noftuples])
			curr_elem_list = []
			for obj_num in range(noftuples):
				# assembling list of elements
				idx_start = self._startindex + obj_num * self._tuple_length
				idx_stop = idx_start + self._tuple_length
				curr_elem_list = curr_elem_list + parts[idx_start:idx_stop]
				#my_print(u'Mapping_split_listobject._extract_value(): noftuples=' + str(noftuples) + u', idx_start=' + str(idx_start) + u', idx_stop=' + str(idx_stop) + u'"')
			#my_print(u'Mapping_split_listobject._extract_value(): returns "' + repr(curr_elem_list) + u'"')
			return curr_elem_list
		except IndexError as ex:
			my_print(u'ERROR: wrong positions of split parts for linemark "' + self.linemark + u'" (error in configuration file or PSC file)')
			raise ex

	def update_value(self, line_str, obj):
		"""
		returns complete PSC line updated with given object at specific position
		=>this function expects and returns unicode strings!
		"""

		# prevent serialization of wrong objects into PSC rawline...
		# FIXME: can we do this in a cleaner way? (=>we should allow ducktyping...)
		assert self.is_property_obj_valid(obj), u'ERROR: update_value expected object of type "' + repr(Mapping.obj_dict[self._property_obj_str]) + u'", but got type "' + repr(type(obj)) + '"!'


		try:
			parts = line_str.split(u';')

			try:
				elem_list = obj.get_serialized()
			except AttributeError as ex:
				my_print(u'ERROR: update_value() expects an PscVariable or compatible object, but we got type "' + repr(type(obj)) + u'"!')
				raise ex
			curr_nof_objs = len(elem_list) / self._tuple_length
			# updating field with number of tuples
			parts[self._noftuples] = str(curr_nof_objs)

			# concatenation of all parts: first cut the current lineparts, then append variable-length element list
			# =>we assume that the PSC-line ends after variable-length element list!
			ret_list = parts[self._startindex + 1] + elem_list
			return u';'.join(ret_list)
		except IndexError as ex:
			my_print(u'ERROR: wrong positions of split parts for linemark "' + self.linemark + u'" (error in configuration file or PSC file)')
			raise ex


class Mapping_split_bit(Mapping):
	"""
	use split_bit argument list to slice PSC line:
	-first element is position of bitfield in CSV
	-second element is position of bit in bitfield
	"""
	def __init__(self, split_bit_arg, *kargs, **kwargs):
		if DEBUGGING:
			my_print(u'constructor Mapping_split with split_arg=' + unicode(repr(split_bit_arg)))
		self.split_pos = split_bit_arg[0]
		self.bit_pos = split_bit_arg[1]
		Mapping.__init__(self, *kargs, **kwargs)

	def _extract_value(self, line_str):
		"""
		returns a bit from a bitfield, which is embedded into one PSC line part
		(parameter "inverse" returns everything except this value(s), it's used for reassembling/serialization)
		=>this function expects and returns unicode strings!
		"""

		try:
			parts = line_str.split(u';')
			bitfield = int(parts[self.split_pos])

			# test one bit in this integer
			# example from https://wiki.python.org/moin/BitManipulation
			if DEBUGGING:
				my_print(u'Mapping_split_bit._extract_value(): bitfield=' + unicode(bitfield) + u', self.bit_pos=' + unicode(self.bit_pos))
			mask = 1 << self.bit_pos
			return bool(bitfield & mask)
		except IndexError as ex:
			my_print(u'ERROR: wrong position of split part in configuration file for linemark "' + self.linemark + u'"')
			raise ex


	def update_value(self, line_str, obj):
		"""
		returns complete PSC line updated with given value at specific position
		=>this function expects and returns unicode strings!
		"""

		# prevent serialization of wrong objects into PSC rawline...
		# FIXME: can we do this in a cleaner way? (=>we should allow ducktyping...)
		assert self.is_property_obj_valid(obj), u'ERROR: update_value expected object of type "' + repr(Mapping.obj_dict[self._property_obj_str]) + u'", but got type "' + repr(type(obj)) + '"!'

		try:
			parts = line_str.split(u';')
			bitfield = int(parts[self.split_pos])

			# set or clear bit in this integer according to obj
			# example from https://wiki.python.org/moin/BitManipulation
			new_bitfield = 0
			try:
				if obj.get_value():
					# set bit
					mask = 1 << self.bit_pos
					new_bitfield = bitfield | mask
				else:
					mask = ~(1 << self.bit_pos)
					new_bitfield = bitfield & mask
			except AttributeError as ex:
				my_print(u'ERROR: update_value() expects an PscVariable or compatible object, but we got type "' + repr(type(obj)) + u'"!')
				raise ex
			# reassemble CSV
			parts[self.split_pos] = unicode(new_bitfield)
			if DEBUGGING:
				my_print(u'Mapping_split_bit._update_value(): bitfield=' + unicode(bitfield) + u', self.bit_pos=' + unicode(self.bit_pos) + u', obj=' + repr(obj) + u', new_bitfield=' + unicode(new_bitfield))
			return u';'.join(parts)
		except IndexError as ex:
			my_print(u'ERROR: wrong position of split part in configuration file for linemark "' + self.linemark + u'"')
			raise ex


class Mapping_regex(Mapping):
	"""
	use Regex argument to slice PSC line
	=>this has to be a regex pattern for "match()" method https://docs.python.org/2/library/re.html#search-vs-match

	=>regex match object has to contain three groups: <before value>, <value itself>, <after value>
	( https://docs.python.org/2/library/re.html#match-objects )
	"""
	def __init__(self, regex_pattern_str, *kargs, **kwargs):
		self.regex_pattern_str = regex_pattern_str
		self._regex_obj = re.compile(self.regex_pattern_str)
		Mapping.__init__(self, *kargs, **kwargs)

	def _extract_value(self, line_str):
		"""
		returns a value in a PSC line according to its regex pattern
		"""
		try:
			match = self._regex_obj.match(line_str)
			# the middle matching group must be value
			return match.group(2)
		except IndexError as ex:
			my_print(u'ERROR: wrong regex string in configuration file for linemark "' + self.linemark + u'"')
			raise ex


	def update_value(self, line_str, obj):
		"""
		returns complete PSC line updated with given obj at specific position
		=>this function expects and returns unicode strings!
		"""

		# prevent serialization of wrong objects into PSC rawline...
		# FIXME: can we do this in a cleaner way? (=>we should allow ducktyping...)
		assert self.is_property_obj_valid(obj), u'ERROR: update_value expected object of type "' + repr(Mapping.obj_dict[self._property_obj_str]) + u'", but got type "' + repr(type(obj)) + '"!'

		try:
			match = self._regex_obj.match(line_str)
			try:
				uni_val = obj.get_serialized()
			except AttributeError as ex:
				my_print(u'ERROR: update_value() expects an PscVariable or compatible object, but we got type "' + repr(type(obj)) + u'"!')
				raise ex
			# replacing middle matching group
			return match.group(1) + uni_val + match.group(3)
		except IndexError as ex:
			my_print(u'ERROR: wrong regex string in configuration file for linemark "' + self.linemark + u'"')
			raise ex


def main(argv=None):
	get_encoding()

	# write configfile for first time
	# WARNING: this could overwrite your manual changes!!!
	write_raw_configfile(u'config.yml')

	with open(u"config.yml", u'r') as ymlfile:
		my_print(unicode(repr(yaml.load(ymlfile)), encoding=ENCODING_FILES_PSC))

	return 0        # success


if __name__ == '__main__':
	status = main()
	# sys.exit(status)