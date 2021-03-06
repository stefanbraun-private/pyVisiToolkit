#!/usr/bin/env python
# encoding: utf-8
"""
DMS_tracer.py

Continuously prints changed DMS keys under a specific DMS node at runtime.
(Quick-and-dirty...)


Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


# import sys
import dms.dmspipe
import dms.datapoint
import argparse
import time
from datetime import datetime


class Node(object):
	def __init__(self, value, datatype_str):
		self.value = value
		self.datatype_str = datatype_str

def get_dms_tree_as_dict(curr_dms, dms_node_str):
	'''retrieves DMS tree with all datatypes and values'''
	dms_key_list = curr_dms.get_DMS_subtree_list_by_key(dms_node_str)

	# copied from "DMS_Value_Changer":
	# mapping to right read function for given DMS type
	readfunc_dict = {
		1: curr_dms.pyDMS_ReadBITEx,
		2: curr_dms.pyDMS_ReadBYSEx,
		3: curr_dms.pyDMS_ReadWOSEx,
		4: curr_dms.pyDMS_ReadDWSEx,
		5: curr_dms.pyDMS_ReadBYUEx,
		6: curr_dms.pyDMS_ReadWOUEx,
		7: curr_dms.pyDMS_ReadDWUEx,
		8: curr_dms.pyDMS_ReadFLTEx,
		9: curr_dms.pyDMS_ReadSTREx
	}

	curr_dict = {}
	for dms_key in dms_key_list:
		# FIXME: copied code from "DMS_Value_Changer"... how to refactor this code? Implement a more efficient way...
		curr_type = curr_dms.pyDMS_ReadTypeEx(dms_key)
		if curr_type != 0:
			# only handling DMS keys
			curr_node = Node(value=readfunc_dict[curr_type](dms_key),
			                 datatype_str=dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[curr_type])
		else:
			curr_node = Node(value=None,
			                 datatype_str='NONE')
		curr_dict[dms_key] = curr_node
	return curr_dict


def print_with_timestamp(line_str):
	# with help from http://stackoverflow.com/questions/415511/how-to-get-current-time-in-python
	time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	print('\t'.join([time_str, line_str]))


def main(dms_node_str, pause_secs, section_sep_str):
	print('Starting "DMS tracer" for DMS node "' + str(dms_node_str) + '"...')
	curr_dms = dms.dmspipe.Dmspipe()

	if curr_dms:
		print('DMS tracer is ready...')
		print('\t(=>pause between polling is ' + str(pause_secs) + ' seconds)')
		print('=>usage hint: press <CTRL> + "C" for cancelling')
	else:
		print('ERROR: "DMS tracer" needs a running DMS!')
		return 0

	old_keys_dict = {}

	# suppress showing of all DMS keys as "ADDED" on first run
	first_run = True

	# help from http://stackoverflow.com/questions/13180941/how-to-kill-a-while-loop-with-a-keystroke
	try:
		while True:
			# handling of set() datatype: https://docs.python.org/2/library/sets.html#set-objects
			# =>we use set() on the dictionary keys to detect and analyze changes compared to last check
			old_keys_set = set(old_keys_dict.keys())
			new_keys_dict = get_dms_tree_as_dict(curr_dms=curr_dms, dms_node_str=dms_node_str)
			new_keys_set = set(new_keys_dict.keys())

			if not first_run:
				new_section = False
				# check for deleted DMS keys
				for dms_key in sorted(old_keys_set - new_keys_set):
					old_node = old_keys_dict[dms_key]
					change_str = 'DELETED:'
					type_str = '[' + old_node.datatype_str + ']'
					value_str = '[' + str(old_node.value) + ']'
					print_with_timestamp('\t'.join([change_str, type_str, dms_key, value_str]))
					new_section = True

				# check for changed DMS keys
				for dms_key in sorted(old_keys_set & new_keys_set):
					old_node = old_keys_dict[dms_key]
					new_node = new_keys_dict[dms_key]
					if old_node.value != new_node.value:
						change_str = 'CHANGED:'
						if old_node.datatype_str != new_node.datatype_str:
							type_str = '[' + old_node.datatype_str + ']=>[' + new_node.datatype_str + ']'
						else:
							type_str = '[' + old_node.datatype_str + ']'
						value_str = '[' + str(old_node.value) + ']=>[' + str(new_node.value) + ']'
						print_with_timestamp('\t'.join([change_str, type_str, dms_key, value_str]))
						new_section = True

				# check for added DMS keys
				for dms_key in sorted(new_keys_set - old_keys_set):
					new_node = new_keys_dict[dms_key]
					change_str = 'ADDED:  '
					type_str = '[' + new_node.datatype_str + ']'
					value_str = '[' + str(new_node.value) + ']'
					print_with_timestamp('\t'.join([change_str, type_str, dms_key, value_str]))
					new_section = True

				# print section separator if wanted (for better readability)
				if new_section and section_sep_str != '':
						print(section_sep_str)

			else:
				first_run = False

			time.sleep(pause_secs)
			old_keys_dict = new_keys_dict
	except KeyboardInterrupt:
		pass
	print('Quitting "DMS tracer"...')

	return 0  # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='DMS tracer of changed DMS keys.')

	# using a flag for insertion of linebreaks
	# help from https://stackoverflow.com/questions/8259001/python-argparse-command-line-flags-without-arguments
	parser.add_argument('-l', '--linear', action='store_true', help='suppress additional newlines between differences (default is building sections for better readability)')

	parser.add_argument('-p', '--pause', default=1.0, type=float, nargs='?', help='waiting time in seconds for next polling cycle (default is 1.0)')

	# this positional argument is optional
	# with help from http://stackoverflow.com/questions/4480075/argparse-optional-positional-arguments
	parser.add_argument('DMS_NODE', default='BMO', nargs='?', help='DMS node and all subnodes to trace (e.g. MSR01:H01, default is BMO)')

	args = parser.parse_args()

	if not args.linear:
		# better readability between different pollings
		section_sep_str = '=' * 20
	else:
		section_sep_str = ''

	status = main(dms_node_str=args.DMS_NODE, pause_secs=args.pause, section_sep_str=section_sep_str)
	# sys.exit(status)