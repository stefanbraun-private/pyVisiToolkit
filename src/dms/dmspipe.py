#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmspipe.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

# Windows Errors:
# https://www.rpi.edu/dept/cis/software/g77-mingw32/include/winerror.h
#
# Windows datatypes:
# https://en.wikibooks.org/wiki/Windows_Programming/Handles_and_Data_Types

import ctypes
import os
import io
import time
import decimal
import dms.datapoint
import misc.visi_binaries

DEBUGGING = True
ENCODING = 'windows-1252'


class DMS_STRING(ctypes.Structure):
	# loosely based on http://stackoverflow.com/questions/5082753/how-do-i-build-a-python-string-from-a-ctype-struct
	# http://stackoverflow.com/questions/10006610/sending-stucture-containing-mutable-string-to-c-from-python-thru-ctypes/10007443#10007443
	# but ignoring handling of strings containing NULL characters inside...

	MAXLENGTH = 81  #  (max. string length in DMS: 80 characters + NULL character)

	def __init__(self, bytestring='\x00'):
		ctypes.Structure.__init__(self)
		size = len(bytestring)
		if size > DMS_STRING.MAXLENGTH:
			raise ValueError("bytestring %s too large for buffer", repr(bytestring))
		ctypes.memmove(self.buffer, bytestring, size)

	## both of following variants works... I thought that an array of "ctypes.c_char" is NOT mutable, because of mapping to immutable python string objects?!?
	#_fields_ = [("buffer",  ctypes.c_char * MAXLENGTH)]   # fixed length string

	# def to_string(self):
	# 	return str(self.buffer)

	_fields_ = [("buffer",  ctypes.c_ubyte * MAXLENGTH)]   # fixed length string

	def to_string(self):
		# "ctypes.string_at()" without parameter "size": conversion of NULL-terminated bytestring into python string
		return ctypes.string_at(ctypes.byref(self))


class _VALUE_TYPE(ctypes.Structure):
	# our DMS message structure as showed by analysis of returned values (reverse-engineering)... ProMoS documentation is outdated in this part...
	# (ProMoS documentation has other order for "val_WOU" and "val_BYU")
	_fields_ = [("val_BIT",  ctypes.c_bool),    # bit
	            ("val_BYS",  ctypes.c_byte),    # signed BYTE
				("val_WOS",  ctypes.c_int16),   # signed WORD (in Windows API: 16bit)
				("val_DWS",  ctypes.c_int32),    # signed DWORD (in Windows API: 32bit)
				("val_BYU",  ctypes.c_ubyte),   # unsigned BYTE
				("reserved",  ctypes.c_ubyte),   # FIXME: experiments showed an empty byte between other values... Why? What's in there?
				("val_WOU",  ctypes.c_uint16),   # unsigned WORD(in Windows API: 16bit)
				("val_DWU",  ctypes.c_uint32),   # unsigned DWORD (in Windows API: 32bit)
				("val_FLT",  ctypes.c_double),   # float (=32bit), double (=64bit)
												# (proven by experiment... makes sense, "DMS_WriteFLT" works only when called with a double instead of float...
	                                            # But "DMS_ReadFLT" returns a DECIMAL in a NULL terminated string...?!?)
				("val_STR",  DMS_STRING)]   # string (max. length in DMS: 80 characters)


class _MESSAGE_FIELDS(ctypes.Structure):
	"""
	our DMS message structure as showed by analysis of returned values (reverse-engineering)... ProMoS documentation is outdated in this part...
	# FIXME: find out all other fields.... according to ProMoS documentation there are more fields...
	"""
	# direct access to structure fields: http://docs.python.org/library/ctypes.html#ctypes.Structure._anonymous_
	_anonymous_ = ("value_type",)
	_fields_ = [("message_id",  ctypes.c_int),   # according to ProMoS documentation (=>all buffers manipulated by DMS_FindNextMessage() have same value)
				("point_name",  DMS_STRING),    # proved by experiments
				("unknown_bytes1", ctypes.c_char * 7),  # FIXME: What's in these bytes?
				("rights",  ctypes.c_char),     # proved by experiments
				("unknown_bytes2", ctypes.c_char * 7),  # FIXME: What's in these bytes?
				("dp_type",    ctypes.c_char),     # proved by experiments
				("unknown_bytes3", ctypes.c_char * 3),  # FIXME: What's in these bytes?
				("value_type", _VALUE_TYPE),
				("unknown_bytes4", ctypes.c_char * 16)]  # FIXME: What's in these bytes? Do they have a meaning

