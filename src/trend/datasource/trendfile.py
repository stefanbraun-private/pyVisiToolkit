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
import calendar
from trend.datasource.dbdata import HighLevelDBData as DBData
from trend.datasource.dbdata import HighLevelDBData2 as DBData2
import configparser
import string
import re
import collections
import misc.timezone as timezone
import itertools
from operator import itemgetter

DEBUGGING = True


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

	# DBData could be ProMoS NT(c) version 1.x or version 2 =>choosing right version
	# trendfiles v1.x ends with ".hdb" , v2.x ends with ".hdbx"
	file_ext = file_fullpath.split('.')[-1]
	if file_ext.upper() == u'HDB':
		# using ProMoS NT(c) version 1.x
		curr_DBData_class = DBData
	else:
		# using ProMoS NT(c) version 2.x
		curr_DBData_class = DBData2
	nof_dbdata_elems = (filesize - TRENDDATA_OFFSET) / ctypes.sizeof(curr_DBData_class)

	class Trendfile_structure(ctypes.LittleEndianStructure):
		"""
		Header contains DMS datapoint name,
		data section contains all DBData elements, amount depends on filesize...
		"""
		# contains some hints from http://stackoverflow.com/questions/18536182/parsing-binary-data-into-ctypes-structure-object-via-readinto
		_fields_ = [
			("dmsDatapoint", ctypes.c_char * DMSDP_NOF_BYTES),                          # DMS datapoint name
			("UNKNOWN_BYTES", ctypes.c_char * (TRENDDATA_OFFSET - DMSDP_NOF_BYTES)),    # perhaps unused
			("dbdata", curr_DBData_class * nof_dbdata_elems)                            # array of DBData elements

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




class IndexedTrendfile(RawTrendfile):
	"""
	enhances a trendfile with OrderedDict as index:
	key: timestamp
	value: list of DBData elements with same timestamp

	second OrderedDict index allows retrieving of DBData-lists by its known position
	==>both index dictionaries MUST have same size!!!
	"""
	def __init__(self, fileFullpath):
		RawTrendfile.__init__(self, fileFullpath)
		self._indexed_by_timestamp = collections.OrderedDict()
		self._indexed_by_index = []

		# some statistics over DBData items
		# with help from http://stackoverflow.com/questions/10576548/python-usable-max-and-min-values
		self.minValue = -float("inf")
		self.maxValue = +float("inf")

		self._create_index()
		if DEBUGGING:
			print('constructor of IndexedTrendfile(): file "' + fileFullpath + '" is ready.')


	def _create_index(self):
		curr_list = []
		curr_timestamp = self.get_first_timestamp()
		for item in self._trendstruct.dbdata:
			# do some statistics, it's not much effort since we already process every item
			curr_val = item.get_value_as_float
			if curr_val < self.minValue:
				self.minValue = curr_val
			if curr_val > self.maxValue:
				self.maxValue = curr_val

			# append item to current list,
			# when there's a new timestamp build a new list
			if item.get_datetime() == curr_timestamp:
				curr_list.append(item)
			else:
				# indexing old DBData elements
				self._indexed_by_timestamp[curr_timestamp] = curr_list
				self._indexed_by_index.append(curr_list)
				# preparing new list
				curr_list = [item]
				curr_timestamp = item.get_datetime()
		# indexing last element
		if curr_timestamp not in self._indexed_by_timestamp:
			self._indexed_by_timestamp[curr_timestamp] = curr_list
			self._indexed_by_index.append(curr_list)
		assert len(self._indexed_by_timestamp) == len(self._indexed_by_index), 'both indexes MUST have same size!'


	def get_DBData_Timestamp_Search_Result(self, timestamp_datetime):
		"""
		returns an instance of DBData_Timestamp_Search_Result according to given timestamp
		=>first we try to get it directly from dictionary,
		alternative is binary searching.
		"""

		# DBData_Timestamp_Search_Result() has three lists of DBData elements:
		# begin and end of three lists don't overlap because they represent three different points in time:
		# [before_begin, ..., before_end] [exact_begin, ..., exact_end] [after_begin, ..., after_end]
		# (based on examples from https://docs.python.org/2/library/bisect.html )

		try:
			# try to get it directly from dictionary
			search_result = DBData_Timestamp_Search_Result()
			search_result.before_list = []
			search_result.exact_list = self._indexed_by_timestamp[timestamp_datetime]
			search_result.after_list = []
		except KeyError:
			# we have to binary search...
			search_result = DBData_Timestamp_Search_Result()

			# =>we adapted algorithm from this source: https://hg.python.org/cpython/file/2.7/Lib/bisect.py
			# Find list ("bisect.bisect_left()")
			low = 0
			high = len(self._indexed_by_index)
			while low < high:
				mid = (low + high) // 2
				dbdata_list = self._indexed_by_index[mid]
				if dbdata_list[0].get_datetime() < timestamp_datetime:
					low = mid + 1
				else:
					high = mid
			idx_after = low

			# now we have to interpret the given index:
			# FIXME: should we care for corrupted trendfiles? (e.g. an empty file would throw IndexError-exception...)
			if idx_after == 0:
				# timestamp_datetime is older than our trenddata
				search_result.before_list = []
				search_result.exact_list = []
				search_result.after_list = self._indexed_by_index[0]
			elif idx_after == len(self._indexed_by_index):
				# timestamp_datetime is younger than our trenddata
				search_result.before_list = self._indexed_by_index[-1]
				search_result.exact_list = []
				search_result.after_list = []
			else:
				# timestamp_datetime must be between timestamps in our trenddata
				search_result.before_list = self._indexed_by_index[idx_after - 1]
				search_result.exact_list = []
				search_result.after_list = self._indexed_by_index[idx_after]

		return search_result


	def get_dbdata_lists_generator(self):
		"""
		generate lists with DBData-elements grouped by timestamp
		(ProMoS NT(c) PDBS daemon stores them in sequence, so they should be sorted by timestamp)
		"""
		for curr_list in self._indexed_by_index:
			yield curr_list


	def get_dbdata_list_of_lists(self):
		"""
		return whole list containing lists with DBData-elements grouped by timestamp
		(ProMoS NT(c) PDBS daemon stores them in sequence, so they should be sorted by timestamp)
		"""
		return self._indexed_by_index

	def get_dbdata_timestamps_generator(self):
		"""
		return all contained timestamps
		(they should be in ascending order, ProMoS NT(c) PDBS daemon stores them in sequence in HDB files,
		and we put then into an OrderedDict)
		"""
		return self._indexed_by_timestamp.iterkeys()


class _Cached_Trendfile(object):
	"""Metadata and reference to a trendfile object, used by Trendfile_Cache_Handler()"""
	# code is adapted from "PSC_file_selector.py"
	def __init__(self, fullpath):
		self._fullpath = fullpath
		self._whole_file = None
		self._modification_time = 0
		self._filesize = 0
		self._last_readtime = -1

	def _read_metadata(self):
		stat = os.stat(self._fullpath)
		self._filesize = stat.st_size
		self._modification_time = stat.st_mtime

	def get_whole_file(self):
		self._read_metadata()
		if self._last_readtime <> self._modification_time:
			# first reading or file changed
			self._whole_file = IndexedTrendfile(self._fullpath)
			self._last_readtime = self._modification_time
		return self._whole_file

	def get_metadata(self):
		# examples from http://stackoverflow.com/questions/39359245/from-stat-st-mtime-to-datetime
		# and http://stackoverflow.com/questions/6591931/getting-file-size-in-python
		# and https://docs.python.org/2/library/stat.html
		# and http://stackoverflow.com/questions/455612/limiting-floats-to-two-decimal-points
		# and http://stackoverflow.com/questions/311627/how-to-print-date-in-a-regular-format-in-python
		self._read_metadata()
		size = float("{0:.2f}".format(self._filesize / 1024.0))
		mod_time = datetime.datetime.fromtimestamp(self._modification_time).strftime("%Y.%m.%d %H:%M:%S")
		return size, mod_time



class Trendfile_Cache_Handler(object):
	"""
	Holds trendfile objects in a cache for more efficiency
	=>currently it's one program-wide cache
	"""

	# class-variable with cache
	# =>using OrderedDict() so it's simple to maintain FIFO-cache
	# https://docs.python.org/2/library/collections.html#collections.OrderedDict
	_trendfile_cache_dict = collections.OrderedDict()
	used_cache_size = 0

	# soft-limit of maximum cache size
	CACHESIZE_KBYTES = 1024 * 50  # 50MBytes

	def get_trendfile_obj(self, filename_fullpath, cached=True):
		"""optional parameter 'cached': False means working on an isolated Trendfile without interfering other instance holders
		(it's possible that these DBData-lists could get corrupted, but I'm not 100% shure...)"""

		# maintain FIFO-cache: deleting oldest item if cache is too large
		curr_size = 0
		for trf in Trendfile_Cache_Handler._trendfile_cache_dict:
			size, mod_time = Trendfile_Cache_Handler._trendfile_cache_dict[trf].get_metadata()
			curr_size = curr_size + size
		while curr_size > Trendfile_Cache_Handler.CACHESIZE_KBYTES:
			# remove oldest item
			dumped_obj = Trendfile_Cache_Handler._trendfile_cache_dict.popitem(last=False)

		# handling request
		if cached:
			if not filename_fullpath in Trendfile_Cache_Handler._trendfile_cache_dict:
				# first time handling of this file...
				Trendfile_Cache_Handler._trendfile_cache_dict[filename_fullpath] = _Cached_Trendfile(filename_fullpath)
			return Trendfile_Cache_Handler._trendfile_cache_dict[filename_fullpath].get_whole_file()
		else:
			# bypass whole caching
			return IndexedTrendfile(filename_fullpath)




class MetaTrendfile(object):
	"""
	provides all trenddata of a specific DMS datapoint from HDB files in project directory and backup directory
	"""
	def __init__(self, projectpath_str, dms_dp_str):
		self.projectpath_str = projectpath_str
		self.dms_dp_str = dms_dp_str
		self.dat_dir = os.path.join(projectpath_str, 'dat')
		self.backup_dir = self._get_backup_dir()
		self.backup_subdirs_dict = self._find_backup_subdirs()   # stores subdir as string (key: tuple (year, month))
		self.trend_filename_str = self._get_trend_filename()
		self.trf_cache_handler = Trendfile_Cache_Handler()

	# timezone awareness (FIXME: currently fixed to 'Europe/Zurich')
	_tz = timezone.Timezone().get_tz()


	def _get_backup_dir(self):
		# we have to read INI-file <projectpath>\cfg\PDBSBACK.CFG
		# and get this attribut:
		# [Backup]
		# Path=D:\Trend
		cfg_parser = configparser.ConfigParser()
		configfile_fullpath = os.path.join(self.projectpath_str, 'cfg', 'PDBSBACK.CFG')
		cfg_parser.read(configfile_fullpath)
		return cfg_parser["Backup"]["Path"]

	def _get_trend_filename(self):
		# FIXME: I assume that all illegal characters in a DMS-datapoint gets replaced by "_" for getting a valid filename....
		# FIXME: It's a known problem that these datapoints stores trends in the SAME TRENDFILE (=>corrupted trend!!!)
		# FIXME: should we abort processing file if we can't find a file with the right DMS-DP-string in trendfile-header?
		#   MSR_U02:Test:L01_02:foo:Input
		#   MSR_U02:Test:L01:02:foo:Input
		#   MSR_U02:Test:L01:02_foo:Input
		#  ===>trenddata of all three TRD-datapoints were combined into file "MSR_U02_Test_L01_02_foo_Input.hdb" !!!

		# some help from http://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
		# =>now we restrict filename and hope PDBS does it the same way...
		valid_chars = set(string.ascii_letters) ^ set(string.digits)
		char_list = []
		for char in self.dms_dp_str:
			if char in valid_chars:
				char_list.append(char)
			else:
				char_list.append('_')
		return ''.join(char_list) + '.hdb'

	def _find_backup_subdirs(self):
		"""
		get a list of available backup subdirectories
		"""
		mydict = {}
		regex_pattern = r'Month_(?P<month>\d\d)\.(?P<year>\d\d\d\d)'
		for subdir in os.listdir(self.backup_dir):
			# an example for backup subdirectory:
			# february 2017: "Month_02.2017"

			m = re.match(regex_pattern, subdir)
			if m:
				# key in our dictionary: tuple (year, month) => value is whole regex match
				key = m.group('year'), m.group('month')
				mydict[key] = m.group(0)
		return mydict

	def _get_backup_subdir(self, timestamp_datetime):
		"""
		locate trenddata by timestamp
		"""
		# an example for backup subdirectory:
		# february 2017: "Month_02.2017"
		month = timestamp_datetime.strftime('%m')
		year = timestamp_datetime.strftime('%Y')
		return ''.join(['Month_', month, '.', year])


	def _get_endpoint_timestamp(self, position_str="first"):
		"""
		returns timestamp of our oldest or youngest DBData element,
		combined from dat- and backup directory.
		=>parameter position_str is either "first" or "last"
		("first" is default, anything other means "last")
		"""

		endpoint_timestamp_list = []
		try:
			# searching in project directory
			filename_fullpath = os.path.join(self.dat_dir, self.trend_filename_str)
			dat_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
			if os.path.exists(filename_fullpath):
				# processing this trendfile
				if position_str == "first":
					# getting oldest DBData
					found_timestamp = dat_trendfile.get_first_timestamp()
				else:
					# getting youngest DBData
					found_timestamp = dat_trendfile.get_last_timestamp()
				endpoint_timestamp_list.append(found_timestamp)
		except Exception as ex:
			print('WARNING: MetaTrendfile._get_endpoint_timestamp(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		try:
			# searching in backup subdirectory
			if position_str == "first":
				# searching oldest DBData =>ascending sorting
				reversed = False
			else:
				# searching youngest DBData =>descending sorting
				reversed = True
			filename_fullpath = ''
			for year, month in sorted(self.backup_subdirs_dict.keys(), reverse=reversed):
				subdir_str = self.backup_subdirs_dict[year, month]
				filename_fullpath = os.path.join(self.backup_dir, subdir_str, self.trend_filename_str)
				if os.path.exists(filename_fullpath):
					# we found a backup, it contains perhaps older trenddata than in project dir...
					break
			if filename_fullpath:
				bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
				if position_str == "first":
					# getting oldest DBData
					found_timestamp = bak_trendfile.get_first_timestamp()
				else:
					# getting youngest DBData
					found_timestamp = bak_trendfile.get_last_timestamp()
				endpoint_timestamp_list.append(found_timestamp)
		except Exception as ex:
			print('WARNING: MetaTrendfile._get_endpoint_timestamp(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		try:
			if position_str == "first":
				# getting oldest DBData
				return min(endpoint_timestamp_list)
			else:
				# getting youngest DBData
				return max(endpoint_timestamp_list)
		except ValueError:
			# seems we didn't found trenddata (list is empty)
			return None


	def get_first_timestamp(self):
		"""
		returns timestamp of our oldest DBData element
		"""
		return self._get_endpoint_timestamp(position_str="first")


	def get_last_timestamp(self):
		"""
		returns timestamp of our youngest DBData element
		"""
		return self._get_endpoint_timestamp(position_str="last")


	def get_DBData_Timestamp_Search_Result(self, timestamp_datetime):
		"""
		returns an instance of DBData_Timestamp_Search_Result according to given timestamp
		=>remember: every search must return either an exact match or the values just before and after it, except first or last DBData!
		"""

		# FIXME: this method is too heavy and should be optimized... =>rewrite it!!!
		search_result_list = []
		try:
			# searching in project directory
			filename_fullpath = os.path.join(self.dat_dir, self.trend_filename_str)
			if os.path.exists(filename_fullpath):
				dat_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
				search_result = dat_trendfile.get_DBData_Timestamp_Search_Result(timestamp_datetime)
				if search_result:
					search_result_list.append(search_result)
		except Exception as ex:
			print('WARNING: MetaTrendfile.get_DBData_Timestamp_Search_Result(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		try:
			# searching in backup directory:
			# first we try to get a "exact_list"-hit, then we
			# walk in both directions through directories and choose best match
			# for "file containing before_list" <= timestamp <= "file containing after_list"

			# trying specific timestamp
			# (following flags are preparation for further searching)
			bak_searching_past = True
			bak_searching_future = True
			curr_subdir = self._get_backup_subdir(timestamp_datetime)
			filename_fullpath = os.path.join(self.backup_dir, curr_subdir, self.trend_filename_str)
			if os.path.exists(filename_fullpath):
				bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
				search_result = bak_trendfile.get_DBData_Timestamp_Search_Result(timestamp_datetime)
				if search_result:
					# got a match... we need to decide how to search further...
					search_result_list.append(search_result)
					if search_result.exact_list:
						# no need to search further...
						bak_searching_past = False
						bak_searching_future = False
					elif search_result.before_list and not search_result.after_list:
						bak_searching_past = False
						bak_searching_future = True
					elif search_result.after_list and not search_result.before_list:
						bak_searching_past = True
						bak_searching_future = False
		except Exception as ex:
			print('WARNING: [1] MetaTrendfile.get_DBData_Timestamp_Search_Result(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		try:
			if bak_searching_past:
				# walking backwards through available directories
				for year, month in sorted(self.backup_subdirs_dict.keys(), reverse=True):
					backupdir_timestamp = datetime.datetime(year=int(year), month=int(month), day=1, tzinfo=MetaTrendfile._tz)
					if backupdir_timestamp < timestamp_datetime:
						subdir_str = self.backup_subdirs_dict[year, month]
						filename_fullpath = os.path.join(self.backup_dir, subdir_str, self.trend_filename_str)
						if os.path.exists(filename_fullpath):
							# we found a backup, it should contain DBData before timestamp...
							bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
							search_result = bak_trendfile.get_DBData_Timestamp_Search_Result(timestamp_datetime)
							if search_result:
								search_result_list.append(search_result)
								break
		except Exception as ex:
			print('WARNING: [2] MetaTrendfile.get_DBData_Timestamp_Search_Result(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		try:
			if bak_searching_future:
				# walking forward through available directories
				for year, month in sorted(self.backup_subdirs_dict.keys(), reverse=False):
					# with help from http://stackoverflow.com/questions/42950/get-last-day-of-the-month-in-python
					last_day_of_month = calendar.monthrange(int(year), int(month))[1]
					backupdir_timestamp = datetime.datetime(year=int(year), month=int(month), day=last_day_of_month, tzinfo=MetaTrendfile._tz)
					if backupdir_timestamp > timestamp_datetime:
						subdir_str = self.backup_subdirs_dict[year, month]
						filename_fullpath = os.path.join(self.backup_dir, subdir_str, self.trend_filename_str)
						if os.path.exists(filename_fullpath):
							# we found a backup, it should contain DBData after timestamp...
							bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
							search_result = bak_trendfile.get_DBData_Timestamp_Search_Result(timestamp_datetime)
							if search_result:
								search_result_list.append(search_result)
								break
		except Exception as ex:
			print('WARNING: [3] MetaTrendfile.get_DBData_Timestamp_Search_Result(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		# getting closest match from all search results
		# FIXME: should we care for mismatch between amount of stored DBData items for one timestamp in DAT and Backup?

		combined_sr = DBData_Timestamp_Search_Result()

		# first try: getting exact match
		if search_result_list:
			dbdata_set = set()
			for sr in search_result_list:
				if sr.exact_list:
					# using all DBData elements of all exact search results
					dbdata_set.update(sr.exact_list)
			if dbdata_set:
				# got exact search results... =>give a list back to caller
				combined_sr.exact_list = list(dbdata_set)
				assert combined_sr.exact_list and not combined_sr.before_list and not combined_sr.after_list, 'exact match for this timestamp expected!'
				return combined_sr

		# second try: getting match as close as possible from all available sources
		if search_result_list:
			# collecting closest timestamp-lists
			past_timestamp = datetime.datetime(year=1900, month=1, day=1, tzinfo=MetaTrendfile._tz)
			future_timestamp = datetime.datetime(year=2100, month=1, day=1, tzinfo=MetaTrendfile._tz)
			for sr in search_result_list:
				# nearest timestamp in the past ("before_list")
				if sr.before_list:
					curr_timestamp = sr.before_list[0].get_datetime()
					if curr_timestamp > past_timestamp:
						# found a closer match
						combined_sr.before_list = sr.before_list
						past_timestamp = curr_timestamp
					elif curr_timestamp == past_timestamp:
						# found result from other source => inserting DBData elements in case some were missing
						combined_sr.before_list.extend(sr.before_list)
				# nearest timestamp in the future ("after_list")
				if sr.after_list:
					curr_timestamp = sr.after_list[0].get_datetime()
					if curr_timestamp < future_timestamp:
						# found a closer match
						combined_sr.after_list = sr.after_list
						future_timestamp = curr_timestamp
					elif curr_timestamp == past_timestamp:
						# found result from other source => inserting DBData elements in case some were missing
						combined_sr.after_list.extend(sr.after_list)
		assert not combined_sr.exact_list, 'no exact match for this timestamp expected!'

		# get unique DBData elements
		dbdata_before_set = set(combined_sr.before_list)
		combined_sr.before_list = list(dbdata_before_set)

		dbdata_after_set = set(combined_sr.after_list)
		combined_sr.after_list = list(dbdata_after_set)
		return combined_sr


	def get_dbdata_lists_generator(self, start_datetime=None, end_datetime=None):
		"""
		a generator over all available trenddata for (perhaps) memory efficient retrieving lists with DBData elements,
		items with same timestamp are grouped
		(caller can only loop once through generator,
		read here: http://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python  )
		=>optional arguments allows filtering of DBData elements
		=>using something similar like "mergesort" algorithm: https://en.wikipedia.org/wiki/Merge_sort
		=>using "deque" objects for efficient popleft: https://docs.python.org/2/library/collections.html#collections.deque
		=>using uncached trendfile, since we MODIFY the internal DBData-lists
		"""
		# FIXME: do a cleaner implementation of this...

		# trenddata in project directory:
		# =>using one queue
		dat_deque = collections.deque()
		try:
			# trendfile in project directory:
			filename_fullpath = os.path.join(self.dat_dir, self.trend_filename_str)
			if os.path.exists(filename_fullpath):
				# disable cache because we alter DBData-list...!!
				dat_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=False)
				dat_deque = collections.deque(dat_trendfile.get_dbdata_list_of_lists())
		except Exception as ex:
			print('WARNING: MetaTrendfile.get_dbdata_lists_generator(): got exception "' + repr(ex) + '" while getting trend from "' + filename_fullpath + '"')

		# trenddata in backup subdirectories:
		# =>interpretation as one long queue, combined from different trendfiles
		# (no subclassing of deque since we don't want to implement all methods of deque()...)
		class _deque_wrapper(object):
			def __init__(self, backup_subdirs_dict, backup_dir, trend_filename_str, trf_cache_handler):
				self._deque_obj = collections.deque()
				self._backup_subdirs_dict = backup_subdirs_dict
				self._backup_dir = backup_dir
				self._trend_filename_str = trend_filename_str
				self.trf_cache_handler = trf_cache_handler
				self._subdir_iter = iter(sorted(backup_subdirs_dict.keys(), reverse=False))
				self._load_next_trendfile()

			def _load_next_trendfile(self):
				# "deque" is getting empty... trying to append next trendfile
				try:
					subdir_str = self._backup_subdirs_dict[self._subdir_iter.next()]
					filename_fullpath = os.path.join(self._backup_dir, subdir_str, self._trend_filename_str)
					if os.path.exists(filename_fullpath):
						# we found a backup file
						# disable cache because we alter DBData-list...!!
						bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=False)
						self._deque_obj.extend(bak_trendfile.get_dbdata_list_of_lists())
				except StopIteration:
					# there are no more backup subdirs to check...
					pass

			def popleft(self):
				# make shure this class contains enough trenddata, then return next element
				# (if we let deque ran out of elements then statement "if bak_deque" will fail)
				if len(self._deque_obj) <= 1:
					# "deque" is empty... trying to append next trendfile
					self._load_next_trendfile()
				return self._deque_obj.popleft()

			def __len__(self):
				# overriding this hook method for allowing getting current size of deque object
				# (with help from http://stackoverflow.com/questions/15114023/using-len-and-def-len-self-to-build-a-class
				#  and http://stackoverflow.com/questions/7816363/if-a-vs-if-a-is-not-none
				# )
				return len(self._deque_obj)


		bak_deque = _deque_wrapper(self.backup_subdirs_dict, self.backup_dir, self.trend_filename_str, self.trf_cache_handler)

		# checking tail of both deques and return list with unique DBData elements at oldest timestamp
		# =>do until we returned all available trenddata
		dat_list = []
		bak_list = []
		while True:
			# get DBData-list from each tail
			curr_list = []
			if dat_deque and bak_deque:
				# both trenddata source available...
				# =>only get new items when there's nothing left from earlier round
				if not dat_list:
					dat_list = dat_deque.popleft()
				if not bak_list:
					bak_list = bak_deque.popleft()

				# return older items to caller
				# if we have same timestamp then we collect all unique DBData element
				dat_timestamp = dat_list[0].get_datetime()
				bak_timestamp = bak_list[0].get_datetime()
				if bak_timestamp < dat_timestamp:
					curr_list = bak_list
					bak_list = []
				elif dat_timestamp < bak_timestamp:
					curr_list = dat_list
					dat_list = []
				else:
					my_set = set(dat_list + bak_list)
					curr_list = list(my_set)
					dat_list = []
					bak_list = []
			elif dat_deque:
				# only trenddata in project directory available...
				curr_list = dat_deque.popleft()
			elif bak_deque:
				# only trenddata in backup directory available...
				curr_list = bak_deque.popleft()
			else:
				# no more trenddata left...
				curr_list = []

			if curr_list:
				# check filter
				ignore = False
				if start_datetime:
					if curr_list[0].get_datetime() < start_datetime:
						ignore = True
				if end_datetime:
					if curr_list[0].get_datetime() > end_datetime:
						ignore = True
						# nothing to do, stop iteration
						break
				if not ignore:
					yield curr_list
			else:
				# nothing to do, stop iteration
				break


	def get_search_result_generator(self, start_datetime=None, stop_datetime=None):
		"""
		a generator creating DBData_Timestamp_Search_Result objects with all available trenddata as exact-list
		(reusing all DBData lists from get_dbdata_lists_generator()
		"""
		for curr_list in self.get_dbdata_lists_generator(start_datetime, stop_datetime):
			sr = DBData_Timestamp_Search_Result()
			# returning this list of DBData elements as exact search hit
			sr.exact_list.extend(curr_list)
			yield sr


	def get_dbdata_timestamps_generator(self, start_datetime=None, stop_datetime=None):
		"""
		a generator creating objects with timestamps and time difference to last timestamp of all available trenddata
		(contains some copied code from "self.get_DBData_Timestamp_Search_Result(self, timestamp_datetime()" )
		"""

		# getting generators of all timestamp sources,
		# then always yield the oldest timestamp of all active timestamp sources


		# helper class for combining timestamp and time difference
		class Tstamp(object):
			"""
			tstamp: timestamp as datetime.datetime object
			diff: difference to last timestamp in seconds
			"""
			old_tstamp_dt = None

			def __init__(self, curr_tstamp_dt):
				self.tstamp_dt = curr_tstamp_dt
				self.is_interpolated = False
				if not Tstamp.old_tstamp_dt:
					# first run =>first timestamp is always okay and should have timediff = 0
					self.timediff = 0.0
				else:
					self.timediff = (curr_tstamp_dt - Tstamp.old_tstamp_dt).total_seconds()
				Tstamp.old_tstamp_dt = curr_tstamp_dt


		if not start_datetime:
			start_datetime = datetime.datetime.fromtimestamp(0, tz=MetaTrendfile._tz)
		if not stop_datetime:
			stop_datetime = datetime.datetime(year=3000, month=1, day=1).replace(tzinfo=MetaTrendfile._tz)

		prj_iter = iter([])
		# trenddata in project directory
		filename_fullpath = os.path.join(self.dat_dir, self.trend_filename_str)
		if os.path.exists(filename_fullpath):
			dat_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
			usable = True
			if dat_trendfile.get_last_timestamp() < start_datetime:
				# trenddata is too old
				usable = False
			if dat_trendfile.get_first_timestamp() > stop_datetime:
				# trenddata is too new
				usable = False
			if usable:
				prj_iter = dat_trendfile.get_dbdata_timestamps_generator()

		# lazily generating timestamp iterators from backup
		# (idea from http://stackoverflow.com/questions/15004772/what-is-the-difference-between-chain-and-chain-from-iterable-in-itertools )
		def generate_backup_iterators():
			# walking forward through available directories
			for year, month in sorted(self.backup_subdirs_dict.keys(), reverse=False):
				if int(year) >= start_datetime.year and int(month) >= start_datetime.month and \
					int(year) <= stop_datetime.year and int(month) <= stop_datetime.month:
					# current backup directory should contain trenddata in requested timerange
					subdir_str = self.backup_subdirs_dict[year, month]
					filename_fullpath = os.path.join(self.backup_dir, subdir_str, self.trend_filename_str)
					if os.path.exists(filename_fullpath):
						# we found a backup, it should contain trenddata...
						bak_trendfile = self.trf_cache_handler.get_trendfile_obj(filename_fullpath, cached=True)
						yield bak_trendfile.get_dbdata_timestamps_generator()

		# combine this generator of generators with trenddata from project
		bak_iter = itertools.chain.from_iterable(generate_backup_iterators())

		tstamp_generator_list = []
		for source in [prj_iter, bak_iter]:
			try:
				# this list always contains head element from iterator, and iterator itself
				new_source = [source.next(), source]
				tstamp_generator_list.append(new_source)
			except StopIteration:
				pass

		# request items from both generators, always returning smaller value
		while tstamp_generator_list:
			# consuming timestamps, returning always oldest one, updating first element
			# sorting list of tuples: http://stackoverflow.com/questions/10695139/sort-a-list-of-tuples-by-2nd-item-integer-value
			# =>getting source list with oldest timestamp
			tstamp_generator_list = sorted(tstamp_generator_list, key=itemgetter(0))
			oldest_source_list = tstamp_generator_list[0]
			curr_tstamp, curr_iter = oldest_source_list[0], oldest_source_list[1]

			if curr_tstamp >= start_datetime and curr_tstamp <= stop_datetime:
				yield Tstamp(curr_tstamp)

			try:
				# update head-element of current timestamp source
				oldest_source_list[0] = curr_iter.next()
			except StopIteration:
				# iterator is empty... =>removing this timestamp-source
				tstamp_generator_list = tstamp_generator_list[1:]



def main(argv=None):
	# for filename in ['C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\dat\MSR01_Allg_Aussentemp_Istwert.hdb']:
	# 	#trf = RawTrendfile(filename)
	# 	trf = IndexedTrendfile(filename)
	# 	print('IndexedTrendfile "' + filename + '" contains trenddata of DMS datapoint ' + trf.get_dms_Datapoint())
	# 	print('number of DBData elements: ' + str(trf.get_nof_dbdata_elements()))
	# 	print('number of unique timestamps: ' + str(len(trf._indexed_by_timestamp)))
	# 	print('timestamp of first DBData element: ' + trf.get_first_timestamp().strftime('%Y-%m-%d %H:%M:%S'))
	# 	print('timestamp of last DBData element: ' + trf.get_last_timestamp().strftime('%Y-%m-%d %H:%M:%S'))
	# 	print('(timespan is ' + str((trf.get_last_timestamp() - trf.get_first_timestamp()).days) + ' days)')
	#
	# 	# getting some values...
	# 	# hint from http://stackoverflow.com/questions/4741243/how-to-pick-just-one-item-from-a-generator-in-python
	# 	# =>we need to get another generator object when we want to get the same interation!
	# 	for x in range(2):
	# 		print('interpretation of values of some DBData elements: (run number ' + str(x) + ')')
	# 		my_generator = trf.get_dbdata_elements_generator()
	# 		for x in range(10):
	# 			elem = my_generator.next()
	# 			print('as boolean: ' + str(elem.get_value_as_boolean()) + '\tas int: ' + str(elem.get_value_as_int())+ '\tas float: ' + str(elem.get_value_as_float()))
	#
	# 	# getting trenddata by timestamp:
	# 	timestamps_list = [datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=23),
	# 	                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=24),
	# 	                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=25),
	# 	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=13),
	# 	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=14),
	# 	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=15)]
	# 	for timestamp in timestamps_list:
	# 		print('getting DBData elements with timestamp "' + timestamp.strftime('%Y-%m-%d %H:%M:%S') + '"')
	# 		result = trf.get_DBData_Timestamp_Search_Result(timestamp)
	# 		print('\t"before_list" contains:')
	# 		for item in result.before_list:
	# 			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))
	# 		print('\t"exact_list" contains:')
	# 		for item in result.exact_list:
	# 			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))
	# 		print('\t"after_list" contains:')
	# 		for item in result.after_list:
	# 			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()))

	# trying backup and projekt directory:
	print('######################################################################')
	print('\nTEST: MetaTrendfile() ')
	mytrf = MetaTrendfile('C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse', 'MSR01:Allg:Aussentemp:Istwert')
	print('get_first_timestamp(): ' + repr(mytrf.get_first_timestamp()))
	print('get_last_timestamp(): ' + repr(mytrf.get_last_timestamp()))

	# getting trenddata by timestamp:
	timestamps_list = [datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=23, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=24, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=25, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=13, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=14, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=15, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=1950, month=1, day=1, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz),
	                   datetime.datetime(year=2999, month=1, day=1, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)
						]
	for timestamp in timestamps_list:
		print('getting DBData elements with timestamp "' + timestamp.strftime('%Y-%m-%d %H:%M:%S') + '"')
		result = mytrf.get_DBData_Timestamp_Search_Result(timestamp)
		print('\t"before_list" contains:')
		for item in result.before_list:
			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()) + ' / ' + item.getStatusBitsString())
		print('\t"exact_list" contains:')
		for item in result.exact_list:
			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()) + ' / ' + item.getStatusBitsString())
		print('\t"after_list" contains:')
		for item in result.after_list:
			print('\t\t' + item.get_datetime().strftime('%Y-%m-%d %H:%M:%S') + ' / ' + str(item.get_value_as_float()) + ' / ' + item.getStatusBitsString())

	# test filtering identical timestamps
	print('\n\ntest filtering identical timestamps')
	print('######################################')
	filename_fullpath = r'C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\dat\MSR01_Allg_Aussentemp_Istwert_LAST_VALUE.hdb'
	#trf_test = IndexedTrendfile()
	# TESTING cache:
	trf_test = Trendfile_Cache_Handler().get_trendfile_obj(filename_fullpath, cached=True)
	print('DMS-datapoint= ' + trf_test.get_dms_Datapoint())
	print('\tcontained DBData-elements:')
	for curr_dbdata in trf_test.get_dbdata_elements_generator():
		print('\ttimestamp: ' + repr(curr_dbdata.get_datetime()))
		print('\tvalue: ' + str(curr_dbdata.get_value_as_float()))
		print('\thash()= ' + str(hash(curr_dbdata)))
	print('\n\tDBData-elements retrieved as set():')
	for curr_dbdata in trf_test.get_dbdata_elements_as_set():
		print('\ttimestamp: ' + repr(curr_dbdata.get_datetime()))
		print('\tvalue: ' + str(curr_dbdata.get_value_as_float()))
		print('\thash()= ' + str(hash(curr_dbdata)))

	# test number of unique timestamps
	print('\n\ntest number of unique timestamps')
	print('#####################################')
	timespans = [#(None, None),
	            (datetime.datetime(year=2013, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2014, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
				(datetime.datetime(year=2014, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2015, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
				(datetime.datetime(year=2015, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2016, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
				(datetime.datetime(year=2016, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2017, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
				(datetime.datetime(year=2017, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2018, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
	            (datetime.datetime(year=2013, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2020, month=1, day=6, hour=0, minute=0, second=0, tzinfo=MetaTrendfile._tz)),
	            (datetime.datetime(year=2016, month=1, day=6, hour=4, minute=27, second=24, tzinfo=MetaTrendfile._tz), datetime.datetime(year=2017, month=2, day=6, hour=20, minute=15, second=14, tzinfo=MetaTrendfile._tz))]
	for start, end in timespans:
		try:
			print('\tbetween ' + start.strftime('%Y-%m-%d %H:%M:%S') + ' and  ' + end.strftime('%Y-%m-%d %H:%M:%S') + ':')
		except AttributeError:
			# this is testcase with (None, None)
			print('\tin all available trenddata:')
		x = 0
		for item in mytrf.get_dbdata_lists_generator(start, end):
			x = x + 1
		print('\t\t=>' + str(x) + ' unique timestamps.')


	# testing MetaTrendfile.get_dbdata_timestamps_generator()
	print('\n\ntesting MetaTrendfile.get_dbdata_timestamps_generator()')
	print('**********************************************************')
	curr_trf = MetaTrendfile(r'C:\Promos15\proj\Foo', 'NS_MSR01a:H01:AussenTemp:Istwert')
	with open(r'd:\foo_Aussentemp.csv', "w") as f:
		for tstamp in curr_trf.get_dbdata_timestamps_generator(
				start_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=0, tzinfo=MetaTrendfile._tz),
				stop_datetime=datetime.datetime(year=2017, month=2, day=6, hour=0, minute=0, tzinfo=MetaTrendfile._tz)
		):
			tstamp_str = str(tstamp.tstamp_dt)
			timediff_str = str(tstamp.timediff)
			f.write(';'.join([tstamp_str, timediff_str]) + '\n')


	return 0  # success


if __name__ == '__main__':
    status = main()
    # disable closing of Notepad++
    # sys.exit(status)
