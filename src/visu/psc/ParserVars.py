#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.ParserVars.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


class PscVariable(object):
	'''
	Conversion from and to python variables into it's representation in PSC files
	'''
	def set_value(self, new_val):
		self._value = new_val

	def get_value(self):
		return self._value


	# allow comparison of PscVariable objects with their python counterpart
	# based on example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		return NotImplemented

	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented


	def __hash__(self):
		"""Override the default hash behavior (that returns the id of the object)
		=>we say objects with same value are same objects"""
		return hash(self._value)

	def __repr__(self):
		return unicode(self._value)

	def __str__(self):
		return unicode(self._value)


class PscVar_str(PscVariable):
	'''
	String representation in PSC files
	'''
	def __init__(self, unicode_string=u''):
		self._value = unicode_string

	def get_serialized(self):
		# return format used in PSC file
		# FIXME: should we encode it here into ENCODING_FILES_PSC, or only in file writing?
		return unicode(self._value)


class PscVar_int(PscVariable):
	'''
	Integer representation in PSC files
	'''
	def __init__(self, int_val):
		self._value = int(int_val)

	def get_serialized(self):
		# return format used in PSC file
		# turn into string, then into unicode
		return unicode(self._value)


class PscVar_float(PscVariable):
	'''
	Float representation in PSC files
	=>it has always 6 decimals
	'''
	def __init__(self, float_val=u'0.000000'):
		self._value = float(float_val)

	def get_serialized(self):
		# return format used in PSC file
		# help from http://stackoverflow.com/questions/455612/limiting-floats-to-two-decimal-points
		return u'{0:.2f}'.format(self._value)


class PscVar_bool(PscVariable):
	'''
	Boolean representation in PSC files
	=>0 means False, 1 means True
	'''
	def __init__(self, bool_as_str=u'0'):
		self.set_value(bool_as_str)

	def get_serialized(self):
		# return format used in PSC file
		if self._value:
			return u'1'
		else:
			return u'0'

	def set_value(self, bool_as_str):
		if bool_as_str in [u'1']:
			self._value = True
		else:
			self._value = False

	def get_value(self):
		return self._value


class PscVar_point(PscVariable):
	def __init__(self, x_int=0, y_int=0):
		self.x = 0
		self.y = 0
		self.set_value((x_int, y_int))

	def set_value(self, new_val):
		self.x = int(new_val[0])
		self.y = int(new_val[1])

	def get_value(self):
		return self.x, self.y

	def __repr__(self):
		return u'(' + unicode(self.x) + u',' + unicode(self.y) + u')'


	# allow comparison of PscVar_point objects
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		return NotImplemented

	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented


	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		return hash(tuple(sorted(self.__dict__.items())))


class PscVar_rectangle(PscVariable):
	"""
	representation of an area by two points
	"""
	def __init__(self, x_left_int=0, y_up_int=0, x_right_int=0, y_down_int=0):
		assert x_left_int <= x_right_int, u'right coordinate is expected to be equal or greater than left coordinate'
		assert y_up_int <= y_down_int, u'higher coordinate is expected to be equal or less than bottom coordinate'
		self._point1 = PscVar_point(x_left_int, y_up_int)
		self._point2 = PscVar_point(x_right_int, y_down_int)

	def is_point_in_area(self, x_int, y_int):
		return (self._point1.x <= x_int <= self._point2.x) and (self._point1.y <= y_int <= self._point2.y)

	def get_coordinates(self):
		return self._point1.x, self._point1.y, self._point2.x, self._point2.y

	def get_value(self):
		return self._point1, self._point2

	def set_value(self, new_pos):
		point1, point2 = new_pos
		assert isinstance(point1, PscVar_point), u'instance of PscVar_point expected for argument <point1>!'
		assert isinstance(point2, PscVar_point), u'instance of PscVar_point expected for argument <point2>!'
		self._point1 = point1
		self._point2 = point2

	def get_height(self):
		# always return a positive height
		return abs(self._point2.y - self._point1.y)

	def get_width(self):
		# always return a positive width
		return abs(self._point2.x - self._point1.x)

	def get_serialized(self):
		# return format used in PSC file
		# (tuple of four integers)
		my_tuple = (self._point1.x, self._point1.y, self._point2.x, self._point2.y)
		return map(unicode, my_tuple)

	def __repr__(self):
		return u'[' + repr(self._point1) + u',' + repr(self._point2) + u']'


	# allow comparison of PscVar_rectangle objects
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			## comparing only internal int-values is enough (don't care for any other attributes)
			return self.get_coordinates() == other.get_coordinates()
		# return self.__dict__ == other.__dict__
		return NotImplemented


	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented


	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		## hashing all coordinate points is enough (don't care for any other attributes)
		return hash(self.get_coordinates())
		# return hash(tuple(sorted(self.__dict__.items())))