class MESSAGE(ctypes.Union):
	"""
	DMS message structure as a huge buffer,
	with parallel access to structure fields and buffer bytes.
	(Union is in C++ a a construct where different variables share same memory area)
	"""

	# ways to get to content of "ctypes.c_char * 123" bytestring-arrays:
	# repr(msg.raw)
	# ctypes.string_at(ctypes.byref(msg), ctypes.sizeof(msg)))

	# reverse-engineering: assuming that this buffer size is enough for whole structure
	# FIXME: minimize buffer size according to further analysis of used C++ structure...
	MAXLENGTH = 220

	# direct access to message bytes and structure fields in parallel: look at Flags() in dbdata.py
	_anonymous_ = ("msg",)
	_fields_ = [("msg", _MESSAGE_FIELDS),
				("raw_bytearray", ctypes.c_ubyte * MAXLENGTH)]

	def get_raw_bytestring(self):
		return bytearray(self.raw_bytearray)

	def getValue(self):
		# FIXME: implement nicer way, now we do similar things as in dms.datapoint ...
		#       should we generate an instance of dms.datapoint() ?
		type_int = ord(self.dp_type)
		if type_int == 1:
			return bool(self.val_BIT)
		elif type_int == 2:
			return int(self.val_BYS)
		elif type_int == 3:
			return int(self.val_WOS)
		elif type_int == 4:
			return int(self.val_DWS)
		elif type_int == 5:
			return int(self.val_BYU)
		elif type_int == 6:
			return int(self.val_WOU)
		elif type_int == 7:
			return int(self.val_DWU)
		elif type_int == 8:
			return float(self.val_FLT)
		elif type_int == 9:
			return self.val_STR.to_string()
		else:
			return None





