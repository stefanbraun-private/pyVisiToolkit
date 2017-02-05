#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.pdbs.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import ctypes
import os
import time
import misc.visi_binaries

import trend.datasource.dbdata
import trend.datasource.trendfile
import trend.datasource.pdbsdata

DEBUGGING = True

class Pdbs(object):
	def __init__(self, pc_name_str='.'):
		# FIXME: how to handle execution on systems without Visi.Plus(c)? ...
		dll_path = misc.visi_binaries.get_fullpath()
		if DEBUGGING:
			print('dll_path=' + dll_path)
		os.chdir(dll_path)
		self.pmospipe = ctypes.windll.LoadLibrary('pdbs.dll')

		self.pmospipe.PdbsConnect.argtypes = [ctypes.c_char_p]
		self.pmospipe.PdbsConnect.restype = ctypes.c_int
		self.handle = self.pmospipe.PdbsConnect(pc_name_str)
		assert self.handle != 0, u'unable to connect to PDBS on host "' + pc_name_str + u'", is Visi.Plus(c) running?'
		if DEBUGGING:
			print('self.handle = ' + str(self.handle))

	def __del__(self):
		self.pmospipe.PdbsDisconnect.argtypes = [ctypes.c_int]
		self.pmospipe.PdbsDisconnect.restype = ctypes.c_bool
		self.pmospipe.PdbsDisconnect(self.handle)

	def pyPdbsGetCount(self, dmsname_str, start_time_int, end_time_int):
		self.pmospipe.PdbsGetCount.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
		self.pmospipe.PdbsGetCount.restype = ctypes.c_int
		return self.pmospipe.PdbsGetCount(self.handle, dmsname_str, start_time_int, end_time_int)

	def pyPdbsGetData(self, dmsname_str, start_time_int, end_time_int, count_int):
		"""
		PdbsGetData()
			Retrieving historical trenddata from PDBS from these sources:
			-up to one month stored by HDAMng (..\dat\*.hdb)
			-longtime backup stored by PDBS (..\Trend\Month_mm.yyyy)

			=>observed behaving of this DLL-function:
				-amount of returned items seems "max(1, pyPdbsGetCount()) + 1"
				-first and last valid items are previous and next items OUTSIDE search window
				-second, and second last valid item: first and last items INSIDE search window
				-then min and max value in every timeslot

				-search window size FIXME
				-4 valid items when we have trend data but no search hit for this search window or search window is negative
				-5 valid items when starttime and endtime is set to an existing timestamp of one trenddata item
				-no valid items (only "STATUS_END") when count_int is 0
				-if there were two identical timestamps in trendfile, then in search result there's only one hit
				-often amount of items is lesser than pyPdbsGetCount()
				-the timestamps were usually ordered (exception: when it returns 4 or 5 valid items)
				-sometimes there are identical items
				-the last returned item has always status "STATUS_END"

			parameters:
			dmsname_str     DMS-key
			start_time_int  range start of trenddata search (in sec since 1.1.1970)
			end_time_int    range end of trenddata search (in sec since 1.1.1970)
			count_int       amount of wished trenddata =>if there exists more items than count_int,
							then PDBS should return 2 * count_int trenddata (min and max in every timeslot)
		"""

		arr_size = max(4, self.pyPdbsGetCount(dmsname_str, start_time_int, end_time_int)) + 1


		# FIXME: perhaps implement Array as in http://stackoverflow.com/questions/1444159/how-to-read-a-structure-containing-an-array-using-pythons-ctypes-and-readinto
		# FIXME: using that in trendfile.py?
		# FIXME: example: https://www.daniweb.com/programming/software-development/threads/351774/passing-pointer-to-array-of-structures-in-ctypes

		# code based on http://stackoverflow.com/questions/16704408/python-ctypes-populate-an-array-of-structures
		self.pmospipe.PdbsGetData.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(
			trend.datasource.dbdata.DBData)]
		self.pmospipe.PdbsGetData.restype = ctypes.c_int
		trenddata_arr = (trend.datasource.dbdata.DBData * arr_size)()
		nof_trenddata = self.pmospipe.PdbsGetData(self.handle, str(dmsname_str), int(start_time_int), int(end_time_int), int(count_int), trenddata_arr)

		trenddata_list = []
		for item in trenddata_arr:
			curr_trenddata = trend.datasource.dbdata.DBData()
			curr_trenddata.setVariables(item.timestamp, item.value, item.status)
			if curr_trenddata.getStatusFlagsString() != 'STATUS_END' and curr_trenddata.getStatusFlagsString() != '':
				trenddata_list.append(curr_trenddata)
			else:
				# found last item, all remaining items are empty
				break

		if DEBUGGING:
			print('arr_size == ' + str(arr_size) + ', nof_trenddata == ' + str(nof_trenddata))

			for item in trenddata_list:
				print('current trenddata: timestamp=' + str(item.getTimestamp()) + '(' + time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(item.getTimestamp())) + ')' +
					   ', value='+str(item.getValue()) + ', status=' + item.getStatusFlagsString())

		return trenddata_list


	def pyPDBS_GetBulkData(self, filename_str, pos_int, count_int):
		"""
		PDBS_GetBulkData()
			Get protocol data, inserted by protocol manager (PrtMng).
		Parameters:
			filename_str:   filename of protocol file, *.pdb in project directory ("...\dat\*.pdb")
			pos_int:        startposition in file (number of first protocol record, counting begins with 0)
			                (=>when called with higher number than available records, then the last one is returned)
			count_int:      number of protocol records to retrieve
		return value:
			list of PDBSData-objects

		=>Hmm, layout of PDBSData is possibly different to documentation,
		  buffersize for successful DLL call in tests:
		    257Bytes (1 record) =>256Bytes is too small ===>using 257Bytes seems stable
		    345Bytes (1 record)
		    761Bytes (2 records)
		    1009Bytes (3 records)
		  sometimes DLL call hangs when called with 500Bytes buffer
		"""

		######### getting raw bytebuffer for reverse engineering of PDBSData structure...
		# # DEBUGGING: How does structure PDBSData look like? Is it right documented?
		# REC_SIZE = 257
		# self.pmospipe.PDBS_GetBulkData.argtypes = [ctypes.c_int,  ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_char * REC_SIZE)]
		# self.pmospipe.PDBS_GetBulkData.restype = ctypes.c_int
		# curr_rec = ctypes.create_string_buffer(REC_SIZE)
		# result_int = self.pmospipe.PDBS_GetBulkData(self.handle, filename_str, pos_int, count_int, ctypes.byref(curr_rec))
		# return (result_int, curr_rec)


		# Create buffer for DLL function (last PDBSData is reserved for strange extra bytes written by DLL function)
		PDBSDataArray = trend.datasource.pdbsdata.PDBSData * (count_int + 1)
		data_arr = PDBSDataArray()
		self.pmospipe.PDBS_GetBulkData.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(PDBSDataArray)]
		self.pmospipe.PDBS_GetBulkData.restype = ctypes.c_int
		result_int = self.pmospipe.PDBS_GetBulkData(self.handle, filename_str, pos_int, count_int, ctypes.byref(data_arr))

		print('ctypes.sizeof(trend.datasource.pdbsdata.PDBSData)=' + str(ctypes.sizeof(trend.datasource.pdbsdata.PDBSData)))
		print('ctypes.sizeof(PDBSDataArray)=' + str(ctypes.sizeof(PDBSDataArray)))
		print('len(data_arr)=' + str(len(data_arr)))

		records_list = []
		for x in range(result_int):
			records_list.append(data_arr[x])
		return records_list

		##### following tests were not successfull...
		# # FIXME: How to simplify getting buffer-bytes into a list of PDBSData objects?!? Now we call the DLL once per protocol entry... :-(
		# self.pmospipe.PDBS_GetBulkData.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(trend.datasource.pdbsdata.PDBSData)]
		# self.pmospipe.PDBS_GetBulkData.restype = ctypes.c_int
		#
		# records_list = []
		# for x in range(count_int):
		# 	one_rec = trend.datasource.pdbsdata.PDBSData()
		# 	print('DEBUGGING: calling DLL with pos_int=' + str(pos_int + x) + ', count_int=' + str(1))
		# 	result_int = self.pmospipe.PDBS_GetBulkData(self.handle, filename_str, pos_int + x, 1, ctypes.byref(one_rec))
		# 	records_list.append(one_rec)


		# # FIXME: How to simplify getting buffer-bytes into a list of PDBSData objects?!?
		# recordsize = ctypes.sizeof(trend.datasource.pdbsdata.PDBSData)
		# buffersize = recordsize * count_int
		# my_buffer = ctypes.create_string_buffer(buffersize)
		# self.pmospipe.PDBS_GetBulkData.argtypes = [ctypes.c_int,  ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_char * buffersize)]
		# self.pmospipe.PDBS_GetBulkData.restype = ctypes.c_int
		# result_int = self.pmospipe.PDBS_GetBulkData(self.handle, filename_str, pos_int, count_int, ctypes.byref(my_buffer))
		#
		# records_list = []
		# for x in range(count_int):
		# 	curr_rec = trend.datasource.pdbsdata.PDBSData()
		# 	ctypes.memmove(ctypes.byref(curr_rec), ctypes.byref((ctypes.byref(my_buffer) + x), recordsize))
		# 	records_list.append(curr_rec)
		# return (result_int, records_list)




	def pvPDBS_GetCount(self, filename_str):
		"""
		PDBS_GetCount()
			Get number of PDBSData records in file
		params:
			filename_str    file with protocol data

		return values:
			True (file is open)
			False (file is closed)
		"""
		self.pmospipe.PDBS_GetCount.argtypes = [ctypes.c_int, ctypes.c_char_p]
		self.pmospipe.PDBS_GetCount.restype = ctypes.c_int
		nof_records = self.pmospipe.PDBS_GetCount(self.handle, filename_str)
		return nof_records


