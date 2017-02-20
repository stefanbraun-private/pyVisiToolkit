#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.trendfile.py

Handling and parsing of trendfiles (*.hdb)

Copyright (C) 2016/2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import ctypes
import os
import datetime
from trend.datasource.dbdata import HighLevelDBData as DBData
import configparser
import string

DEBUGGING = False


class DBData_Timestamp_Search_Result(object):
	"""
	contains lists of DBData elements after search for a specific point of time:
	-exact: elements with equal timestamps

	if "exact"-list is empty, then these lists help to calculate values in between:
	-before: elements with same timestamps before point of time
	-after: elements with same timestamps after point of time
	"""
	def __init__(self):
		self.before_list = []
		self.exact_list = []
		self.after_list = []

	def set_before(self, before_list):
		self.before_list = before_list

	def set_exact(self, exact_list):
		self.exact_list = exact_list

	def set_after(self, after_list):
		self.after_list = after_list



def get_trendfile_structure_obj(file_fullpath):
	"""
	returns appropriate structure for accessing all DBData elements
	(ctypes.Structure doesn't allow unknown amounts of elements)
	"""

	DMSDP_NOF_BYTES = 83        # based on observations made in class "PDBSData" (pdbsdata.py)
	TRENDDATA_OFFSET = 1024     # based ob reverse engineering *.hdb file format

	filesize = os.path.getsize(file_fullpath)
	nof_dbdata_elems = (filesize - TRENDDATA_OFFSET) / ctypes.sizeof(DBData)

	class Trendfile_structure(ctypes.LittleEndianStructure):
		"""
		Header contains DMS datapoint name,
		data section contains all DBData elements, amount depends on filesize...
		"""
		# contains some hints from http://stackoverflow.com/questions/18536182/parsing-binary-data-into-ctypes-structure-object-via-readinto
		_fields_ = [
			("dmsDatapoint", ctypes.c_char * DMSDP_NOF_BYTES),                          # DMS datapoint name
			("UNKNOWN_BYTES", ctypes.c_char * (TRENDDATA_OFFSET - DMSDP_NOF_BYTES)),    # perhaps unused
			("dbdata", DBData * nof_dbdata_elems)                                       # array of DBData elements

		]

	# return an instance to caller
	return Trendfile_structure()



