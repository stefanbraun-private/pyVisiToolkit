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
from trend.datasource.dbdata import HighLevelDBData as DBData

DEBUGGING = False


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

	def get_dbdata_elements(self):
		"""
		a generator for retrieving DBData elements
		"""
		# FIXME: implement some filtering (same as in "trendfile.py.old", e.g. retrieving only data of a specific timespan)
		for elem in self._trendstruct.dbdata:
			yield elem


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
		my_generator = trf.get_dbdata_elements()
		print('interpretation of values of some DBData elements:')
		for x in range(10):
			elem = my_generator.next()
			print('as boolean: ' + str(elem.get_value_as_boolean()) + '\tas int: ' + str(elem.get_value_as_int())+ '\tas float: ' + str(elem.get_value_as_float()))

	return 0  # success


if __name__ == '__main__':
    status = main()
    # disable closing of Notepad++
    # sys.exit(status)
