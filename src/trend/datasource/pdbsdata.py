#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.pdbsdata.py

PDBSData()
a structure used as result when retrieving protocol-data from PDBS service.

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import ctypes
import re


class PDBSData(ctypes.Structure):
	"""
	Structure to hold one record of a protocol file
	=>when retrieving records by "pdbs.dll" then only these fields contains values:
	  -timestamp
	  -milliseconds
	  -DMS datapoint name
	  -protocol text

	Results of tests in "pdbs.py"
	=>Hmm, layout of PDBSData is possibly different to documentation,
		  buffersize for successful DLL call in tests:
		    257Bytes (1 record) =>256Bytes is too small ===>using 257Bytes seems stable

	Layout of structure:
	1th byte to 4th byte: timestamp (int) as seconds since 1970
	5th byte to 8th byte: unknown, perhaps milliseconds as int (according documentation)
	9th byte perhaps up to 91th byte: DMS datapoint name (assumption 80 bytes, plus 3 bytes extra according documentation, NUL terminated)
	92th byte to 96th byte: unknown, perhaps status as int (according documentation), but unknown meaning
	97th byte to 249th byte: protocol text (153bytes according documentation)
	249th byte to 256th byte: unknown, perhaps group and priority as int (according documentation) =>but one more byte is needed!!!
	"""


	############# FIXME: WARNING: THESE STRUCTURE DEFINITION IS BASED ON TRIAL AND ERROR, MODIFY THEM WITH CARE!!!
	# =>ONLY THESE FACTS ARE PROVED:
	# "reftime" is an 4 byte integer timestamp
	# DMS datapoint name starts at byte 9
	# protocol text starts at byte 97
	# =>total length of structure is 254 bytes, when changing size then "Pdbs.pyPDBS_GetBulkData()" will return garbage!!!

	DMSDP_NOF_BYTES = 83
	TEXT_NOF_BYTES = 153

	_fields_ = [("reftime", ctypes.c_uint),                     # timestamp (unix epoche)
				("UNKNOWN_BYTES1", ctypes.c_char * 4),          # milliseconds?
				("dmsName", ctypes.c_char * DMSDP_NOF_BYTES),   # DMS datapoint name
				("UNKNOWN_BYTES2", ctypes.c_char * 5),          # status?
				("text", ctypes.c_char * TEXT_NOF_BYTES),       # protocol text
				("UNKNOWN_BYTES3", ctypes.c_char * 5)           # group? priority?
				]


	def parse_text(self, formatstr):
		"""
		Get values from protocol (variable "text") as dictionary
		=>call this function with the used Visi.Plus "PRTFormat" string,
		  you have to get it from DMS under key "....:PRT:Format" of the logged DMS datapoint

		example:
		"Mani1@#c #N #V^NAME #VComment #z(Ein:Aus) #u"

		(If you open an alarm protocol file ("Alarm.pdb"), then formatstring is stored under ":ALM:Alarm1:Format",
		example:
		"Alarm1@#c #V^NAME #VComment #T #Z(kommt:geht:Err_Quit) #u"
		)
		"""

		prot_text = self.text
		parts_dict = {}


		return parts_dict