class RawTrendfile(object):
	def __init__(self, fileFullpath):
		self._fileFullpath = fileFullpath
		self._trendstruct = get_trendfile_structure_obj(self._fileFullpath)
		self._parseFile_()

	def _parseFile_(self):
		# reading binary trendfile into ctypes structure
		# contains hints from http://stackoverflow.com/questions/18536182/parsing-binary-data-into-ctypes-structure-object-via-readinto
		with open(self._fileFullpath, "rb") as f:
			f.readinto(self._trendstruct)

	def get_dms_Datapoint(self):
		return self._trendstruct.dmsDatapoint

	def get_nof_dbdata_elements(self):
		return len(self._trendstruct.dbdata)

	def get_first_timestamp(self):
		return self._trendstruct.dbdata[0].get_datetime()

	def get_last_timestamp(self):
		return self._trendstruct.dbdata[-1].get_datetime()

	def get_dbdata_elements_generator(self, start_datetime=None, end_datetime=None):
		"""
		a generator for memory efficient retrieving DBData elements
		(caller can only loop once through generator,
		read here: http://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python  )
		=>optional arguments allows filtering of DBData elements
		"""
		# FIXME: implement some filtering (same as in "trendfile.py.old"?) Or is further filtering done in HighLevelTrendfile?
		for elem in self._trendstruct.dbdata:
			ignore = False
			if start_datetime:
				if elem.get_datetime() < start_datetime:
					ignore = True
			if end_datetime:
				if elem.get_datetime() > end_datetime:
					ignore = True

			if not ignore:
				yield elem

	def get_dbdata_elements_as_set(self):
		"""
		returns DBData elements in a set()
		"""
		# FIXME: should we improve this code? How can we get good performance in Megabytes of trenddata?
		# FIXME: Should we save the set() for next function execution, or does we allow altering of trenddata in-memory?
		return set(self._trendstruct.dbdata)


	def get_DBData_Timestamp_Search_Result(self, timestamp_datetime):
		"""
		returns an instance of DBData_Timestamp_Search_Result according to given timestamp
		"""
		# FIXME: method works as expected, but we should find a cleaner solution...

		search_result = DBData_Timestamp_Search_Result()

		# begin and end indeces of three lists don't overlap: [before_begin, ..., before_end] [exact_begin, ..., exact_end] [after_begin, ..., after_end]
		# based on examples from https://docs.python.org/2/library/bisect.html
		idx_bisect_left = self._get_bisect_left(timestamp_datetime)

		# based on example: "Locate the leftmost value exactly equal to x"
		# =>collecting all DBData elements with given timestamp

		if idx_bisect_left == len(self._trendstruct.dbdata):
			# special case: timestamp is higher than highest DBData-timestamp
			# =>do workaround: taking last element and continue processing...
			curr_elem = self._trendstruct.dbdata[-1]
		else:
			curr_elem = self._trendstruct.dbdata[idx_bisect_left]

		if idx_bisect_left != len(self._trendstruct.dbdata) and curr_elem.get_datetime() == timestamp_datetime:
			# we found "exact_begin"
			# appending all elements with same timestamp
			idx = idx_bisect_left
			exact_timestamp = curr_elem.get_datetime()
			while idx < len(self._trendstruct.dbdata):
				curr_elem = self._trendstruct.dbdata[idx]
				if curr_elem.get_datetime() == exact_timestamp:
					search_result.exact_list.append(self._trendstruct.dbdata[idx])
					idx = idx + 1
				else:
					break
		else:
			# no exact search hits found... =>populating list "before"
			if idx_bisect_left > 0:
				idx = idx_bisect_left - 1
				before_timestamp = self._trendstruct.dbdata[idx].get_datetime()
				while idx >= 0:
					# collecting DBData elements with equal timestamps
					curr_elem = self._trendstruct.dbdata[idx]
					if curr_elem.get_datetime() == before_timestamp:
						search_result.before_list.append(self._trendstruct.dbdata[idx])
						idx = idx - 1
					else:
						break
			# ... and populating list "after"
			# based on example "Find leftmost value greater than x"
			idx_bisect_right = self._get_bisect_right(timestamp_datetime)
			if idx_bisect_right != len(self._trendstruct.dbdata):
				idx = idx_bisect_right
				after_timestamp = self._trendstruct.dbdata[idx].get_datetime()
				while idx < len(self._trendstruct.dbdata):
					# collecting DBData elements with equal timestamps
					curr_elem = self._trendstruct.dbdata[idx]
					if curr_elem.get_datetime() == after_timestamp:
						search_result.after_list.append(self._trendstruct.dbdata[idx])
						idx = idx + 1
					else:
						break
		return search_result



	def _get_bisect_left(self, timestamp_datetime):
		"""
		returns index of DBData element with exact timestamp or later
		"""
		# our DBData elements are sorted by timestamp
		# =>we can use binary searching! There's already class "bisect" for this.
		# =>problem: using "bisect" is impossible, it can't handle DBData directly...: https://docs.python.org/2/library/bisect.html

		# =>now we adapt algorithm from it's source: https://hg.python.org/cpython/file/2.7/Lib/bisect.py
		# Find DBData ("bisect.bisect_left()")
		low = 0
		high = len(self._trendstruct.dbdata)
		while low < high:
			mid = (low + high) // 2
			if self._trendstruct.dbdata[mid].get_datetime() < timestamp_datetime:
				low = mid + 1
			else:
				high = mid
		return low


	def _get_bisect_right(self, timestamp_datetime):
		"""
		returns index of DBData element at time point later as in given timestamp
		"""
		# our DBData elements are sorted by timestamp
		# =>we can use binary searching! There's already class "bisect" for this.
		# =>problem: using "bisect" is impossible, it can't handle DBData directly...: https://docs.python.org/2/library/bisect.html

		# =>now we adapt algorithm from it's source: https://hg.python.org/cpython/file/2.7/Lib/bisect.py
		# Find DBData ("bisect.bisect_right()")
		low = 0
		high = len(self._trendstruct.dbdata)
		while low < high:
			mid = (low + high) // 2
			if timestamp_datetime < self._trendstruct.dbdata[mid].get_datetime():
				high = mid
			else:
				low = mid + 1
		return low


