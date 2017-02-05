#!/usr/bin/env python
# encoding: utf-8
"""
misc.clipboard.py
stores and retrieves PROMOS clipboard objects

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

# very good helper tool for reversing clipboard format:
# http://www.nirsoft.net/utils/inside_clipboard.html

# based on example code from
# http://bugs.python.org/file37366/test_clipboard_win.py

DEBUGGING = False

import ctypes
import locale
import sys
import hashlib

def cp_PROMOS_factory(curr_size):
	# factory for dynamic size structure
	# example:
	# http://stackoverflow.com/questions/3400495/how-do-i-emulate-a-dynamically-sized-c-structure-in-python-using-ctypes
	# http://stackoverflow.com/questions/7015487/ctypes-variable-length-structures
	class CP_PROMOS(ctypes.Structure):
		"""
		clipboard object "PROMOS" with unknown structure
		"""

		# ways to get to content of "ctypes.c_char * 123" bytestring-arrays:
		# repr(msg.raw)
		# ctypes.string_at(ctypes.byref(msg), ctypes.sizeof(msg)))
		_fields_ = [("raw_bytearray",   ctypes.c_ubyte * curr_size)]

		def get_raw_bytestring(self):
			return bytearray(self.raw_bytearray)


		def get_md5_hash(self):
			"""
			returns the MD5 hash digest of the PROMOS object
			(yes, there ARE more secure hash algorithms, but hey, we need performance instead of cryptographic security!)
			"""
			m = hashlib.md5()
			m.update(self.get_raw_bytestring())
			return m.digest()


		def get_strings(self, allowed_ord_nums, encoding='cp1252'):
			"""
			a generator which returns all strings found on clipboard

			parameters:
				allowed_ord_nums: a list, set or tuple of allowed ordinal numbers (you have to take care of the encoding!!!)
				encoding: encoding to use for returning string ( https://docs.python.org/2/library/codecs.html )

			FIXME: how can we build this efficient? Now we check every character
			(strings aren't always NUL-terminated, often they have a size-value just in front of them...)
			"""
			char_list = []
			for idx in xrange(curr_size):
				# filter characters by ordinal number of ASCII code
				# http://www.asciitable.com/
				# =>warning: take the right characterset for Umlaut and other special characters!
				# =>per default we use Windows Codepage-1252 (Western Europe)
				# https://docs.python.org/2/library/codecs.html
				# https://de.wikipedia.org/wiki/ISO_8859-1#Windows-1252
				try:
					if self.raw_bytearray[idx] in allowed_ord_nums:
						mychar = chr(self.raw_bytearray[idx]).decode(encoding)
						char_list.append(mychar)
					else:
						# hmm, should we return it as unicode string with "u''.join()"?
						# until now we don't really care encoding problems... :-/
						yield ''.join(char_list)
						char_list = []
				except UnicodeDecodeError:
					yield ''.join(char_list)
					char_list = []


		def get_dms_keys(self):
			"""
			collects all found strings into a sorted list with unique elements

			-dangerous assumption: every string containing a ':' with at least one character before and after ':' is a DMS key...
			=>you have to check if they're valid DMS keys!
			"""
			result_set = set()
			DELIMITER = ':'
			#=>FIXME: currently we only accept [A-Z]|[a-z]|[0-9]|[_:] as valid DMS keys...
			#  But DMS is able to handle many more characters! (this way it's a problem to find the strings in clipboard object)
			ord_nums = []
			ord_nums.extend(range(ord('0'), ord('9') + 1))
			ord_nums.extend(range(ord('A'), ord('Z') + 1))
			ord_nums.extend(range(ord('a'), ord('z') + 1))
			ord_nums.extend([ord(':'), ord('_')])
			allowed_ord_nums = set(ord_nums)
			for mystring in self.get_strings(allowed_ord_nums):
				if len(mystring) >= 3:
					if DELIMITER in mystring:
						if mystring[0] != DELIMITER and mystring[-1] != DELIMITER:
							result_set.add(mystring)
			return sorted(list(result_set))

	return CP_PROMOS




# http://stackoverflow.com/questions/579687/how-do-i-copy-a-string-to-the-clipboard-on-windows-using-python/4203897
class Clipboard(object):
	# based on example code from
	# http://bugs.python.org/file37366/test_clipboard_win.py
	# http://stackoverflow.com/questions/579687/how-do-i-copy-a-string-to-the-clipboard-on-windows-using-python/4203897

	cp_format_dict = {}                     # look-up for "clipboard format name" -> "clipboard format number"
	CF_UNICODETEXT = 13                     # standard clipboard format
	NAME_CF_PROMOS = 'PROMOS'               # custom clipboard format used by ProMoS (format name "PROMOS")
	cf_promos = 0                           # (system-dependant number, Windows assign it when clipboard format is registered)
	NAME_CF_CATALOGUE_OBJ = 'CATALOGUE_OBJ' # custom clipboard format used by ProMoS (format name "Catalogue Object")
	cf_catalogue_obj = 0                    # (system-dependant number, Windows assign it when clipboard format is registered)
	GMEM_DDESHARE = 0x2000

	# WinAPI: system errorcode
	# https://msdn.microsoft.com/en-us/library/windows/desktop/ms681382%28v=vs.85%29.aspx
	ERROR_INVALID_PARAMETER = 87

	wcscpy = ctypes.cdll.msvcrt.wcscpy
	OpenClipboard = ctypes.windll.user32.OpenClipboard
	EmptyClipboard = ctypes.windll.user32.EmptyClipboard
	GetClipboardData = ctypes.windll.user32.GetClipboardData
	SetClipboardData = ctypes.windll.user32.SetClipboardData
	CloseClipboard = ctypes.windll.user32.CloseClipboard

	EnumClipboardFormats = ctypes.windll.user32.EnumClipboardFormats

	# do protection against incompatible argument types... "A" stands for ANSI...
	GetClipboardFormatNameA = ctypes.windll.user32.GetClipboardFormatNameA
	GetClipboardFormatNameA.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_int]
	GetClipboardFormatNameA.restype = ctypes.c_int

	GlobalAlloc = ctypes.windll.kernel32.GlobalAlloc
	GlobalLock = ctypes.windll.kernel32.GlobalLock
	GlobalUnlock = ctypes.windll.kernel32.GlobalUnlock
	GlobalSize = ctypes.windll.kernel32.GlobalSize

	GetLastError = ctypes.windll.kernel32.GetLastError

	def __init__(self):
		self.cp_obj = None
		Clipboard._get_cp_formats()
		self.found_obj_list = []

	@classmethod
	def _get_cp_formats(cls):
		"""
		Get clipboard formats from current clipboard objects and fill it in a dict with their names as key.
		=>call this before GetClipboardData() for filling this system-dependant dictionary

		(when clipboard formats were registered, then Windows assigns a unique number to this format.
		This is only needed for non-standard clipboard formats, those have their predefined format number)
		"""

		# first step: getting clipboard format numbers
		cls.OpenClipboard(None)
		cp_num_list = []
		nextformat = 0
		firstrun = True
		while nextformat != 0 or firstrun:
			firstrun = False
			nextformat = cls.EnumClipboardFormats(nextformat)
			if nextformat != 0:
				# got valid clipboard format number
				cp_num_list.append(nextformat)
			else:
				if DEBUGGING:
					# "ERROR_SUCCESS" = 0
					# (any other value needs debugging, consult this website and lookup your "System Error Codes":
					# https://msdn.microsoft.com/en-us/library/windows/desktop/ms681382%28v=vs.85%29.aspx
					errcode = cls.GetLastError()
					if errcode != 0:
						print('Error code "' + str(errcode) + '" returned by EnumClipboardFormats(...)')
						print('\t(got ' + str(len(cp_num_list)) + ' clipboard formats from Windows API), now retrieving their name...')
		cls.CloseClipboard()

		# second step: lookup the clipboard format names, fill them into our dictionary
		for cp_num in cp_num_list:
			# maximal length of string according to a comment on
			# https://msdn.microsoft.com/en-us/library/windows/desktop/ms649040%28v=vs.85%29.aspx
			maxlength = 256
			mybuf = ctypes.create_string_buffer(maxlength)
			retval = cls.GetClipboardFormatNameA(cp_num, mybuf, maxlength)
			if retval > 0:
				# return value is length of clipboard format name in our buffer (we don't need this info)
				if not mybuf.value in cls.cp_format_dict:
					cls.cp_format_dict[mybuf.value] = cp_num
				if DEBUGGING:
					print('found custom clipboard format "' + mybuf.value + '" (unique id is ' + str(cp_num) + ')')
			else:
				errcode = cls.GetLastError()
				if errcode == cls.ERROR_INVALID_PARAMETER:
					# we found standard clipboard format as defined in
					# https://msdn.microsoft.com/en-us/library/windows/desktop/ff729168%28v=vs.85%29.aspx
					# =>ignoring it (there doesn't seem to be a way to retrieve default cp format names?)
					if DEBUGGING:
						print('found predefined clipboard format with unique id ' + str(cp_num) + ', ignoring it...')
				else:
					# Any other errorcode zero needs debugging, consult this website and lookup your "System Error Codes":
					# https://msdn.microsoft.com/en-us/library/windows/desktop/ms681382%28v=vs.85%29.aspx
					if DEBUGGING:
						print('->Error code "' + str(errcode) + '" returned by GetClipboardFormatName(...)')
						print('\t(clipboard format number is ' + str(cp_num) + ', returned string is "' + mybuf.value + '"')

	def copy_c(self, data):
		try:  # Python 2
			if not isinstance(data, unicode):
				data = data.decode('mbcs')
		except NameError:
			if not isinstance(data, str):
				data = data.decode('mbcs')
		Clipboard.OpenClipboard(None)
		Clipboard.EmptyClipboard()
		hCd = Clipboard.GlobalAlloc(Clipboard.GMEM_DDESHARE, 2 * (len(data) + 1))
		pchData = Clipboard.GlobalLock(hCd)
		Clipboard.wcscpy(ctypes.c_wchar_p(pchData), data)
		Clipboard.GlobalUnlock(hCd)
		Clipboard.SetClipboardData(Clipboard.CF_UNICODETEXT, hCd)
		self._reinsert_PROMOS()
		Clipboard.CloseClipboard()


	def _reinsert_PROMOS(self):
		"""
		Experimental: Reinsertion of last PROMOS object
		=>it works! It seems that "CATALOGUE_OBJ" isn't needed for copy&paste of Visi+ objects
		"""
		if self.cp_obj:
			buf_size = ctypes.sizeof(self.cp_obj)
			hCd = Clipboard.GlobalAlloc(Clipboard.GMEM_DDESHARE, buf_size)
			pchData = Clipboard.GlobalLock(hCd)
			ctypes.memmove(pchData, ctypes.byref(self.cp_obj), buf_size)
			Clipboard.GlobalUnlock(hCd)
			try:
				Clipboard.SetClipboardData(Clipboard.cp_format_dict[Clipboard.NAME_CF_PROMOS], hCd)
			except KeyError:
				if DEBUGGING:
					print('Can not resinsert CF_PROMOS object on clipboard yet... =>format number of CF_PROMOS is unknown on this system!')
		else:
			if DEBUGGING:
					print('Can not resinsert CF_PROMOS object on clipboard: there is no CF_PROMOS object available!')


	def paste_c(self):
		Clipboard._get_cp_formats()
		Clipboard.OpenClipboard(None)
		try:
			handle = Clipboard.GetClipboardData(Clipboard.cp_format_dict[Clipboard.NAME_CF_PROMOS])
		except KeyError:
			if DEBUGGING:
				print('We have never seen a CF_PROMOS object on clipboard yet... =>format number of CF_PROMOS is unknown on this system!')
			handle = 0

		if handle != 0:
			# found a CF_PROMOS object
			if DEBUGGING:
				print('found a CF_PROMOS object on clipboard. Handle is now ' + str(handle))

			# size of clipboard object is not accurate in every case...
			# PROMOS object has minimal size of 8192 bytes, and maximum size is "as huge as needed"...
			# =>could have data from earlier copy processes in there!
			# http://stackoverflow.com/questions/22075754/how-do-i-determine-clipboard-data-size
			# https://msdn.microsoft.com/en-us/library/windows/desktop/aa366593%28v=vs.85%29.aspx
			buf_size = Clipboard.GlobalSize(handle)
			if DEBUGGING:
				print('size of CF_PROMOS object: ' + str(buf_size))

			cp_class = cp_PROMOS_factory(buf_size)
			self.cp_obj = cp_class()
			ctypes.memmove(ctypes.byref(self.cp_obj), handle, buf_size)

			if DEBUGGING:
				#print('\nCF_PROMOS object contains these strings:')
				#for mystring in cp_obj.get_strings():
				#	print('\t' + mystring)

				print('\nCF_PROMOS object contains these possible DMS-keys:')
				for mystring in self.cp_obj.get_dms_keys():
					print('\t' + mystring)

				print('\nMD5-hash of the CF_PROMOS memory block is :' + repr(self.cp_obj.get_md5_hash()))
			self.found_obj_list = self.cp_obj.get_dms_keys()
			curr_hash = self.cp_obj.get_md5_hash()
		else:
			if DEBUGGING:
				print('There is no CF_PROMOS object on clipboard...')
			self.found_obj_list = []
			curr_hash = ''
		Clipboard.CloseClipboard()

		return self.found_obj_list, curr_hash


def main(argv=None):
	clp = Clipboard()
	clp.paste_c()
	#print('Is there a PROMOS object in clipbboard?')
	# if len(data) > 0:
	# 	print('YES!')
	# 	print(repr(data))
	# else:
	# 	print('No.')


	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)