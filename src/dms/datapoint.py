#!/usr/bin/env python
# encoding: utf-8
"""
dms.datapoint.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

DEBUGGING = True


class Dp(object):

	# access rights in DMS
	# READ_WRITE = '\x02'
	# READ_ONLY = '\x04' (<=this is assumption!)
	# REMANENT = '\x08'
	# CONFIGURATION = '\x80' (<=based on Reverse-Engineering!)
	READ_WRITE  = 0x02
	READ_ONLY   = 0x04
	REMANENT    = 0x08
	CONFIG      = 0x80

	def __init__(self):
		# "access rights" in DMS:
		#       READ_ONLY Other processes can't write values.       (currently 'RO' in set)
		#       READ_WRITE Every process can write values.          (currently 'RW' in set)
		#       REMANENT Only remanent values are stored on disk    (currently 'REM' in set)
		self._rights = 0

	def is_readonly(self):
		mask = Dp.READ_ONLY
		return bool(self._rights & mask)

	def is_readwrite(self):
		mask = Dp.READ_WRITE
		return bool(self._rights & mask)

	def is_remanent(self):
		mask = Dp.REMANENT
		return bool(self._rights & mask)

	def is_configuration(self):
		mask = Dp.CONFIG
		return bool(self._rights & mask)

	def set_rights(self, rights_int):
		"""
		call this function with raw value from Dmspipe
		or with integer built with bitwise manipulations (e.g. Dp.READ_WRITE | Dp.REMANENT)
		"""
		mask = rights_int
		self._rights = self._rights | mask
		if DEBUGGING:
			print('access rights are now ' + self.get_rights_string())

	def clear_rights(self, rights_int):
		"""
		call this function with raw value from Dmspipe
		or with integer built with bitwise manipulations (e.g. Dp.READ_WRITE | Dp.REMANENT)
		"""
		# complement in Python ( https://wiki.python.org/moin/BitwiseOperators )
		mask = ~rights_int
		self._rights = self._rights & mask
		if DEBUGGING:
			print('access rights are now ' + self.get_rights_string())

	def get_rights_string(self):
		curr_list = []
		if self.is_readonly():
			curr_list.append('READ_ONLY')
		if self.is_readwrite():
			curr_list.append('READ_WRITE')
		if self.is_remanent():
			curr_list.append('REMANENT')
		if self.is_configuration():
			curr_list.append('CONFIGURATION')
		return ','.join(curr_list)

	def get_value(self):
		return self.value


class Dp_NONE(Dp):
	"""
	No datapoint found
	"""
	def __init__(self, value=None):
		Dp.__init__(self)
		self.value = None


class Dp_BIT(Dp):
	"""
	Boolean
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = bool(value)


class Dp_BYS(Dp):
	"""
	Byte signed
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_BYU(Dp):
	"""
	Byte unsigned
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_WOS(Dp):
	"""
	Word signed
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_WOU(Dp):
	"""
	Word unsigned
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_DWS(Dp):
	"""
	Double Word signed
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_DWU(Dp):
	"""
	Double Word unsigned
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = int(value)


class Dp_FLT(Dp):
	"""
	Double (floating point value)
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = float(value)


class Dp_STR(Dp):
	"""
	String (max. MAX_NAME characters)
	"""
	def __init__(self, value):
		Dp.__init__(self)
		self.value = str(value)


class Dms_dp_Factory(object):
	# example of "factory" pattern: http://stackoverflow.com/questions/21025959/factory-design-pattern
	dp_types_dict = { 'NONE':   Dp_NONE,
					'BIT':	Dp_BIT,
					'BYS':	Dp_BYS,
					'WOS':	Dp_WOS,
					'DWS':	Dp_DWS,
					'BYU':	Dp_BYU,
					'WOU':	Dp_WOU,
					'DWU':	Dp_DWU,
					'FLT':	Dp_FLT,
					'STR':	Dp_STR,
				}
	# numeric DMS types: from ProMoS documentation, based on example in Delphi, but Trial-and-Error revealed this relation:
	dp_numeric_types_dict = { 0:   'NONE',
					1:	'BIT',
					2:	'BYS',
					3:	'WOS',
					4:	'DWS',
					5:	'BYU',
					6:	'WOU',
					7:	'DWU',
					8:	'FLT',
					9:	'STR',
				}

	dp_string_types_dict = { 'NONE':   0,
					'BIT':	1,
					'BYS':	2,
					'WOS':	3,
					'DWS':	4,
					'BYU':	5,
					'WOU':	6,
					'DWU':	7,
					'FLT':	8,
					'STR':	9,
				}

	@classmethod
	def new_dp_by_str(cls, type_str, value):
		assert type_str in cls.dp_types_dict, "type_str is not an valid DMS datatype: %r" % type_str
		new_dp = cls.dp_types_dict[type_str](value)
		return new_dp

	@classmethod
	def new_dp_by_int(cls, type_int, value):
		assert type_int in cls.dp_numeric_types_dict, "type_int is not an valid DMS datatype: %r" % type_int
		type_str = cls.dp_numeric_types_dict[type_int]
		new_dp = cls.dp_types_dict[type_str](value)
		return new_dp

	@classmethod
	def get_dp_numeric_type_by_instance(cls, dp_obj):
		"""
		return numeric DMS datapoint type
		"""
		for type_int, type_str in cls.dp_numeric_types_dict.items():
			if type(dp_obj) == type(cls.new_dp_by_str(type_str, 0)):
				return type_int

	@classmethod
	def get_dp_string_type_by_instance(cls, dp_obj):
		"""
		return three-letter-string DMS datapoint type
		"""
		for type_int, type_str in cls.dp_numeric_types_dict.items():
			if type(dp_obj) == type(cls.new_dp_by_str(type_str, 0)):
				return type_str


def main(argv=None):

	return 0        # success


if __name__ == '__main__':
	status = main()