def main(argv=None):

	dms_dp_name = 'MSR01:Allg:Aussentemp:Istwert'
	currPdbs = Pdbs()

	# endtime = int(time.time())
	# #starttime = int(endtime - 1 * 10**6)
	# #endtime = int(time.time())
	# #starttime = 1452988800
	# #endtime = 1453075200
	#
	# print('searchWindow' + '\t' + 'nofTrends' + '\t' + 'curr_trenddata_list')
	# for searchWindow in range(1*10**5, 10*10**5, 1*10**5):
	#     starttime = int(endtime - searchWindow)
	#     try:
	#         nofTrends = currPdbs.pyPdbsGetCount(dms_dp_name, starttime, endtime)
	#         curr_trenddata_list = curr_trenddata_list = currPdbs.pyPdbsGetData(dms_dp_name, starttime, endtime, 9*10**4)
	#     except MemoryError:
	#         nofTrends = 0
	#         curr_trenddata_list = 0
	#         currPdbs = None
	#         currPdbs = Pdbs()
	#     print(str(searchWindow) + '\t' + str(nofTrends) + '\t' + str(len(curr_trenddata_list)))
	#
	# nofTrends = currPdbs.pyPdbsGetCount(dms_dp_name, starttime, endtime)
	# print('nofTrends is ' + str(nofTrends))
	#
	# curr_trenddata_list = currPdbs.pyPdbsGetData(dms_dp_name, starttime, endtime, nofTrends)
	# print('curr_trenddata_list contains ' + str(len(curr_trenddata_list)) + ' trenddata items')

	print('DEBUGGING: ctypes.sizeof(trend.datasource.pdbsdata.PDBSData) = ' + str(ctypes.sizeof(trend.datasource.pdbsdata.PDBSData)))

	curr_protocol = 'Login.pdb'
	#curr_protocol = 'Alarm.pdb'
	#curr_protocol = 'Manip1.pdb'
	nof_records = currPdbs.pvPDBS_GetCount(curr_protocol)
	print('nof_records = ' + str(nof_records) + ' ,' + str(type(nof_records)))

	# get the last 10 records
	records = currPdbs.pyPDBS_GetBulkData(curr_protocol, nof_records - 10, 10)
	print('nof records returned by pyPDBS_GetBulkData(): ' + str(len(records)))
	for index, one_rec in enumerate(records):
		print('Record ' + str(index) + ' contains text "' + one_rec.text + '"')
	print('')
	for index, one_rec in enumerate(records):
		print('Record ' + str(index) + ' contains DMS datapoint "' + one_rec.dmsName + '"')
	return 0        # success


if __name__ == '__main__':
	status = main()