class PscVar_value_rgb_pairs(PscVariable):
	def __init__(self, elem_list=[]):
		"""
		Used in initialisations as dynamic foreground-color mappings between values of one DMS-keys and their RGB-color counterpart
		=>excepted: list of all value_float, rgb_int values (alternated)
		"""
		assert len(elem_list) % 2 == 0, u'PscVar_value_rgb_pairs() expects a list of all value_float / rgb_int values (alternated appearance)'
		self._pairs_list = []
		value_float = None
		rgb_int = None
		# conversion of list into list of tuples:
		# and http://stackoverflow.com/questions/4647050/collect-every-pair-of-elements-from-a-list-into-tuples-in-python
		for elem_tuple in zip(elem_list[0::2], elem_list[1::2]):
			value_float = float(elem_tuple[0])
			rgb_int = int(elem_tuple[1])
			mytuple = (value_float, PscVar_RGB(rgb_int))
			#my_print(u'constructor of PscVar_value_rgb_pairs(): mytuple=' + repr(mytuple))
			self._pairs_list.append(mytuple)

	def get_value(self):
		# return a deep-copy of internal list (avoid external corruption of this list)
		return list(self._pairs_list)

	def set_value(self, new_pairs_list):
		# insert deep-copy to internal list (avoid external corruption of this list)
		# doing minimal check of new list (FIXME: same code as in __init__()... combine it!)
		for elem_tuple in new_pairs_list:
			value_float = float(elem_tuple[0])
			rgb_int = int(elem_tuple[1])
			mytuple = (value_float, PscVar_RGB(rgb_int))
			self._pairs_list.append(mytuple)

	def __repr__(self):
		elements_list = []
		for value_float, rgb in self._pairs_list:
			assign_list = []
			assign_list.append(repr(value_float))
			assign_list.append(u'=>')
			assign_list.append(repr(rgb))
			elements_list.append(u''.join(assign_list))
		return u'[' + u'; '.join(elements_list) + u']'

	def get_serialized(self):
		# return format used in PSC file
		# (tuple of two values)
		elements_list = []
		for value_float, rgb in self._pairs_list:
			elements_list.append(u'{0:.2f}'.format(value_float))
			elements_list.append(rgb.get_serialized())
		return elements_list

	# allow comparison of PscVar_value_rgb_pairs objects
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			# comparing internal list with deep comparison (don't care for any other attributes)
			# =>simplification: we compare strings generated by __repr__()
			return repr(self) == repr(other)
		return NotImplemented


	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented


	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		# just using internal list (don't care for any other attributes)
		# =>simplification: build hash of string generated by __repr__()
		return hash(repr(self))


class PscVar_line_style(PscVariable):
	SOLID = 0
	DASHED = 1
	DOTTED = 2
	DASH_DOT = 3
	DASH_DOT_DOT = 4

	def __init__(self, style=0):
		self._style_int = int(style)

	def get_value(self):
		return self._style_int

	def set_value(self, new_style):
		self.set_style(new_style)

	def set_style(self, arg):
		try:
			new_val = int(arg)
			assert (new_val >= 0) and (new_val <= 4), str(new_val) + u' is an unknown line style'
			self._style_int = int(arg)
		except ValueError:
			if arg in [u"SOLID", u"solid"]:
				self._style_int = PscVar_line_style.SOLID
			elif arg in [u"DASHED", u"dashed"]:
				self._style_int = PscVar_line_style.DASHED
			elif arg in [u"DOTTED", u"dotted"]:
				self._style_int = PscVar_line_style.DOTTED
			elif arg in [u"DASH_DOT", u"dash_dot"]:
				self._style_int = PscVar_line_style.DASH_DOT
			elif arg in [u"DASH_DOT_DOT", u"dash_dot_dot"]:
				self._style_int = PscVar_line_style.DASH_DOT_DOT
			else:
				raise ValueError(repr(arg) + u' is an unknown line style')

	def get_serialized(self):
		# return format used in PSC file
		return unicode(self._style_int)

	def __repr__(self):
		return self.get_serialized()

	# allow comparison of PscVar_line_style objects
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			## comparing only internal int-value is enough (don't care for any other attributes)
			return self._style_int == other._style_int
		# return self.__dict__ == other.__dict__
		return NotImplemented


	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented

	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		## just returning our internal RGB value is enough (don't care for any other attributes)
		return self._style_int
		# return hash(tuple(sorted(self.__dict__.items())))