class Dmspipe(object):
	"""
	Access to a running DMS by pmospipe.dll via "Access functions" ("DMS_*")

	# FIXME: implement callback function (e.g. message handler for change events of datapoints)
	# (perhaps implementing in another Class because callback-function prototype uses "ctypes.cdll.*" instead of "ctypes.windll.*"?)
	"""
	def __init__(self, pipe_name_str=r'\\.\pipe\PROMOS-DMS'):
		self.func_result = 0
		# FIXME: how to handle execution on systems without Visi.Plus(c)? ...
		dll_path = misc.visi_binaries.get_fullpath()
		if DEBUGGING:
			print('dll_path=' + dll_path)
		os.chdir(dll_path)
		self.pmospipe = ctypes.windll.LoadLibrary('pmospipe.dll')

		if DEBUGGING:
			print('pipe_name_str=' + pipe_name_str)
		self.pmospipe.DMS_ConnectEx.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
		self.pmospipe.DMS_ConnectEx.restype = ctypes.c_int
		self.handle = ctypes.c_int(0)
		self.func_result = self.pmospipe.DMS_ConnectEx(pipe_name_str, ctypes.byref(self.handle))
		assert self.handle.value != 0, u'unable to connect to DMS with argument "' + pipe_name_str + u'", is Visi.Plus(c) running?'
		if DEBUGGING:
			print('self.handle = ' + str(self.handle) + ', self.func_result = ' + str(self.func_result))

	def __del__(self):
		self.pmospipe.DMS_CloseEx.argtypes = [ctypes.c_int]
		self.pmospipe.DMS_CloseEx.restype = ctypes.c_bool
		self.pmospipe.DMS_CloseEx(self.handle)

	def get_last_errorcode(self):
		return self.func_result

	def is_dp_available(self, datapoint_str):
		# Reverse-Engineering: how to detect unavailable datapoints?
		# (since we use DMS_ReadSTREx() for getting EVERY datapoint type, there's mostly an error in self.func_result)
		# pyDMS_ReadSTREx() sets self.func_result == 2 when datapoint is not in DMS
		# if DMS is not running then self.func_result == -2
		myString = self.pyDMS_ReadSTREx(datapoint_str)
		return (self.func_result == 0 or self.func_result == -6)

	def pyDMS_ReadSTREx(self, datapoint_str):
		# self.func_result == 0 when successfully read STR datapoint
		# (it's possible to read EVERY datapoint type with this function, but then self.func_result == -6)
		self.pmospipe.DMS_ReadSTREx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
		self.pmospipe.DMS_ReadSTREx.restype = ctypes.c_int
		curr_string = ctypes.create_string_buffer(255)
		self.func_result = self.pmospipe.DMS_ReadSTREx(self.handle, datapoint_str, curr_string)
		return curr_string.value

	def pyDMS_ReadTypeEx(self, datapoint_str):
		# pyDMS_ReadTypeEx() returns -0x5 when datapoint is not in DMS
		self.pmospipe.DMS_ReadTypeEx.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.DMS_ReadTypeEx.restype = ctypes.c_int
		numeric_type = self.pmospipe.DMS_ReadTypeEx(self.handle, datapoint_str)
		return numeric_type

	def pyDMS_FindMessageEx(self, search_str):
		"""
		Get datapoints from DMS to an internal array. To access the datas use the function DMS_FindNextMessage()

		searchstring is case-sensitive and has to contain DMS nodes or leafs, no complete DMS keys
		e.g. 'merkung' doesn't match 'Bemerkung',
			'MSR01:Allg:Alarm01:ESchema' doesn't match the existing key
		(according to documentation the only wildcard search '*' hits EVERY datapoint)
		"""
		self.pmospipe.DMS_FindMessageEx.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.DMS_FindMessageEx.restype = ctypes.c_int
		num_of_dps_int = self.pmospipe.DMS_FindMessageEx(self.handle, search_str)
		return num_of_dps_int

	def pyDMS_FindNextMessage(self):
		"""
		gets DMS data as instance of MESSAGE for search results of "DMS_FindMessage()"
		=>there isn't a function "DMS_FindNextMessageEx()" in "pmospipe.dll"...
		 =>call this function so many times as there were search results (according to return value of "DMS_FindMessage()")
		"""
		self.pmospipe.DMS_FindNextMessage.argtypes = [ctypes.POINTER(MESSAGE)]
		self.pmospipe.DMS_FindNextMessage.restype = ctypes.c_char_p
		curr_msg = MESSAGE()
		dp_name_str = self.pmospipe.DMS_FindNextMessage(ctypes.byref(curr_msg))
		return (dp_name_str, curr_msg)

	# def pyDMS_FindNextMessage(self):
	# 	"""
	#   Tests / used for reverse-engineering:
	# 	gets DMS data as instance of MESSAGE for search results of "DMS_FindMessage()"
	# 	=>there isn't a function "DMS_FindNextMessageEx()" in "pmospipe.dll"...
	# 	 =>call this function so many times as there were search results (according to return value of "DMS_FindMessage()")
	# 	"""
	# 	MSG_SIZE = 500
	# 	self.pmospipe.DMS_FindNextMessage.argtypes = [ctypes.POINTER(ctypes.c_char * MSG_SIZE)]
	# 	self.pmospipe.DMS_FindNextMessage.restype = ctypes.c_char_p
	# 	#curr_msg = (ctypes.c_ubyte * MSG_SIZE)()
	# 	curr_msg = ctypes.create_string_buffer(MSG_SIZE)
	# 	dp_name_str = self.pmospipe.DMS_FindNextMessage(ctypes.byref(curr_msg))
	# 	return (dp_name_str, curr_msg)
	#
	#
	# =>display byte-by-byte when calling this function:
	# print('one char per line:')
	# for charpos in range(len(one_rec)):
	#	print(repr(one_rec.raw[charpos:charpos+1]))


	def get_DMS_keyvalue_list_by_keypart(self, dms_key_str):
		"""
		returns a list of matching DMS keyparts
		(a handy wrapper for pyDMS_FindMessageEx() and all necessary calls to pyDMS_FindNextMessage())
		"""
		my_key_list = []
		count = self.pyDMS_FindMessageEx(str(dms_key_str))
		for i in range(count):
			dp_name_str, curr_msg = self.pyDMS_FindNextMessage()
			my_key_list.append((dp_name_str, curr_msg.getValue()))
		return my_key_list

	def pyDMS_GetNamesEx(self, datapoint_str):
		"""
		searches all sons of a DMS key
		(search results were retrieved by pyDMS_GetNextNameEx())
		"""
		self.pmospipe.DMS_GetNamesEx.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.DMS_GetNamesEx.restype = ctypes.c_int
		self.func_result = self.pmospipe.DMS_GetNamesEx(self.handle, datapoint_str)

	def pyDMS_GetNextNameEx(self):
		"""
		every call returns the DMS key of next child and a flag if there are grandchildren
		(you have to call pyDMS_GetNamesEx() first)

		=>WARNING: prototype in documentation is wrong!!! (thanks to Garry/Trendgenerator for pointing me to the solution)
		in documentation version 2008: TCHAR* _stdcall DMS_GetNextName(HANDLE pipe, int& sons);
		implementation in current Visi.Plus: TCHAR* _stdcall DMS_GetNextName(int& sons);

		observed behaving:
		-when all available children were already returned, then further calling of this function returns empty strings,
		 further calls then get 'ERROR! > 300 Names'
		"""
		self.pmospipe.DMS_GetNextNameEx.argtypes = [ctypes.POINTER(ctypes.c_int)]
		self.pmospipe.DMS_GetNextNameEx.restype = ctypes.c_char_p

		has_grandchildren_cint = ctypes.c_int(0)
		curr_son_name = self.pmospipe.DMS_GetNextNameEx(ctypes.byref(has_grandchildren_cint))

		return (str(curr_son_name), has_grandchildren_cint.value != 0)


	def get_DMS_sons_list_by_key(self, datapoint_str):
		"""
		returns all sons of a DMS node
		(a handy wrapper for pyDMS_GetNamesEx() and all necessary calls to pyDMS_GetNextNameEx())
		"""
		my_key_list = []
		if datapoint_str == '' or self.is_dp_available(datapoint_str):
			self.pyDMS_GetNamesEx(datapoint_str)
			curr_nof_loops = 0
			get_next_child = True
			while get_next_child and curr_nof_loops < 1000: # FIXME: replace this magic number with correct amount of maximal allowed sons per node...
				curr_nof_loops = curr_nof_loops + 1
				son_name, has_grandchildren = self.pyDMS_GetNextNameEx()
				if son_name != '' and son_name != 'ERROR! > 300 Names':
					my_key_list.append((son_name, has_grandchildren))
				else:
					get_next_child = False
		return my_key_list


	def get_DMS_subtree_list_by_key(self, datapoint_str):
		"""
		searches recursively trough DMS subtree and returns all DMS datapoints in a list of strings

		(remark: this function returns ALL nodes...
		 parent nodes without value (DMS-type == None) weren't included into *.dms exportfiles of DMS.exe,
		 for this behaving you should check "self.pyDMS_ReadTypeEx(datapoint_str) != 0" before appending parent node!)
		"""
		myList = []

		# include parent node itself
		myList.append(datapoint_str)

		for child in self.get_DMS_sons_list_by_key(datapoint_str):
			curr_child, has_grandchildren = child
			dms_key_of_child = datapoint_str + ':' + curr_child
			if has_grandchildren:
				subnodes_list = self.get_DMS_subtree_list_by_key(dms_key_of_child)
				myList.extend(subnodes_list)
			else:
				myList.append(dms_key_of_child)
		return myList


	def get_serialized_dms_format(self, parent_node_str):
		'''
		returns a string containing all child nodes of given DMS key in their serialised format (as used in DMS import/export files)
		FIXME: rewrite and use our dms.datapoint.Dp class for more portability and replace "magic numbers"
		'''

		# call right read function for given DMS type
		readfunc_dict = {
				1:	self.pyDMS_ReadBITEx,
				2:	self.pyDMS_ReadBYSEx,
				3:	self.pyDMS_ReadWOSEx,
				4:	self.pyDMS_ReadDWSEx,
				5:	self.pyDMS_ReadBYUEx,
				6:	self.pyDMS_ReadWOUEx,
				7:	self.pyDMS_ReadDWUEx,
				8:	self.pyDMS_ReadFLTEx,
				9:  self.pyDMS_ReadSTREx
		}
		serialised_list = []

		for key in self.get_DMS_subtree_list_by_key(parent_node_str):
			curr_type = self.pyDMS_ReadTypeEx(key)
			if curr_type in readfunc_dict:
				curr_type_str = dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[curr_type]
				curr_val = readfunc_dict[curr_type](key)

				# FIXME: access rights do work this way, but we should implement a more elegant solution in "dms.datapoint.Dp"...
				curr_rights = self.pyDMS_GetRightsEx(key)
				if curr_rights & dms.datapoint.Dp.READ_WRITE:
					curr_rights_str = 'RW'
				else:
					curr_rights_str = 'RO'
				if curr_rights & dms.datapoint.Dp.CONFIG:
					curr_rights_str = curr_rights_str + 'S'

				# prepare string containing value, boolean values were stored as '0' or '1'
				if curr_type_str == 'BIT':
					if curr_val:
						curr_val_str = '1'
					else:
						curr_val_str = '0'
				elif curr_type_str == 'FLT':
					# DMS serialization has always floats with precision 10E-6
					curr_val_str = '{:.6f}'.format(curr_val)
					if DEBUGGING:
						if curr_val_str.startswith(' '):
							print('key=' + key + ', curr_val_str=' + curr_val_str + ', type(curr_val)=' + str(type(curr_val)))
				else:
					curr_val_str = str(curr_val)

				# handling all strings as unicode strings =>decode strings which could contain Umlaut
				curr_line_str = ';'.join([key,
				                          curr_type_str,
				                          curr_val_str.decode(ENCODING),
				                          curr_rights_str])
				serialised_list.append(curr_line_str)
		return '\n'.join(serialised_list)


	def write_DMS_subtree_serialization(self, datapoint_str, file_fullpath_str):
		"""
		exports a DMS subtree in DMS exportformat (*.dms) into a file
		Only difference to files exported by DMS.exe: sorting of the DMS-keys...

		FIXME: This function works as expected, but is very slow because of many DMS read access via DLL...
		=>what about multithreading? (complicated and non-trivial....)
		=>what about caching read accesses, with flag "read uncached" and a timestamp for obsolete values?
		=>what about background read-ahead cache? (complicated and non-trivial....)

		(remark: difference to get_DMS_subtree_list_by_key(): DMS serialization export format doesn't contain empty nodes)
		"""

		# Write the file out
		with io.open(file_fullpath_str, 'w', encoding=ENCODING) as f:
			# handling all strings as unicode strings =>encode to local codepage
			# remark: when file opened with 'w', then '\n' get's converted into platform specific line separator
			#   This tool writes '\r\n' as difference to DMS.exe...
			#   DMS.exe exports always with 'line feed' =>we should open textfile in binary mode and write encoded string to file...
			f.write(self.get_serialized_dms_format(datapoint_str))
			if DEBUGGING:
				print('\twrote file "' + file_fullpath_str + '"...')


	def pyDMS_GetRightsEx(self, datapoint_str):
		"""
		datapoint access rights
		(returned value: ASCII ordinal number from c_char, in python a one character string)
		=>for proper interpretation consult dms.datapoint.Dp
		"""
		self.pmospipe.DMS_GetRightsEx.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.DMS_GetRightsEx.restype = ctypes.c_char
		rights_str = self.pmospipe.DMS_GetRightsEx(self.handle, datapoint_str)
		rights_int = ord(rights_str[0])
		return rights_int


	def pyDMS_SetRightsEx(self, datapoint_str, rights_int):
		"""
		datapoint access rights
		(parameter "rights_int": ASCII ordinal number for c_char, in python a one character string)
		=>for proper interpretation consult dms.datapoint.Dp

		return value: new access rights of this datapoint =>same as pyDMS_GetRightsEx()
		"""
		self.pmospipe.DMS_SetRightsEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char]
		self.pmospipe.DMS_SetRightsEx.restype = ctypes.c_char

		rights_onechar = chr(rights_int)[0]
		new_rights_str = self.pmospipe.DMS_SetRightsEx(self.handle, datapoint_str, ctypes.c_char(rights_onechar))
		new_rights_int = ord(new_rights_str[0])
		return new_rights_int


	def pyDMS_CreateEx(self, datapoint_str, type_int):
		self.pmospipe.DMS_CreateEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char]
		self.pmospipe.DMS_CreateEx.restype = ctypes.c_int
		type_onechar = chr(type_int)
		# if DEBUGGING:
		# 	print('type_onechar: ' + str(ord(type_onechar)))
		self.func_result = self.pmospipe.DMS_CreateEx(self.handle, datapoint_str, type_onechar)

	def pyDMS_CreatePointEx(self, datapoint_str, type_int, rights_int):
		self.pmospipe.DMS_CreatePointEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char, ctypes.c_char]
		self.pmospipe.DMS_CreatePointEx.restype = ctypes.c_int
		type_onechar = chr(type_int)
		rights_onechar = chr(rights_int)
		# if DEBUGGING:
		# 	print('type_onechar: ' + str(ord(type_onechar)))
		# 	print('rights_onechar: ' + str(ord(rights_onechar)))
		self.func_result = self.pmospipe.DMS_CreatePointEx(self.handle, datapoint_str, type_onechar, rights_onechar)

	def pyDMS_DeleteEx(self, datapoint_str):
		"""
		deletes a DMS datapoint it no other process is registered onto it
		"""
		self.pmospipe.DMS_DeleteEx.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.DMS_DeleteEx.restype = ctypes.c_int
		self.func_result = self.pmospipe.DMS_DeleteEx(self.handle, datapoint_str)


	def pyDMS_WriteBITEx(self, datapoint_str, value_bool):
		self.pmospipe.DMS_WriteBITEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_bool]
		self.pmospipe.DMS_WriteBITEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_bool = ' + str(value_bool))
		self.func_result = self.pmospipe.DMS_WriteBITEx(self.handle, datapoint_str, value_bool)

	def pyDMS_WriteBYSEx(self, datapoint_str, value_bys):
		"""
		set value of signed byte (8bit) datapoint
		"""
		self.pmospipe.DMS_WriteBYSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_byte]
		self.pmospipe.DMS_WriteBYSEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_bys = ' + str(value_bys))
		self.func_result = self.pmospipe.DMS_WriteBYSEx(self.handle, datapoint_str, value_bys)

	def pyDMS_WriteWOSEx(self, datapoint_str, value_wos):
		"""
		set value of signed WORD (in Windows API: 16bit) datapoint
		"""
		self.pmospipe.DMS_WriteWOSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int16]
		self.pmospipe.DMS_WriteWOSEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_wos = ' + str(value_wos))
		self.func_result = self.pmospipe.DMS_WriteWOSEx(self.handle, datapoint_str, value_wos)

	def pyDMS_WriteDWSEx(self, datapoint_str, value_dws):
		"""
		set value of signed DWORD (in Windows API: 32bit) datapoint
		"""
		self.pmospipe.DMS_WriteDWSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int32]
		self.pmospipe.DMS_WriteDWSEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_dws = ' + str(value_dws))
		self.func_result = self.pmospipe.DMS_WriteDWSEx(self.handle, datapoint_str, value_dws)


	def pyDMS_WriteWOUEx(self, datapoint_str, value_wou):
		"""
		set value of unsigned WORD(in Windows API: 16bit) datapoint
		"""
		self.pmospipe.DMS_WriteWOUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint16]
		self.pmospipe.DMS_WriteWOUEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_wou = ' + str(value_wou))
		self.func_result = self.pmospipe.DMS_WriteWOUEx(self.handle, datapoint_str, value_wou)


	def pyDMS_WriteBYUEx(self, datapoint_str, value_byu):
		"""
		set value of unsigned BYTE datapoint
		"""
		self.pmospipe.DMS_WriteBYUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_ubyte]
		self.pmospipe.DMS_WriteBYUEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_byu = ' + str(value_byu))
		self.func_result = self.pmospipe.DMS_WriteBYUEx(self.handle, datapoint_str, value_byu)


	def pyDMS_WriteDWUEx(self, datapoint_str, value_dwu):
		"""
		set value of unsigned DWORD (in Windows API: 32bit) datapoint
		"""
		self.pmospipe.DMS_WriteDWUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_ubyte]
		self.pmospipe.DMS_WriteDWUEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_dwu = ' + str(value_dwu))
		self.func_result = self.pmospipe.DMS_WriteDWUEx(self.handle, datapoint_str, value_dwu)


	def pyDMS_WriteFLTEx(self, datapoint_str, value_flt):
		"""
		set value of float datapoint
		"""
		self.pmospipe.DMS_WriteFLTEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_double]
		self.pmospipe.DMS_WriteFLTEx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_flt = ' + str(value_flt))
		self.func_result = self.pmospipe.DMS_WriteFLTEx(self.handle, datapoint_str, value_flt)



	def pyDMS_WriteSTREx(self, datapoint_str, value_str):
		"""
		set value of string (max. length in DMS: 80 characters) datapoint
		"""
		self.pmospipe.DMS_WriteSTREx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
		self.pmospipe.DMS_WriteSTREx.restype = ctypes.c_int
		# if DEBUGGING:
		# 	print('datapoint_str = ' + datapoint_str)
		# 	print('value_str = ' + value_str)
		self.func_result = self.pmospipe.DMS_WriteSTREx(self.handle, datapoint_str, value_str)

	def pyDMS_ReadBITEx(self, datapoint_str):
		"""
		reads a boolean datapoint.
		=>when read as string, then pmospipe returns "ON" or "OFF", but read as boolean, then it works as expected... :-)
		"""
		self.pmospipe.DMS_ReadBITEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_bool)]
		self.pmospipe.DMS_ReadBITEx.restype = ctypes.c_int

		curr_bit = ctypes.c_bool()
		self.func_result = self.pmospipe.DMS_ReadBITEx(self.handle, datapoint_str, ctypes.byref(curr_bit))
		return curr_bit.value

	def pyDMS_ReadBYSEx(self, datapoint_str):
		self.pmospipe.DMS_ReadBYSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_byte)]
		self.pmospipe.DMS_ReadBYSEx.restype = ctypes.c_int

		curr_bys = ctypes.c_byte()
		self.func_result = self.pmospipe.DMS_ReadBYSEx(self.handle, datapoint_str, ctypes.byref(curr_bys))
		return curr_bys.value

	def pyDMS_ReadWOSEx(self, datapoint_str):
		self.pmospipe.DMS_ReadWOSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int16)]
		self.pmospipe.DMS_ReadWOSEx.restype = ctypes.c_int

		curr_wos = ctypes.c_int16()
		self.func_result = self.pmospipe.DMS_ReadWOSEx(self.handle, datapoint_str, ctypes.byref(curr_wos))
		return curr_wos.value

	def pyDMS_ReadDWSEx(self, datapoint_str):
		self.pmospipe.DMS_ReadDWSEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32)]
		self.pmospipe.DMS_ReadDWSEx.restype = ctypes.c_int

		curr_dws = ctypes.c_int32()
		self.func_result = self.pmospipe.DMS_ReadDWSEx(self.handle, datapoint_str, ctypes.byref(curr_dws))
		return curr_dws.value


	def pyDMS_ReadBYUEx(self, datapoint_str):
		self.pmospipe.DMS_ReadBYUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte)]
		self.pmospipe.DMS_ReadBYUEx.restype = ctypes.c_int

		curr_byu = ctypes.c_ubyte()
		self.func_result = self.pmospipe.DMS_ReadBYUEx(self.handle, datapoint_str, ctypes.byref(curr_byu))
		return curr_byu.value

	def pyDMS_ReadWOUEx(self, datapoint_str):
		self.pmospipe.DMS_ReadWOUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint16)]
		self.pmospipe.DMS_ReadWOUEx.restype = ctypes.c_int

		curr_wou = ctypes.c_uint16()
		self.func_result = self.pmospipe.DMS_ReadWOUEx(self.handle, datapoint_str, ctypes.byref(curr_wou))
		return curr_wou.value


	def pyDMS_ReadDWUEx(self, datapoint_str):
		self.pmospipe.DMS_ReadDWUEx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32)]
		self.pmospipe.DMS_ReadDWUEx.restype = ctypes.c_int

		curr_dwu = ctypes.c_uint32()
		self.func_result = self.pmospipe.DMS_ReadDWUEx(self.handle, datapoint_str, ctypes.byref(curr_dwu))
		return curr_dwu.value


	def pyDMS_ReadFLTEx(self, datapoint_str):
		# FIXME: self.func_result is always "-6" .... :-(
		# =>returned value is right! :-)
		# pmospipe returns a NUL terminated string, it seems to be a DECIMAL with resolution 0.001, NOT FLOAT!!!
		self.pmospipe.DMS_ReadSTREx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(DMS_STRING)]
		self.pmospipe.DMS_ReadSTREx.restype = ctypes.c_int

		curr_decimal = DMS_STRING('0.0')
		self.func_result = self.pmospipe.DMS_ReadSTREx(self.handle, datapoint_str, ctypes.byref(curr_decimal))
		return decimal.Decimal(curr_decimal.to_string())


