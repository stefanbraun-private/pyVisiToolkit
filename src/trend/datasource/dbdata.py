#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.dbdata.py


DBData()
a structure used in trendfiles on harddisk (*.hdb) and as result when retrieving history-data from PDBS service.

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import ctypes
import struct
import time
import os
import yaml
import datetime

DBDATA_STATUSBITS_YAML = r'c:\PyVisiToolkit_DBData_Statusbits.yml'
statusbits_namelist = []
statusbits_unnamedlist = []


def get_statusbits_class():
	# class-factory
	# default access to status bits ("bit0", "bit1", etc., ctypes.c_ulong means 32 bits)
	# format is _fields_ = [("bit0", ctypes.c_ulong, 1), ("bit1", ctypes.c_ulong, 1), ...]
	# => example: https://docs.python.org/2/library/ctypes.html#bit-fields-in-structures-and-unions
	fields_list = []
	global statusbits_unnamedlist
	if not statusbits_unnamedlist:
		# create list with unnamed bits only once
		statusbits_unnamedlist = [u'bit' + str(x) for x in range(32)]

	for bit in statusbits_unnamedlist:
		curr_tuple = (bit, ctypes.c_ulong, 1)
		fields_list.append(curr_tuple)

	class Status_bits(ctypes.LittleEndianStructure):
		# interpretation of trenddata status
		# (based on code from https://wiki.python.org/moin/BitManipulation )
		_fields_ = fields_list

	return Status_bits


def get_named_statusbits_class():
	# class-factory
	# using correct meaning of statusbits from configuration file (read it only once)
	global statusbits_namelist
	if not statusbits_namelist:
		with open(DBDATA_STATUSBITS_YAML, u'r') as ymlfile:
			names_dict = yaml.load(ymlfile)

		# lists in YAML are always unsorted... =>by using a dictionary we can force sorting of the bit names
		# unnamedlist contains 'bit0', 'bit1', ....
		# =>these are the keys for our YAML-dictionary, then we get same sorting in both lists
		global statusbits_unnamedlist
		for bitname in statusbits_unnamedlist:
			statusbits_namelist.append(names_dict[bitname])

	fields_list = []
	for bit in statusbits_namelist:
		curr_tuple = (bit, ctypes.c_ulong, 1)
		fields_list.append(curr_tuple)

	class Named_status_bits(ctypes.LittleEndianStructure):
		_fields_ = fields_list

	return Named_status_bits



def get_status_class():
	'''
	class-factory for meaning of DBData status bits
	=>correct meaning of statusbits is available when DBDATA_STATUSBITS_YAML exists,
	  direct access to every bit is always possible with "bit<x>" (0 <= x <= 15)
	'''

	curr_fields = [
        ("unnamed", get_statusbits_class()),
        ("asLong", ctypes.c_ulong)
    ]
	curr_anonymous = ["unnamed"]

	if os.path.exists(DBDATA_STATUSBITS_YAML):
		# Asenta-internal knowledge of status bits is available... ->including it [MST Support - Ticket #13023] (request Feedback) PBDS: getData // MST-Ticket #13023
		curr_fields.append(("named", get_named_statusbits_class()))
		curr_anonymous.append("named")

	class Status(ctypes.Union):
		_fields_ = curr_fields
		_anonymous_ = curr_anonymous

		global statusbits_namelist
		@classmethod
		def get_statusbits_namelist(cls):
			return statusbits_namelist

		global statusbits_unnamedlist
		@classmethod
		def get_statusbits_unnamedlist(cls):
			return statusbits_unnamedlist

	return Status


class DBData(ctypes.Structure):
	# Trenddata struct: [time (=>32bit unsigned integer), value (=>32bit IEEE float), status (=>32bit bitmap, interpret as unsigned integer)], every element is 32bit
	# https://docs.python.org/2/library/struct.html#format-characters
	STRUCT_FORMAT = 'IfI'

	# based on http://stackoverflow.com/questions/1444159/how-to-read-a-structure-containing-an-array-using-pythons-ctypes-and-readinto
	_fields_ = [
		("timestamp", ctypes.c_uint),
		("value", ctypes.c_float),
		("status", ctypes.c_uint)]

	# hold reference to statusbit class for better performance
	# FIXME: first time call to DBData.Statusbit_class().get_statusbits_namelist() crashes when no DBData constructor created "Statusbit_class"...
	# FIXME: =>how can we do this in a cleaner way with better incapsulation?
	Statusbit_class = None

	@classmethod
	def load_statusbit_class(cls):
		if not cls.Statusbit_class:
			cls.Statusbit_class = get_status_class()

	def __init__(self, *kargs, **kwargs):
		ctypes.Structure.__init__(self, *kargs, **kwargs)
		DBData.load_statusbit_class()

	def __str__(self):
		# a simple string prasentation
		return 'timestamp=' + str(self.timestamp) + '\tvalue=' + str(self.value) + '\tstatus=' + str(
			self.status) + ' (' + self.getStatusBitsString() + ')'

	def getValue(self, offset=0, corrFactor=1.0):
		return corrFactor * (self.value + float(offset))

	def getTimestamp(self):
		return self.timestamp

	def getStatus(self):
		return self.status

	def get_statusbits_set(self):
		curr_bits = DBData.Statusbit_class()
		curr_bits.asLong = self.status

		# generate a set containing only active statusbits
		# (if available insert named and unnamed statusbits)
		# =>idea from http://stackoverflow.com/questions/3789372/python-can-we-convert-a-ctypes-structure-to-a-dictionary
		myset = set()

		allbits_list = []
		allbits_list.extend(curr_bits.get_statusbits_namelist())
		allbits_list.extend(curr_bits.get_statusbits_unnamedlist())
		for bit_name in allbits_list:
			if getattr(curr_bits, bit_name):
				myset.add(bit_name)

		return myset

	def getStatusBitsString(self):
		return ', '.join(self.get_statusbits_set())


	# allow using DBData objects in set():
	# =>we need a hash value over all fields to get same hash for same trenddata element!
	# example from http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
	def __hash__(self):
		"""Override the default hash behavior (that returns the id or the object)"""
		return hash(tuple(sorted(self.timestamp, self.value, self.status)))


class HighLevelDBData(DBData):
	"""
	Interpret the raw data in DBData as datetime-object and value in a datatype
	https://docs.python.org/2/library/datetime.html
	"""
	def __init__(self, *kargs, **kwargs):
		DBData.__init__(*kargs, **kwargs)

	def get_datetime(self):
		# hints: https://docs.python.org/2/library/datetime.html#datetime.datetime
		return datetime.datetime.fromtimestamp(self.timestamp)

	def get_value_as_boolean(self):
		return self.value > 0.0

	def get_value_as_int(self):
		return int(self.value)

	def get_value_as_float(self):
		return self.value