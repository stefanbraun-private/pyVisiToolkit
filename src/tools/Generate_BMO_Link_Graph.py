#!/usr/bin/env python
# encoding: utf-8
"""
tools.Generate_BMO_Link_Graph.py
Extracts the BMO-links from a running DMS based on PAR_IN fields in the BMO instances and generates a *.GV file (then GraphViz generates a SVG or bitmap)

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

#import sys
import dms.dmspipe
import os
import time
#import io  # used when write file with ENCODING

DEBUGGING = True
# currently we ignore the encoding (Graphviz seems to fail with Umlaut)
#ENCODING = 'windows-1252'

# constants as key in dictionary
PAR_IN = 'PAR_IN'
PAR_DATA = 'PAR_DATA'
PAR_OUT = 'PAR_OUT'

# other constants
TYPE_NONE = 0
TYPE_ANALOGUE = 1
TYPE_DIGITAL = 2

GV_SUFFIX_WRONG_TYPE = ' [label="wrong type", color="red", fontsize=8]'
GV_SUFFIX_WRONG_DP = ' [label="wrong datapoint", color="red", fontsize=8]'
GV_SUFFIX_WRONG_PLC = ' [label="wrong PLC", color="red", fontsize=8]'
GV_SUFFIX_WRONG_BMO = ' [label="unknown BMO", color="red", fontsize=8]'

used_bmo_dict = {}  # dict of dicts of lists with PAR_* datapoints of BMO-classes
bmo_inst_dict = {}  # dict of lists of BMO instances (PLC-name is key)
used_plc_list = []  # list of PLC-names


def _write_gv_header(f):
	f.write('/* Test graph connections between BMO instances */\n')
	f.write('digraph bmo_links {\n')
	f.write('\t/* some default declarations */\n')
	f.write('\t// for color-strings look at http://www.graphviz.org/doc/info/colors.html\n')
	f.write('\tnode [color=lightblue2, style=filled];\n')
	f.write('\trankdir=LR;\n')
	f.write('\tgraph [fillcolor=beige, style="rounded, filled"]\n\n\n')



def main(argv=None):
	if DEBUGGING:
		print('******************************')
		print('* Generate_BMO_Link_Graph.py *')
		print('* v0.0.1                     *')
		print('******************************\n')

	curr_dms = dms.dmspipe.Dmspipe()

	curr_prj = curr_dms.pyDMS_ReadSTREx('System:Project')
	export_fname = curr_prj + '_' + time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime()) + '.gv'
	if DEBUGGING:
		print('Visi.Plus project "' + curr_prj + '" is running...')
		print('\t->The generated Graphviz file is named "' + export_fname + '"')

	# get all BMO instances (OBJECTs)
	if DEBUGGING:
		print('Retrieve list of all BMO instances ("OBJECT") from DMS...')
	my_bmo_inst_list = curr_dms.get_DMS_keyvalue_list_by_keypart('OBJECT')
	if DEBUGGING:
		print('Found ' + str(len(my_bmo_inst_list)) + ' BMO instances...')
	for item in my_bmo_inst_list:
		curr_key_str, bmo_class = item
		if not curr_key_str.startswith('BMO:'):
			# suppress BMO-classtree, handle only initialised BMO instances
			if not bmo_class in used_bmo_dict:
				# prepare data structure for this BMO class
				used_bmo_dict[bmo_class] = {}
				used_bmo_dict[bmo_class][PAR_IN] = []
				used_bmo_dict[bmo_class][PAR_DATA] = []
				used_bmo_dict[bmo_class][PAR_OUT] = []

			# arrange all BMO instances based on their PLC into our data structure
			# (first part is the PLC, last part is ":OBJECT")
			curr_bmo_parts = curr_key_str.split(':')
			curr_plc = curr_bmo_parts[0]
			if curr_plc not in used_plc_list:
				# new PLC found
				used_plc_list.append(curr_plc)
				bmo_inst_dict[curr_plc] = {}

			# get DMS-key-parts up to ":OBJECT" as BMO instance and store its BMO class
			curr_inst = ':'.join(curr_bmo_parts[:-1])
			bmo_inst_dict[curr_plc][curr_inst] = bmo_class

	if DEBUGGING:
		print('=>' + str(len(used_bmo_dict)) + ' BMO classes were used...')

	# collect all PAR_INs of the used BMO classes from DMS-tree "BMO:...."
	# (assumption: DMS is not corrupted, BMO instances are sane and contain the same PAR_INs as the BMO class!)
	for bmo_class in used_bmo_dict.keys():
		if bmo_class != '':
			curr_bmo = 'BMO:' + bmo_class
			for dmsvar in curr_dms.get_DMS_subtree_list_by_key(curr_bmo):
				if dmsvar.endswith(':' + PAR_IN):
					my_par_in = dmsvar[:-7]
					used_bmo_dict[bmo_class][PAR_IN].append(my_par_in)
				elif dmsvar.endswith(':' + PAR_DATA):
					my_par_data = dmsvar[:-9]
					used_bmo_dict[bmo_class][PAR_DATA].append(my_par_data)
				elif dmsvar.endswith(':' + PAR_OUT):
					my_par_out = dmsvar[:-8]
					used_bmo_dict[bmo_class][PAR_OUT].append(my_par_out)
			if DEBUGGING:
				print('\tBMO "' + bmo_class + '" contains ' + str(len(used_bmo_dict[bmo_class][PAR_IN])) + ' PAR_IN, ' + str(len(used_bmo_dict[bmo_class][PAR_DATA])) + ' PAR_DATA, ' + str(len(used_bmo_dict[bmo_class][PAR_OUT])) + ' PAR_OUT.')


	with open(export_fname, 'w') as f:
		_write_gv_header(f)

		# create a subgraph per PLC-name
		# (reversed ordering because graphviz generates graphs this way...)
		missing_bmo_list = []
		for plc in sorted(used_plc_list, reverse=True):
			f.write('\tsubgraph cluster_' + plc + ' {\n')
			f.write('\t\tlabel = "' + plc + '";\n')
			f.write('\t\t\n')

			# list for setting all BMO instances with hardware dependencies (PAR_DATA) on the same rank
			hardware_bmo_list = []

			# insert all edges and nodes (insert special styles/colors were needed)
			f.write('\t\t// BMO instances referenced from PAR_IN\n')
			for bmo_inst in bmo_inst_dict[plc]:
				bmo_class = bmo_inst_dict[plc][bmo_inst]
				for par_in_key in used_bmo_dict[bmo_class][PAR_IN]:
					#if DEBUGGING:
					#	print('bmo_inst=' + bmo_inst + ', bmo_class=' + bmo_class + ', par_in_key=' + par_in_key)
					link_drain = bmo_inst + par_in_key.replace('BMO:' + bmo_class, '')
					#if DEBUGGING:
					#	print('link_drain=' + link_drain)
					link_source = curr_dms.pyDMS_ReadSTREx(link_drain + ':' + PAR_IN)
					#if DEBUGGING:
					#	print('link_drain=' + link_drain + ', link_source=' + link_source)
					#src_type = TYPE_NONE   // not implemented
					gv_suffix = ''
					src_bmo = ''
					if link_source.startswith('F.') or link_source.startswith('R.') or link_source.startswith('I.'):
						# add PLC-name for unique node identification
						src_bmo = plc + '--' + link_source
					elif ':' in link_source:
						# search BMO instance for this datapoint
						# assumption: format is always <BMO-instance>:<datapoint>:(PLC|PAR_IN|PAR_OUT):*
						src_bmo = ':'.join(link_source.split(':')[:-1])
						if not src_bmo in bmo_inst_dict[plc]:
							if curr_dms.is_dp_available(src_bmo + ':OBJECT'):
								# BMO instance not on same PLC, but it's a valid BMO object in DMS
								gv_suffix = GV_SUFFIX_WRONG_PLC
							else:
								# no valid BMO object in DMS found
								gv_suffix = GV_SUFFIX_WRONG_BMO
								missing_bmo_list.append(src_bmo)
						else:
							# check if link source is a valid PLC-communicated datapoint
							if not curr_dms.is_dp_available(link_source + ':PLC'):
								gv_suffix = GV_SUFFIX_WRONG_DP

					if src_bmo != '':
						# it seems we have a valid link source!
						# =>build edge between these two BMO instances
						edge = '"' + src_bmo + '" -> "' + bmo_inst + '"' + gv_suffix + ';'
						f.write('\t\t' + edge + '\n')

				# assume hardware dependency when this BMO class has PAR_DATA fields
				if used_bmo_dict[bmo_class][PAR_DATA]:
					hardware_bmo_list.append(bmo_inst)

			# set all nodes with hardware dependency on same rank as sink (last line in graph)
			# (with help from http://stackoverflow.com/questions/25734244/how-do-i-place-nodes-on-the-same-level-in-dot )
			mynodes = '"; "'.join(hardware_bmo_list)
			f.write('\t{rank = same; "' + mynodes + '";}\n')

			# close PLC-subgraph
			f.write('\t}\n\n')

		# set special formating on nodes of missing BMO instances
		f.write('\t// special formating of missing BMO instances\n')
		for bmo_inst in missing_bmo_list:
			node = '"' + bmo_inst + '" [color=red];'
			f.write('\t' + node + '\n')

		f.write('}\n')


	# command under Windows:
	# K:\TEMP>"C:\Program Files (x86)\Graphviz2.38\bin\dot.exe" -T svg test.gv  -Gcharset=latin1 -v -o test.svg
	# or perhaps
	# K:\TEMP>"C:\Program Files (x86)\Graphviz2.38\bin\dot.exe" -T svg test.gv  -Gcharset=cp-1252 -v -o test.svg
	# ("Scheiss Encoding...!!!")
	print('\n\n->Usage example under Windows:')
	print(r'K:\TEMP>"C:\Program Files (x86)\Graphviz2.38\bin\dot.exe" -T svg test.gv  -Gcharset=cp-1252 -v -o test.svg')
	print('\nFor simple usage of Graphviz we generate now a Windows batch file:')

	#gv_filename = os.path.split(export_fname)[1]
	gv_filename = export_fname
	bat_filename = gv_filename.replace('.gv', '.bat')
	svg_filename = gv_filename.replace('.gv', '.svg')
	print('You will find it here:\n' + bat_filename)
	with open(bat_filename, 'w') as curr_file:
		curr_file.write('REM **************************************************\n')
		curr_file.write('REM Batch file generated by Generate_BMO_Link_Graph.py\n')
		curr_file.write('REM **************************************************\n\n')
		curr_file.write(r'"C:\Program Files (x86)\Graphviz2.38\bin\dot.exe" -T svg ' + gv_filename + ' -Gcharset=cp-1252 -v -o ' + svg_filename + '\n')

	print('\nDone.')

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)