class MetaTrendfile(object):
	"""
	provides all trenddata of a specific DMS datapoint from HDB files in project directory and backup directory
	"""
	def __init__(self, projectpath_str, dms_dp_str):
		self.projectpath_str = projectpath_str
		self.dms_dp_str = dms_dp_str
		self.dat_dir = os.path.join(projectpath_str, 'dat')
		self._get_backup_dir()
		self._get_trend_filename()

	def _get_backup_dir(self):
		# we have to read INI-file <projectpath>\cfg\PDBSBACK.CFG
		# and get this attribut:
		# [Backup]
		# Path=D:\Trend
		cfg_parser = configparser.ConfigParser()
		configfile_fullpath = os.path.join(self.projectpath_str, 'cfg', 'PDBSBACK.CFG')
		cfg_parser.read(configfile_fullpath)
		self.backup_dir = cfg_parser["Backup"]["Path"]

	def _get_trend_filename(self):
		# FIXME: I assume that many other characters gets replaced by "_" for getting a valid filename....
		# FIXME: It's a known problem that these datapoints stores trends in the SAME TRENDFILE (=>corrupted trend!!!)
		# FIXME: should we abort processing file if we can't find a file with DMS-DP-string in trendfile-header?
		#   MSR_U02:Test:L01_02:foo:Input
		#   MSR_U02:Test:L01:02:foo:Input
		#   MSR_U02:Test:L01:02_foo:Input
		#  ===>trenddata of all three TRD-datapoints were combined into file "MSR_U02_Test_L01_02_foo_Input.hdb" !!!

		# some help from http://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
		valid_chars = set(string.ascii_letters) ^ set(string.digits)
		char_list = []
		for char in self.dms_dp_str:
			if char in valid_chars:
				char_list.append(char)
			else:
				char_list.append('_')
		self.trend_filename_str = ''.join(char_list) + '.hdb'




def main(argv=None):
	for filename in ['C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\dat\MSR01_Allg_Aussentemp_Istwert.hdb']:
		trf = RawTrendfile(filename)
		print('RawTrendfile "' + filename + '" contains trenddata of DMS datapoint ' + trf.get_dms_Datapoint())
		print('number of DBData elements: ' + str(trf.get_nof_dbdata_elements()))
		print('timestamp of first DBData element: ' + trf.get_first_timestamp().strftime('%Y-%m-%d %H:%M:%S'))
		print('timestamp of last DBData element: ' + trf.get_last_timestamp().strftime('%Y-%m-%d %H:%M:%S'))
		print('(timespan is ' + str((trf.get_last_timestamp() - trf.get_first_timestamp()).days) + ' days)')

		# getting some values...
		# hint from http://stackoverflow.com/questions/4741243/how-to-pick-just-one-item-from-a-generator-in-python
		# =>we need to get another generator object when we want to get the same interation!
		for x in range(2):
			print('interpretation of values of some DBData elements: (run number ' + str(x) + ')')
			my_generator = trf.get_dbdata_elements_generator()
			for x in range(10):
				elem = my_generator.next()
				print('as boolean: ' + str(elem.get_value_as_boolean()) + '\tas int: ' + str(elem.get_value_as_int())+ '\tas float: ' + str(elem.get_value_as_float()))

		# getting trenddata by timestamp:
		timestamps_list = [datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=23),
		                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=24),
		                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=25),
		                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=13),
		                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=14),
		                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=15)]
		for timestamp in timestamps_list:
			print('getting DBData elements with timestamp "' + timestamp.strftime('%Y-%m-%d %H:%M:%S') + '"')
			result = trf.get_DBData_Timestamp_Search_Result(timestamp)
			print('\t"before_list" contains:')
			for item in result.before_list:
				print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))
			print('\t"exact_list" contains:')
			for item in result.exact_list:
				print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))
			print('\t"after_list" contains:')
			for item in result.after_list:
				print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))

	return 0  # success


if __name__ == '__main__':
    status = main()
    # disable closing of Notepad++
    # sys.exit(status)
