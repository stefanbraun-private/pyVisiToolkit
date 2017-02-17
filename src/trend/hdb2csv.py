#!/usr/bin/env python
# encoding: utf-8
"""
trend.hdb2csv.py

Quick and dirty tool: Converting raw trendfiles (*.hdb) to CSV
(contains some codeparts from trend.datasource.trendfile.py
FIXME: do some refactoring, build reusable code...)

Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


from trend.datasource.dbdata import DBData
from trend.datasource.trendfile import RawTrendfile
import struct
import time
import argparse


DEBUGGING = True


class Converter(object):
	def __init__(self, hdb_filename, csv_filename):
		self._hdb_filename = hdb_filename
		self._csv_filename = csv_filename
		self._DBData_list = []

	def convert(self):
		curr_trf = RawTrendfile(self._hdb_filename)
		with open(self._csv_filename, "w") as f:
			# write headerline
			header_cells = ["Datum/Zeit", curr_trf.get_dms_Datapoint(), "Status"]

			# if available insert statusbit names instead of their bitnumber
			DBData.load_statusbit_class()
			all_statusbits_list = DBData.Statusbit_class().get_statusbits_namelist()
			if not all_statusbits_list:
				all_statusbits_list = DBData.Statusbit_class().get_statusbits_unnamedlist()
			for bit in all_statusbits_list:
				header_cells.append(bit)
			f.write(';'.join(header_cells))
			f.write('\n')

			for item in curr_trf.get_dbdata_elements():
				# help from http://stackoverflow.com/questions/12400256/python-converting-epoch-time-into-the-datetime
				timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item.getTimestamp()))
				value_str = str(item.getValue())
				status_str = str(item.getStatus())
				curr_row = [timestamp_str, value_str, status_str]

				# add statusbits one bit per cell
				curr_statusbits = item.get_statusbits_set()
				for bit in all_statusbits_list:
					if bit in curr_statusbits:
						curr_row.append("1")
					else:
						curr_row.append("")
				f.write(';'.join(curr_row))
				f.write('\n')


def main(argv=None):

	DIR = r'D:\Trenddaten\Month_02.2017'
	job_list = [(r'NS_MSR01a_H01_AussenTemp_Istwert.hdb', 'H01_AussenTemp'),
	            (r'NS_MSR01a_H01_ErdsAustrTempEinb_Istwert.hdb', 'H01_ErdsAustrTempEinb'),
	            (r'NS_MSR01a_H01_ErdsEintrTempEinb_Istwert.hdb', 'H01_ErdsEintrTempEinb'),
	            (r'NS_MSR01a_H01_VerdUwp_RM_Ein.hdb', 'H01_VerdUwp')]
	for job in job_list:
		hdb_filename = DIR + '\\' + job[0]
		csv_filename = DIR + '\\' + 'hdb2csv_' + job[1] + r'_Feb_2017.csv'
		print('conversion: ' + hdb_filename + ' ==>> ' + csv_filename)
		myconverter = Converter(hdb_filename, csv_filename)
		myconverter.convert()
		print('\tdone.')

if __name__ == '__main__':
    status = main()