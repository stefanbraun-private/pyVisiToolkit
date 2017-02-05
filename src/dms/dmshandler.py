#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmshandler.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import dms.datapoint

DEBUGGING = True


class Dmshandler(object):
	def __init__(self, pipe_name_str=r'\\.\pipe\PROMOS-DMS', dmsfile = ''):
		if dmsfile != '':
			assert dmsfile == '', 'Using a DMS file is not yet implemented!'
			# FIXME: using DMS as file is currently not implemented
			pass
		else:
			self.__dms = dms.dmspipe.Dmspipe(pipe_name_str)

	def get_last_errorcode(self):
		return self.__dms.get_last_errorcode()

	def get_dms_dp(self, key_str):
		curr_type = self.__dms.pyDMS_ReadTypeEx(key_str)
		curr_raw_value = self.__dms.pyDMS_ReadSTREx(key_str)
		curr_dp = dms.datapoint.Dms_dp_Factory.new_dp_by_int(curr_type, curr_raw_value)
		curr_dp.set_rights(self.__dms.pyDMS_GetRightsEx(key_str))
		return curr_dp

	def create_dms_dp(self, key_str, value, type_str):
		curr_dp = dms.datapoint.Dms_dp_Factory.new_dp_by_str(type_str, value)
		curr_type_int = dms.datapoint.Dms_dp_Factory.get_dp_numeric_type_by_instance(curr_dp)
		self.__dms.pyDMS_CreateEx(key_str, curr_type_int)
		if curr_type_int == 1:
			self.__dms.pyDMS_WriteBITEx(key_str, value)
		elif curr_type_int == 9:
			self.__dms.pyDMS_WriteSTREx(key_str, value)



	# FIXME: following code seems identical to dmspipe.write_DMS_subtree_serialization()...
	# =>implement a more general way to get this feature with different DMS connections! (PIPE, file, JSON, ...)
	# def get_serialised_dms_format(self, parent_node_str):
	# 	'''
	# 	returns a string containing all child nodes of given DMS key in their serialised format (as used in DMS import/export files)
	# 	FIXME: rewrite and use our dms.datapoint.Dp class for more portability and replace "magic numbers"
	# 	'''
	# 	serialised_list = []
	# 	for key in self.__dms.get_DMS_subtree_list_by_key(parent_node_str):
	# 		dms_type_int = self.__dms.pyDMS_ReadTypeEx(key)
	# 		if dms_type_int != 0:
	# 			# in exportfile there weren't any empty nodes
	# 			curr_rights_raw =  self.__dms.pyDMS_GetRightsEx(key)
	# 			if curr_rights_raw & dms.datapoint.Dp.REMANENT:
	# 				# only export remanent datapoints
	#
	# 				# construction of serialised DMS type
	# 				curr_rights_str = 'R'
	# 				if curr_rights_raw & dms.datapoint.Dp.READ_WRITE:
	# 					curr_rights_str = curr_rights_str + 'W'
	# 				elif curr_rights_raw & dms.datapoint.Dp.READ_ONLY:
	# 					curr_rights_str = curr_rights_str + 'O'
	# 				if curr_rights_raw & dms.datapoint.Dp.CONFIG:
	# 					curr_rights_str = curr_rights_str + 'S'
	#
	# 				# proper formating of value
	# 				curr_value_raw = self.__dms.pyDMS_ReadSTREx(key)
	# 				if dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[dms_type_int] == 'BIT':
	# 					if curr_value_raw == 'TRUE':
	# 						curr_value_str = '1'
	# 					else:
	# 						curr_value_str = '0'
	# 				else:
	# 					curr_value_str = curr_value_raw
	#
	#
	# 				curr_line_str = ';'.join([key, dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[dms_type_int],
	# 				             curr_value_str, curr_rights_str])
	# 				serialised_list.append(curr_line_str)
	# 	return '\n'.join(serialised_list)
	#
	#
	# def export_dms_file(self, parent_node_str, export_filename):
	# 	# FIXME: rewrite and use our dms.datapoint.Dp class for more portability and replace "magic numbers"
	# 	# just in case we implement offline-DMS-file instead of running DMS
	# 	with open(export_filename, 'w') as f:
	# 		f.write(self.get_serialised_dms_format(parent_node_str))


def main(argv=None):

	curr_dms = Dmshandler()

	#curr_dp = dms.get_dms_dp('MSR01:Test')
	curr_dp = curr_dms.get_dms_dp('System:Time')
	print('DMS-key contains value "' + str(curr_dp.get_value()) + '"')
	print('\t(Python type is "' + str(type(curr_dp)) + '"')
	if curr_dp.is_readonly():
		print('\taccess right READ_ONLY')
	if curr_dp.is_readwrite():
		print('\taccess right READ_WRITE')
	if curr_dp.is_remanent():
		print('\taccess right REMANENT')
	print('\n')

	curr_dms.create_dms_dp('MSR01:Test3', True, 'BIT')
	print('last error was ' + str(curr_dms.get_last_errorcode()))
	curr_dp = curr_dms.get_dms_dp('MSR01:Test3')
	print('DMS-key contains value "' + str(curr_dp.get_value()) + '"')
	print('\n')

	curr_dms.create_dms_dp('MSR01:Test4', 'Teststring', 'STR')
	print('last error was ' + str(curr_dms.get_last_errorcode()))
	curr_dp = curr_dms.get_dms_dp('MSR01:Test4')
	print('DMS-key contains value "' + str(curr_dp.get_value()) + '"')
	print('\n')


	print('***** Export DMS tree into *.dms file ****')
	curr_dms.export_dms_file('MSR01:Allg:QUIT:Or01', r'D:\my_DMS_export.dms')
	print('\tdone.')

	return 0        # success


if __name__ == '__main__':
	status = main()