class PscVar_RGB(PscVariable):
	# FIXME: how to simplify handling of color RGB values? Which functionality is needed?
	# we use usualy Windows default colormap as shown in MS Paint
	# (how to get color of any pixel in an image: http://www.bustatech.com/simple-way-to-get-rgb-value-of-the-color-on-your-screen/ )
	#
	# Visi+ RGB values: red = 255, blue = 0xFF0000, ... =>colors: 0xBBGGRR (attention to the ordering)
	#
	# Python code for 551 named color constants:
	# https://www.webucator.com/blog/2015/03/python-color-constants-module/
	# useful: https://wiki.python.org/moin/BitManipulation

	def __init__(self, rgb_val=u'#000000'):
		red_int, green_int, blue_int = 0, 0, 0
		if isinstance(rgb_val, int):
			self._rgb_int = rgb_val
		else:
			try:
				if rgb_val[0] == u'#':
					# assume HTML-colorcode as 3x8bit hexstring '#RRGGBB'
					assert len(rgb_val) == 7
					red_int = int(u'0x' + rgb_val[1:3], 16)
					green_int = int(u'0x' + rgb_val[3:5], 16)
					blue_int = int(u'0x' + rgb_val[5:7], 16)
					self._rgb_int = (blue_int << 16) + (green_int << 8) + red_int
				elif len(rgb_val) == 3 and rgb_val != str(rgb_val):
					# assume color definition as tuple of (red_int, green_int, blue_int) with values between 0 and 255
					self.set_value(rgb_val)
				else:
					# assume color definition in Visi+: RGB, 8bit per color, hexcode 0xRRGGBB is represented as integer
					self._rgb_int = int(rgb_val)
			except:
				#my_print(u'PscVar_RGB() constructor was called with argument "' + unicode(repr(rgb_val)) + u'"')
				raise ValueError
		assert red_int >= 0 and red_int <= 255
		assert green_int >= 0 and green_int <= 255
		assert blue_int >= 0 and blue_int <= 255
		assert self._rgb_int >= 0 and self._rgb_int <= 0xffffff

	def get_value(self):
		return self.get_tuple()

	def set_value(self, new_color_tuple):
		# assume color definition as tuple of (red_int, green_int, blue_int) with values between 0 and 255
		red_int, green_int, blue_int = map(int, new_color_tuple)
		self._rgb_int = (blue_int << 16) + (green_int << 8) + red_int

	def get_tuple(self):
		mask_red = int(b'0x0000ff', 16)
		value_red = self._rgb_int & mask_red

		mask_green = int(b'0x00ff00', 16)
		value_green = (self._rgb_int & mask_green) >> 8

		mask_blue = int(b'0xff0000', 16)
		value_blue = (self._rgb_int & mask_blue) >> 16

		return value_red, value_green, value_blue

	def get_int(self):
		return self._rgb_int

	def get_html(self):
		# return HTML-colorcode as string '#RRGGBB'
		# string filled to a fixed length with zeros
		# based on http://stackoverflow.com/questions/5676646/fill-out-a-python-string-with-spaces
		hex_string_parts = []
		for part in self.get_tuple():
			hex_string = hex(part).upper()[2:]
			hex_string_parts.append(hex_string.rjust(2, '0'))

		# string filled to a fixed length with zeros
		# based on http://stackoverflow.com/questions/5676646/fill-out-a-python-string-with-spaces
		return u'#' + u''.join(hex_string_parts)

	def get_serialized(self):
		# return format used in PSC file
		return unicode(self._rgb_int)

	def __repr__(self):
		val_r, val_g, val_b = self.get_tuple()
		return u'PscVar_RGB(' + u','.join([unicode(val_r), unicode(val_g), unicode(val_b)]) + u')'

	# allow comparison of PscVar_RGB objects
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __eq__(self, other):
		"""Override the default Equals behavior"""
		if isinstance(other, self.__class__):
			## comparing only internal RGB-value is enough (don't care for any other attributes)
			return self._rgb_int == other._rgb_int
			#return self.__dict__ == other.__dict__
		return NotImplemented

	def __ne__(self, other):
		"""Define a non-equality test"""
		if isinstance(other, self.__class__):
			return not self.__eq__(other)
		return NotImplemented

	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		## just returning our internal RGB value is enough (don't care for any other attributes)
		return self._rgb_int
		#return hash(tuple(sorted(self.__dict__.items())))