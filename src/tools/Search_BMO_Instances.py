#!/usr/bin/env python
# encoding: utf-8
"""
tools.Search_BMO_Instances.py
Searches BMO instances in running DMS according to different filter conditions

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

#import sys
import dms.dmspipe
import dms.datapoint
import misc.clipboard
import Tkinter as tk
import re

import functools

DEBUGGING = True


class SearchBmoGui(tk.Tk):
	def __init__(self, curr_dms):
		tk.Tk.__init__(self)
		self.title("Search BMO Instances v0.0.1")
		self.resizable(0, 0)
		self.curr_dms = curr_dms

		self.bmo_filter_tk = tk.StringVar()
		self.bmo_class_list = []
		self.bmo_instance_list = []
		self._populate_obj_list()
		self.textarea_frame = _Text_area('Nothing to show...\nPlease do another search!')

		self._draw_structure()


	def _draw_structure(self):
		rox_idx = 0
		lab = tk.Label(master=self, text="Select search criteria:")
		lab.grid(row=rox_idx, column=0, padx=5, pady=5)

		rox_idx += 1
		lab = tk.Label(master=self, text="BMO class:")
		lab.grid(row=rox_idx, column=0, padx=5, pady=5)

		# OptionMenu with BMO classes (FIXME: should we set a default filter? how to implement an empty filter?)
		#self.bmo_filter_tk.set()
		# example from http://effbot.org/tkinterbook/optionmenu.htm
		self.optmenu = apply(tk.OptionMenu, (self, self.bmo_filter_tk) + tuple(sorted(self.bmo_class_list)))
		self.optmenu.grid(row=rox_idx, column=1, padx=5, pady=5)

		rox_idx += 1
		lab = tk.Label(master=self, text="Regex pattern of DMS key:")
		lab.grid(row=rox_idx, column=0, padx=5, pady=5)
		self.key_regex_entry = tk.Entry(self, width=80)
		self.key_regex_entry.insert(0, ".*")
		self.key_regex_entry.grid(row=rox_idx, column=1, padx=5, pady=5)


		rox_idx += 1
		lab = tk.Label(master=self, text="Regex pattern of NAME:")
		lab.grid(row=rox_idx, column=0, padx=5, pady=5)
		self.name_regex_entry = tk.Entry(self, width=80)
		self.name_regex_entry.insert(0, ".*")
		self.name_regex_entry.grid(row=rox_idx, column=1, padx=5, pady=5)



		rox_idx += 1
		btn = tk.Button(master=self, text='Search BMO instance', command=self._cb_button_search_bmo)
		btn.grid(row=rox_idx, column=0, columnspan=2, padx=5, pady=5, sticky='NSEW')

		rox_idx += 1
		self.textarea_frame_gridpos = (rox_idx, 0)
		self.textarea_frame.grid(row=self.textarea_frame_gridpos[0], column=self.textarea_frame_gridpos[1], columnspan=2, padx=5, pady=5, sticky='NSEW')


	def _cb_button_search_bmo(self):
		# getting all BMO instances
		self.bmo_instance_list = []
		key_list = self.curr_dms.get_DMS_keyvalue_list_by_keypart('OBJECT')
		if DEBUGGING:
			print('Search for "OBJECT" had ' + str(len(key_list))+ ' hits...')
		for key, bmo_class in key_list:
			if bmo_class == self.bmo_filter_tk.get() and not key.startswith('BMO:'):
				# removing trailing string ":OBJECT"...
				curr_key = key[:-7]
				match = re.search(self.key_regex_entry.get(), curr_key)
				if match:

					self.bmo_instance_list.append(curr_key)

		# FIXME: improve this code, don't create another list (deleting an item of a list while iterating over it is a bad idea...)
		name_applied_list = []      # list of tuples (DMS-key, NAME)
		for key in self.bmo_instance_list:
			curr_name = self.curr_dms.pyDMS_ReadSTREx(key + ':NAME')
			match = re.search(self.name_regex_entry.get(), curr_name)
			if match:
				name_applied_list.append((key, curr_name))

		# build the resulting text area, possible to copy it into Excel
		curr_line_list = []
		for item in name_applied_list:
			curr_line_list.append('\t'.join(item))
		curr_string = '\n'.join(curr_line_list)

		if self.textarea_frame != None:
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self.textarea_frame.grid_forget()
			self.textarea_frame.destroy()
		self.textarea_frame = _Text_area(curr_string)
		self.textarea_frame.grid(row=self.textarea_frame_gridpos[0], column=self.textarea_frame_gridpos[1], columnspan=2, padx=1, pady=1, sticky='NSEW')


	def _populate_obj_list(self):
		# getting all BMO classes
		key_list = self.curr_dms.get_DMS_sons_list_by_key('BMO')
		if DEBUGGING:
			print('Found ' + str(len(key_list)) + ' child nodes under "BMO"...')
		for item in key_list:
			self.bmo_class_list.append(item[0])


class _Text_area(tk.Frame):
	def __init__(self, text_str, *kargs, **kwargs):
		tk.Frame.__init__(self, *kargs, **kwargs)
		self.text_str = text_str

		self._show_text()

	def _show_text(self):
		# example: multiline text with scrollbars:
		# http://stackoverflow.com/questions/17657212/how-to-code-the-tkinter-scrolledtext-module
		xscrollbar = tk.Scrollbar(self)
		yscrollbar = tk.Scrollbar(self)
		textArea = tk.Text(self, width=150, height=50, wrap="word",
		                    xscrollcommand=xscrollbar.set,
		                    yscrollcommand=yscrollbar.set,
                            borderwidth=0, highlightthickness=0)
		xscrollbar.config(command=textArea.xview)
		yscrollbar.config(command=textArea.yview)
		xscrollbar.pack(side="bottom", fill="x")
		yscrollbar.pack(side="right", fill="y")
		textArea.pack(side="left", fill="both", expand=True)

		# show text
		textArea.insert(tk.END, self.text_str)



def main(argv=None):
	curr_dms = dms.dmspipe.Dmspipe()

	rootwindow = SearchBmoGui(curr_dms)

	rootwindow.mainloop()

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)