def main(argv=None):

	curr_dms = Dmspipe()

	# reverse engineering: PET numbering of datapoints with PLC communication
	# get unique list of DMS types for analogue values:
	analogue_dpnames = ['MSR01:E01:LueKeller:Auto:Err_AbVerz','MSR01:E01:LueKeller:Auto:Err_AnVerz','MSR01:E01:LueKeller:Auto:Err_SaGroup']
	digital_dpnames = ['MSR01:E01:LueKeller:Auto:Err','MSR01:E01:LueKeller:Auto:Err_Freigabe','MSR01:E01:LueKeller:Auto:Err_Freigabe_Ext','MSR01:E01:LueKeller:Auto:Err_Freigabe_ExtAktiv','MSR01:E01:LueKeller:Auto:Err_Freigabe_ExtLogik']
	datablock_dpnames = ['MSR01:H01:BalAntr:CFG_CONFIG_DB','MSR01:H01:KesAntr:CFG_CONFIG_DB']
	for dpname in analogue_dpnames:
		myset = set()
		myset.add(curr_dms.pyDMS_ReadTypeEx(dpname))
	print('analogue values in SDriver-communication have DMS-types: ' + str(myset))
	for dpname in digital_dpnames:
		myset = set()
		myset.add(curr_dms.pyDMS_ReadTypeEx(dpname))
	print('digital values in SDriver-communication have DMS-types: ' + str(myset))
	for dpname in datablock_dpnames:
		myset = set()
		myset.add(curr_dms.pyDMS_ReadTypeEx(dpname))
	print('datablock values in SDriver-communication have DMS-types: ' + str(myset))




	# # test: some read operations
	# # (reading everything with pyDMS_ReadSTREx() does work, but with error "-6"! )
	# dms_dp_names = ['System:Time', 'MSR01:Allg:Aussentemp:Istwert', 'MSR01:Allg:Aussentemp:Err']
	# for dp in dms_dp_names:
	# 	print('DMS-key "' + dp + '" contains string "' + curr_dms.pyDMS_ReadSTREx(dp) + '"')
	# 	print('\tDMS numeric type: ' + hex(curr_dms.pyDMS_ReadTypeEx(dp)))
	# 	print('\taccess rights: ' + str(curr_dms.pyDMS_GetRightsEx(dp)))
	# 	if DEBUGGING:
	# 		print('\tself.func_result =' + str(curr_dms.func_result))
	# print('****\n')
	#
	# dp_testcases = [('System:Time', 'STR', curr_dms.pyDMS_ReadSTREx),
	#                 ('MSR01:TEST:val_FLT', 'FLT', curr_dms.pyDMS_ReadFLTEx),
	#                 ('MSR01:TEST:val_BIT', 'BIT', curr_dms.pyDMS_ReadBITEx),
	#                 ('MSR01:TEST:val_BYS', 'BYS', curr_dms.pyDMS_ReadBYSEx),
	#                 ('MSR01:TEST:val_WOS', 'WOS', curr_dms.pyDMS_ReadWOSEx),
	#                 ('MSR01:TEST:val_DWS', 'DWS', curr_dms.pyDMS_ReadDWSEx),
	#                 ('MSR01:TEST:val_BYU', 'BYU', curr_dms.pyDMS_ReadBYUEx),
	#                 ('MSR01:TEST:val_WOU', 'WOU', curr_dms.pyDMS_ReadWOUEx),
	#                 ('MSR01:TEST:val_DWU', 'DWU', curr_dms.pyDMS_ReadDWUEx)]
	# for dp in dp_testcases:
	# 	print('\nTest: Read ' + dp[1])
	# 	print('"' + dp[0] + '" contains string "' + curr_dms.pyDMS_ReadSTREx(dp[0]) + '"')
	# 	print('\tself.func_result =' + str(curr_dms.func_result))
	# 	print('"' + dp[0] + '" contains ' + dp[1] + ' "' + str(dp[2](dp[0])) + '"')
	# 	print('\tself.func_result =' + str(curr_dms.func_result))
	#
	#
	# print('\nTest datapoint access rights:')
	# # before test: all these datapoints had accessrights int(10)
	# for dp in dp_testcases:
	# 	print('\n' + dp[0] + ': current access rights "GetRights": ' + str(curr_dms.pyDMS_GetRightsEx(dp[0])))
	# 	print('\tself.func_result =' + repr(curr_dms.func_result))
	# 	print('setting new access rights... new rights acccording to "SetRights": ' +
	# 		str(curr_dms.pyDMS_SetRightsEx(dp[0], dms.datapoint.Dp.REMANENT |
	# 								dms.datapoint.Dp.READ_ONLY |
	# 								dms.datapoint.Dp.READ_WRITE)))
	# 	print(dp[0] + ': current access rights "GetRights": ' + str(curr_dms.pyDMS_GetRightsEx(dp[0])))
	# 	print('\tself.func_result =' + repr(curr_dms.func_result))



	# # test: write dms keys
	# dp_numeric_types_dict = { 'NONE':   0,
	# 			'BIT':	1,
	# 			'BYS':	2,
	# 			'WOS':	3,
	# 			'DWS':	4,
	# 			'BYU':	5,
	# 			'WOU':	6,
	# 			'DWU':	7,
	# 			'FLT':	8,
	# 			'STR':	9,
	# 		}
	# rights_int = 2**1 + 2**3 + 2**7
	# new_dps = [('MSR01:WRITE_TEST:val_bit', 'BIT', True),
	#            ('MSR01:WRITE_TEST:val_bys', 'BYS', 1),
	#            ('MSR01:WRITE_TEST:val_wos', 'WOS', 2),
	#            ('MSR01:WRITE_TEST:val_dws', 'DWS', 3),
	#            ('MSR01:WRITE_TEST:val_byu', 'BYU', 4),
	#            ('MSR01:WRITE_TEST:val_wou', 'WOU', 5),
	#            ('MSR01:WRITE_TEST:val_dwu', 'DWU', 6),
	#            ('MSR01:WRITE_TEST:val_flt', 'FLT', 1.1),
	#            ('MSR01:WRITE_TEST:val_str', 'STR', 'Teststring')]
	# for item in new_dps:
	# 	key_str = item[0]
	# 	type_int = dp_numeric_types_dict[item[1]]
	# 	value = item[2]
	#
	# 	# # reading non-existent key:
	# 	# print('DMS-key "' + key_str + '" contains string "' + curr_dms.pyDMS_ReadSTREx(key_str) + '"')
	# 	# print('\tDMS numeric type: ' + hex(curr_dms.pyDMS_ReadTypeEx(key_str)))
	# 	# print('\taccess rights: ' + str(curr_dms.pyDMS_GetRightsEx(key_str)))
	# 	# if DEBUGGING:
	# 	# 	print('\tDMS_ReadSTREx: self.func_result =' + str(curr_dms.func_result))
	#
	# 	if curr_dms.is_dp_available(key_str):
	# 		print('\n"' + key_str + '" does already exists in DMS!')
	# 	else:
	# 		print('"' + key_str + '" is not in DMS!')
	#
	# 	# create new key and write value into DMS:
	# 	curr_dms.pyDMS_CreatePointEx(key_str, type_int, rights_int)
	# 	if DEBUGGING:
	# 		print('\tDMS_CreatePointEx: self.func_result =' + str(curr_dms.func_result))
	#
	# 	# call right write function for this DMS type
	# 	writefunc_dict = { 'BIT':	curr_dms.pyDMS_WriteBITEx,
	# 			'BYS':	curr_dms.pyDMS_WriteBYSEx,
	# 			'WOS':	curr_dms.pyDMS_WriteWOSEx,
	# 			'DWS':	curr_dms.pyDMS_WriteDWSEx,
	# 			'BYU':	curr_dms.pyDMS_WriteBYUEx,
	# 			'WOU':	curr_dms.pyDMS_WriteWOUEx,
	# 			'DWU':	curr_dms.pyDMS_WriteDWUEx,
	# 			'FLT':	curr_dms.pyDMS_WriteFLTEx,
	# 			'STR':	curr_dms.pyDMS_WriteSTREx
	# 	}
	# 	writefunc_dict[item[1]](key_str, value)
	# 	if DEBUGGING:
	# 		print('\tDMS_Write*Ex: self.func_result =' + str(curr_dms.func_result))
	#
	# 	# reading new key:
	# 	print('DMS-key "' + key_str + '" contains string "' + curr_dms.pyDMS_ReadSTREx(key_str) + '"')
	# 	print('\tDMS numeric type: ' + hex(curr_dms.pyDMS_ReadTypeEx(key_str)))
	# 	print('\taccess rights: ' + str(curr_dms.pyDMS_GetRightsEx(key_str)))
	# 	if DEBUGGING:
	# 		print('\tDMS_ReadSTREx: self.func_result =' + str(curr_dms.func_result))
	#
	# 	# now deletion of this datapoint...
	# 	curr_dms.pyDMS_DeleteEx(key_str)
	# 	if DEBUGGING:
	# 		print('\tDMS_DeleteEx: self.func_result =' + str(curr_dms.func_result))
	#
	# 	if curr_dms.is_dp_available(key_str):
	# 		print('"' + key_str + '" does still exist in DMS!')
	# 	else:
	# 		print('"' + key_str + '" is no more in DMS.')
	# 	print('Done.\n')



	# # get number of datapoints matching a search string
	# print('Searching for datapoints')
	# # 'Bemerkung' isn't found... neither 'MSR01:Allg:Alarm01:ESchema'
	# search_list = ['System', 'OBJECT', 'H01', '*merkung', 'merkung', 'ESchema', 'object', 'MSR01:Allg:Alarm01:ESchema']
	# for item in search_list:
	# 	count = curr_dms.pyDMS_FindMessageEx(item)
	# 	print('\tnumber of datapoints matching search "' + item + '": ' + str(count))
	# print('search is done.')




	# # search dms keys and retrieve all their values
	# testcases = ['OBJECT', 'Err', 'Istwert', 'H01']
	# for item in testcases:
	# 	key_list = curr_dms.get_DMS_keyvalue_list_by_keypart(item)
	# 	print('Search for "' + item + '" had ' + str(len(key_list))+ ' hits:')
	# 	for item in key_list:
	# 		curr_key_str, curr_value = item
	# 		print('\tDMS key "' + curr_key_str + '" has value "' + str(curr_value) + '"')


	# # get all sons of a specific DMS key
	# print('get all sons of specific DMS keys...')
	# dms_keys_list = ['', 'MSR01', 'MSR01:Allg:Aussentemp', 'NOT_EXISTENT_KEY']
	# for curr_parent in dms_keys_list:
	# 	print('\tsons of "' + curr_parent + '":')
	# 	for curr_son in curr_dms.get_DMS_sons_list_by_key(curr_parent):
	# 		print('\t\t' + curr_son[0] + ', has_son = ' + str(curr_son[1]))
	#
	# # write whole DMS into a file
	# t_start = time.time()
	# export_filename = r'D:\running_DMS.dms'
	# print('\nExporting running DMS into exportfile "' + export_filename + '"')
	# with open(export_filename, 'w') as f:
	# 	curr_parent = 'MSR01'
	# 	all_DMS_keys = curr_dms.get_DMS_subtree_list_by_key(curr_parent)
	# 	print('\tsubtree "' + curr_parent + '" counts ' + str(len(all_DMS_keys)) + ' DMS keys')
	# 	for curr_key in all_DMS_keys:
	# 		f.write(curr_key + '\n')
	# print('\t\t=>excecution time for this code: ' + str(time.time() - t_start) + ' seconds')
	#
	# # test DMS-types:
	# print('\ntest DMS-types')
	# for key_str in curr_dms.get_DMS_subtree_list_by_key('MSR01:TEST'):
	# 	# reading keys:
	# 	print('DMS-key "' + key_str + '" contains string "' + curr_dms.pyDMS_ReadSTREx(key_str) + '"')
	# 	print('\tDMS numeric type: ' + hex(curr_dms.pyDMS_ReadTypeEx(key_str)))
	# 	print('\taccess rights: ' + str(curr_dms.pyDMS_GetRightsEx(dp)))

	# # Test searching for strings:
	# count_i = curr_dms.pyDMS_FindMessageEx('OBJECT')
	# print('found ' + str(count_i) + ' times "OBJECT"')
	# for n in range(count_i):
	# 	dms_name = curr_dms.pyDMS_FindNextMessage()
	# 	print('\t' + str(n) + ': ' + dms_name)



	return 0        # success


if __name__ == '__main__':
	status = main()