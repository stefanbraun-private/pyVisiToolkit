#!/usr/bin/env python
# encoding: utf-8
"""
tools.DMS_Value_Changer.py
Retrieves from a list of DMS keys their current value and allows simple changes of them.

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

#import sys
import dms.dmspipe
import dms.datapoint
import Tkinter as tk
import time
import os
import io
import traceback

DEBUGGING = True
ENCODING = 'windows-1252'

class DMS_Datapoint(object):
	def __init__(self):
		self.is_available = False
		self.datatype_str = 'NONE'
		self.old_value = None
		self.new_value = None
		self.rights = 0
		self.value_error = False    # Python throwed an exception while trying to parse "new_value"... did user made a typo?


class DMS_Vars(object):
	def __init__(self, curr_dms):
		self.curr_dms = curr_dms
		self.curr_prj = self.curr_dms.pyDMS_ReadSTREx('System:Project')
		assert self.curr_prj != '', 'Unable to retrieve datapoint "System:Project"... Is DMS running?'
		print('CONNECTED TO DMS. Current active project is "' + self.curr_prj + '"')
		self.dp_dict = {}

	def read_from_dms(self, key_list):
		# call right read function for given DMS type
		readfunc_dict = {
				1:	self.curr_dms.pyDMS_ReadBITEx,
				2:	self.curr_dms.pyDMS_ReadBYSEx,
				3:	self.curr_dms.pyDMS_ReadWOSEx,
				4:	self.curr_dms.pyDMS_ReadDWSEx,
				5:	self.curr_dms.pyDMS_ReadBYUEx,
				6:	self.curr_dms.pyDMS_ReadWOUEx,
				7:	self.curr_dms.pyDMS_ReadDWUEx,
				8:	self.curr_dms.pyDMS_ReadFLTEx,
				9:  self.curr_dms.pyDMS_ReadSTREx
		}

		self.dp_dict = {}
		for item in key_list:
			dp = DMS_Datapoint()
			if self.curr_dms.is_dp_available(item):
				dp.is_available = True
				curr_type = self.curr_dms.pyDMS_ReadTypeEx(item)
				dp.datatype_str = dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[curr_type]
				dp.rights = self.curr_dms.pyDMS_GetRightsEx(item)
				dp.old_value = readfunc_dict[curr_type](item)
			self.dp_dict[item] = dp


	def _get_serialized_dms_format(self, curr_key, curr_rights, curr_type_str, curr_val):
		# FIXME: copied from "Dmspipe.get_serialized_dms_format(self, parent_node_str)" ... =>do refactoring for more code usability?
		# FIXME: BUT beware curr_val now could be int/float/bool/str (from DMS) OR unicode-text (from text widget)!!!

		# FIXME: access rights do work this way, but we should implement a more elegant solution in "dms.datapoint.Dp"...
		if curr_rights & dms.datapoint.Dp.READ_WRITE:
			curr_rights_str = 'RW'
		else:
			curr_rights_str = 'RO'
		if curr_rights & dms.datapoint.Dp.CONFIG:
			curr_rights_str = curr_rights_str + 'S'

		# prepare string containing value, boolean values were stored as '0' or '1'
		if curr_type_str == 'BIT':
			if isinstance(curr_val, bool):
				# datasource is DMS
				if curr_val:
					curr_val_str = '1'
				else:
					curr_val_str = '0'
			else:
				# datasource is text widget
				if curr_val.upper() == 'TRUE' or curr_val == '1':
					curr_val_str = '1'
				else:
					curr_val_str = '0'
		elif curr_type_str == 'FLT':
			# DMS serialization has always floats with precision 10E-6
			curr_val_str = '{:.6f}'.format(float(curr_val))
			if DEBUGGING:
				if curr_val_str.startswith(' '):
					print('key=' + curr_key + ', curr_val_str=' + curr_val_str + ', type(curr_val)=' + str(type(curr_val)))
		else:
			# current value doesn't need special treatment, convert it to string...
			# =>if it's already a string then decode it to unicode
			if isinstance(curr_val, str):
				curr_val_str = curr_val.decode(ENCODING)
			elif isinstance(curr_val, unicode):
				curr_val_str = curr_val
			else:
				curr_val_str = unicode(str(curr_val),ENCODING)

		# handling all strings as unicode strings =>decode strings which could contain Umlaut
		return ';'.join([curr_key,
		                curr_type_str,
		                curr_val_str,   #.decode(ENCODING),
		                curr_rights_str])


	def get_metadata(self, key_list):
		lines_list = []
		for item in key_list:
			if self.dp_dict[item].is_available:
				my_str = 'type: ' + self.dp_dict[item].datatype_str
			else:
				my_str = 'missing...'
			lines_list.append(my_str)
		return '\n'.join(lines_list)


	def get_values(self, key_list):
		lines_list = []
		for item in key_list:
			if self.dp_dict[item].is_available:
				# FIXME: do we need a *.decode(ENCODING) here to prevent encoding problems?
				my_str = str(self.dp_dict[item].old_value)
			else:
				my_str = ''
			lines_list.append(my_str)
		return '\n'.join(lines_list)


	def set_values(self, key_list, value_list):
		for idx, item in enumerate(key_list):
			if self.dp_dict[item].is_available:
				self.dp_dict[item].new_value = value_list[idx]


	def write_to_dms(self, key_list):
		# first generate DMS import files with old and new value (as backup for simple undoing last action)
		# returns a list of *.value_error flags (used as tag in GUI text widget)
		OLD = 'oldvalue'
		NEW = 'newvalue'
		for dp_revision in [OLD, NEW]:
			export_fname =  'DMS_Value_Changer_' + time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime()) + '_' + dp_revision + '.dms'
			export_fullpath = os.path.join(self.curr_prj, 'cfg', export_fname)
			old_serialized_list = []
			new_serialized_list = []
			for item in key_list:
				if self.dp_dict[item].is_available:
					if dp_revision == OLD:
						line_str = self._get_serialized_dms_format(curr_key=item,
						                                          curr_rights=self.dp_dict[item].rights,
						                                          curr_type_str=self.dp_dict[item].datatype_str,
						                                          curr_val=self.dp_dict[item].old_value)
						old_serialized_list.append(line_str)
					else:
						line_str = self._get_serialized_dms_format(curr_key=item,
						                                          curr_rights=self.dp_dict[item].rights,
						                                          curr_type_str=self.dp_dict[item].datatype_str,
						                                          curr_val=self.dp_dict[item].new_value)
						new_serialized_list.append(line_str)

			print('\tExporting datapoints in serialized DMS format into exportfile "' + export_fullpath + '"')
			# Write the file out
			with io.open(export_fullpath, 'w', encoding=ENCODING) as f:
				if dp_revision == OLD:
					export_content = '\n'.join(old_serialized_list)
				else:
					export_content = '\n'.join(new_serialized_list)
				# handling all strings as unicode strings =>encode to local codepage
				f.write(export_content)
				# append one linebreak at the end (DMS does the same in exportfiles)
				f.write(u'\n')
		print('\tWriting of exportfiles is done...')


		# call right write function for given DMS type
		writefunc_dict = {
				1:	self.curr_dms.pyDMS_WriteBITEx,
				2:	self.curr_dms.pyDMS_WriteBYSEx,
				3:	self.curr_dms.pyDMS_WriteWOSEx,
				4:	self.curr_dms.pyDMS_WriteDWSEx,
				5:	self.curr_dms.pyDMS_WriteBYUEx,
				6:	self.curr_dms.pyDMS_WriteWOUEx,
				7:	self.curr_dms.pyDMS_WriteDWUEx,
				8:	self.curr_dms.pyDMS_WriteFLTEx,
				9:  self.curr_dms.pyDMS_WriteSTREx
		}

		# call right Python datatype constructor
		construct_func_dict = {
				1:	parse_boolean,   #self.curr_dms.pyDMS_WriteBITEx,
				2:	int,    #self.curr_dms.pyDMS_WriteBYSEx,
				3:	int,    #self.curr_dms.pyDMS_WriteWOSEx,
				4:	int,    #self.curr_dms.pyDMS_WriteDWSEx,
				5:	int,    #self.curr_dms.pyDMS_WriteBYUEx,
				6:	int,    #self.curr_dms.pyDMS_WriteWOUEx,
				7:	int,    #self.curr_dms.pyDMS_WriteDWUEx,
				8:	float,  #self.curr_dms.pyDMS_WriteFLTEx,
				9:  str     #self.curr_dms.pyDMS_WriteSTREx
		}
		print('\tUpdate all values in DMS...')
		error_list = []
		for item in key_list:
			if self.dp_dict[item].is_available:
				dp = self.dp_dict[item]
				type_num = dms.datapoint.Dms_dp_Factory.dp_string_types_dict[dp.datatype_str]

				try:
					# encode unicode to current codepage if needed
					# FIXME: is there a better way to handle unicode?
					if type_num == 9:
						python_val = dp.new_value.encode(ENCODING)
					else:
						python_val = construct_func_dict[type_num](dp.new_value)

					writefunc_dict[type_num](item, python_val)
				except ValueError:
					# couldn't parse "new_value", user did possibly a typo...
					# =>used as tag in GUI text widget
					self.dp_dict[item].value_error = True

					# Show exception, then user can see the details
					# example from http://www.ianbicking.org/blog/2007/09/re-raising-exceptions.html
					traceback.print_exc()

				# set error flag for GUI
				error_list.append(self.dp_dict[item].value_error)
		print('DONE.')
		return error_list

	def reset_cache(self):
		self.dp_dict = {}



class DMS_Value_Changer(tk.Tk):
	def __init__(self, curr_dms):
		tk.Tk.__init__(self)
		self.title("DMS Value Changer v0.0.1")
		self.resizable(0, 0)
		self.dms_vars = DMS_Vars(curr_dms)

		lab = tk.Label(master=self, text="DMS Value Changer\n->update multiple arbitrary DMS keys with one click!")
		lab.pack(pady=20)

		self.text_area_dict = {}
		data_frame = _Text_Frame(self)
		data_frame.pack(fill=tk.BOTH, expand=1)

		btn_frame = _Button_Frame(self)
		btn_frame.pack(fill=tk.BOTH, expand=1)


class _Button_Frame(tk.Frame):
	def __init__(self, root):
		tk.Frame.__init__(self, master=root)
		self.parent = root
		self.text_area_dict = root.text_area_dict

		self._draw_buttons()


	def _draw_buttons(self):
		self.btn_reset = tk.Button(master=self, text='Reset cached values', command=self._cb_btn_reset)
		self.btn_reset.grid(row=0, column=0, padx=5, pady=5, sticky='NSEW')

		self.btn_read = tk.Button(master=self, text='Read from DMS', command=self._cb_btn_read)
		self.btn_read.grid(row=0, column=1, padx=5, pady=5, sticky='NSEW')

		self.btn_write = tk.Button(master=self, text='Write to DMS', command=self._cb_btn_write)
		self.btn_write.grid(row=0, column=2, padx=5, pady=5, sticky='NSEW')

		# default state after start: only text area with DMS keys makes sense
		self._cb_btn_reset()


	def _cb_btn_reset(self):
		# activate text widget "key", clear data in other text widgets
		for area in self.text_area_dict:
			if area == 'key':
				self.text_area_dict[area].config(state=tk.NORMAL)
				self.text_area_dict[area].config(background="white")
			else:
				self.text_area_dict[area].config(state=tk.NORMAL)
				self.text_area_dict[area].delete(1.0, tk.END)
				self.text_area_dict[area].config(state=tk.DISABLED)
				self.text_area_dict[area].config(background="gray")

		# only "reset" and "read" buttons makes sense after reset
		self.btn_reset.config(state=tk.NORMAL)
		self.btn_read.config(state=tk.NORMAL)
		self.btn_write.config(state=tk.DISABLED)

		# reset internal cached values
		self.parent.dms_vars.reset_cache()


	def _cb_btn_read(self):
		# first do a clean-up
		self._cb_btn_reset()

		# request all given DMS-keys
		# and put their metadata and values into our text areas
		# FIXME: we have always two empty strings at the list end... How to remove them while not causing many exceptions in other code parts?!?
		key_list = self.text_area_dict['key'].get("1.0",tk.END).split('\n')
		self.parent.dms_vars.read_from_dms(key_list)

		# put content from DMS into text areas (we need to set them into editable state for doing this)
		for area in ['metadata', 'oldval', 'newval']:
			self.text_area_dict[area].config(state=tk.NORMAL)
			if area == 'metadata':
				self.text_area_dict[area].insert(tk.END, self.parent.dms_vars.get_metadata(key_list))
			elif area == 'oldval' or area == 'newval':
				self.text_area_dict[area].insert(tk.END, self.parent.dms_vars.get_values(key_list))

		# coloring lines for better readability
		# code source: http://stackoverflow.com/questions/26348989/changing-background-color-for-every-other-line-of-text-in-a-tkinter-text-box-wid
		for area in ['key', 'metadata', 'oldval', 'newval']:
			self.text_area_dict[area].tag_configure("even", background="#e0e0e0")
			self.text_area_dict[area].tag_configure("odd", background="#ffffff")

			lastline = self.text_area_dict[area].index("end-1c").split(".")[0]
			tag = "odd"
			for i in range(1, int(lastline)):
				if tag == "even":
					# FIXME: just colorize even lines, because otherwise selected text is white on white...
					self.text_area_dict[area].tag_add(tag, "%s.0" % i, "%s.0" % (i+1))
				tag = "even" if tag == "odd" else "odd"


		# deactivate all text widgets except text widget for editing "newval"
		for area in self.text_area_dict:
			if area == 'newval':
				self.text_area_dict[area].config(state=tk.NORMAL)
				self.text_area_dict[area].config(background="white")
			else:
				self.text_area_dict[area].config(state=tk.DISABLED)
				self.text_area_dict[area].config(background="gray")

		# all buttons makes sense after read
		self.btn_reset.config(state=tk.NORMAL)
		self.btn_read.config(state=tk.NORMAL)
		self.btn_write.config(state=tk.NORMAL)


	def _cb_btn_write(self):
		key_list = self.text_area_dict['key'].get("1.0",tk.END).split('\n')
		new_val_list = self.text_area_dict['newval'].get("1.0",tk.END).split('\n')
		self.parent.dms_vars.set_values(key_list, new_val_list)
		error_list = self.parent.dms_vars.write_to_dms(key_list)

		# mark wrong datatypes in "newval" text area
		self.text_area_dict['newval'].tag_configure("error", background="#ff0000")
		for i in range(1, len(error_list) + 1):
			if error_list[i - 1]:
				self.text_area_dict['newval'].tag_add("error", "%s.0" % i, "%s.0" % (i+1))

		# all buttons makes sense after write
		self.btn_reset.config(state=tk.NORMAL)
		self.btn_read.config(state=tk.NORMAL)
		self.btn_write.config(state=tk.NORMAL)




class _Text_Frame(tk.Frame):
	def __init__(self, root):
		tk.Frame.__init__(self, master=root)
		self.text_area_dict = root.text_area_dict
		self._draw_data_frame()


	def _draw_data_frame(self):
		yscrollbar = tk.Scrollbar(self)

		row_idx = 0
		lab = tk.Label(master=self, text="DMS keys")
		lab.grid(row=row_idx, column=0, padx=5, pady=5)

		lab = tk.Label(master=self, text="Metadata")
		lab.grid(row=row_idx, column=1, padx=5, pady=5)

		lab = tk.Label(master=self, text="old value")
		lab.grid(row=row_idx, column=2, padx=5, pady=5)

		lab = tk.Label(master=self, text="new value")
		lab.grid(row=row_idx, column=3, padx=5, pady=5)


		row_idx += 1
		self.key_textarea = tk.Text(self, width=80, height=40, wrap="word", yscrollcommand=yscrollbar.set, borderwidth=0, highlightthickness=0)
		# show some text
		self.key_textarea.insert(tk.END, 'Please insert a list of DMS keys...')
		# save reference for external access into text field
		self.text_area_dict['key'] = self.key_textarea
		#self.key_textarea.pack(side="left", fill="both", expand=True)
		self.key_textarea.grid(row=row_idx, column=0, padx=2, pady=5)

		self.metadata_textarea = tk.Text(self, width=15, height=40, wrap="word", yscrollcommand=yscrollbar.set,  borderwidth=0, highlightthickness=0)
		# show some text
		#self.metadata_textarea.insert(tk.END, 'Nothing to show...\n\n\nreally nothing...')
		# save reference for external access into text field
		self.text_area_dict['metadata'] = self.metadata_textarea
		#self.oldval_textarea.pack(side="left", fill="both", expand=True)
		self.metadata_textarea.grid(row=row_idx, column=1, padx=2, pady=5)


		self.oldval_textarea = tk.Text(self, width=50, height=40, wrap="word", yscrollcommand=yscrollbar.set,  borderwidth=0, highlightthickness=0)
		# show some text
		#self.oldval_textarea.insert(tk.END, 'Nothing to show...\n\n\nreally nothing...')
		# save reference for external access into text field
		self.text_area_dict['oldval'] = self.oldval_textarea
		#self.oldval_textarea.pack(side="left", fill="both", expand=True)
		self.oldval_textarea.grid(row=row_idx, column=2, padx=2, pady=5)


		self.newval_textarea = tk.Text(self, width=50, height=40, wrap="word", yscrollcommand=yscrollbar.set, borderwidth=0, highlightthickness=0)
		# show some text
		#self.newval_textarea.insert(tk.END, 'Nothing to show...\n\n\nreally nothing...')
		# save reference for external access into text field
		self.text_area_dict['newval'] = self.newval_textarea
		#self.newval_textarea.pack(side="left", fill="both", expand=True)
		self.newval_textarea.grid(row=row_idx, column=3, padx=2, pady=5)


		yscrollbar.config(command=self._scrollbar_command)
		#yscrollbar.pack(side="left", fill="y")
		yscrollbar.grid(row=row_idx, column=4, sticky=tk.N+tk.S)

	def _scrollbar_command(self, *kargs):
		# scrollbar command should inform all three textareas for changes
		# (it seems that tkinter calls this callback with arguments 'moveto', x.xxx)
		self.key_textarea.yview(*kargs)
		self.oldval_textarea.yview(*kargs)
		self.newval_textarea.yview(*kargs)


def parse_boolean(curr_str):
	# help from http://stackoverflow.com/questions/715417/converting-from-a-string-to-boolean-in-python
	# just "bool('xxx')" returns always true... So we need another solution
	return curr_str.upper() in ['TRUE', '1']


def main(argv=None):
	curr_dms = dms.dmspipe.Dmspipe()

	rootwindow = DMS_Value_Changer(curr_dms)

	rootwindow.mainloop()

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)