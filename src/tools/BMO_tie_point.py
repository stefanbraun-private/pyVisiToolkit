#!/usr/bin/env python
# encoding: utf-8
"""
tools.BMO_tie_point.py
shows information about communicated PLC datapoints
(developing in Visi.Plus: helps during linkage of BMO instances and creating dialog forms)

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
import functools

DEBUGGING = True



class Bmo_dp(object):

	# some constant strings for set() filter
	MISC = 'MISC'
	ANALOG = 'ANALOG'
	DIGITAL = 'DIGITAL'
	PAR_IN = 'PAR_IN'
	PAR_OUT = 'PAR_OUT'
	PLC = 'PLC'


	def __init__(self):
		self.is_analogue = False
		self.is_digital = False
		self.comment = ''
		self.is_par_in = False
		self.is_par_out = False
		self.is_plc = False

	@classmethod
	def get_display_filter(cls, misc=False, analog=False, digital=False, par_in=False, par_out=False, plc=False):
		# default: allowing all datapoints
		myset = set()
		if misc:
			myset.add(cls.MISC)
		if analog:
			myset.add(cls.ANALOG)
		if digital:
			myset.add(cls.DIGITAL)
		if par_in:
			myset.add(cls.PAR_IN)
		if par_out:
			myset.add(cls.PAR_OUT)
		if plc:
			myset.add(cls.PLC)
		return myset

	def get_dp_properties(self):
		# builds a property set from given datapoint
		# (for comparison to display filter)
		myset = set()
		if not self.is_analog and not self.is_digital:
			myset.add(Bmo_dp.MISC)
		if self.is_analog:
			myset.add(Bmo_dp.ANALOG)
		if self.is_digital:
			myset.add(Bmo_dp.DIGITAL)
		if self.is_par_in:
			myset.add(Bmo_dp.PAR_IN)
		if self.is_par_out:
			myset.add(Bmo_dp.PAR_OUT)
		if self.is_plc:
			myset.add(Bmo_dp.PLC)
		return myset


class Bmo_instance(object):
	def __init__(self, curr_dms, bmo_instance=''):
		self.curr_dms = curr_dms
		self.bmo_instance = ''
		self.object = ''
		self.comment = ''
		self.name = ''
		self.dp_dict = {}

		if bmo_instance != self.bmo_instance:
			self.update_bmo_instance(bmo_instance)

	def update_bmo_instance(self, bmo_instance):
		self.bmo_instance = bmo_instance
		curr_obj = self.curr_dms.pyDMS_ReadSTREx(':'.join([bmo_instance, 'OBJECT']))
		self.dp_dict = {}
		if curr_obj != '':
			self.object = curr_obj
			self.comment = self.curr_dms.pyDMS_ReadSTREx(':'.join(['BMO', curr_obj]))
			self.name = self.curr_dms.pyDMS_ReadSTREx(':'.join([bmo_instance, 'NAME']))

			for child, hasgrandchildren in self.curr_dms.get_DMS_sons_list_by_key(bmo_instance):
				# collect all necessary information about every childnode of this BMO instance
				self.dp_dict[child] = Bmo_dp()
				full_dms_key = ':'.join([bmo_instance, child])
				curr_dp_type = dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[self.curr_dms.pyDMS_ReadTypeEx(full_dms_key)]
				self.dp_dict[child].is_digital = curr_dp_type == 'BIT'
				self.dp_dict[child].is_analog = curr_dp_type == 'FLT'

				self.dp_dict[child].comment = self.curr_dms.pyDMS_ReadSTREx(':'.join([full_dms_key, 'Comment']))
				self.dp_dict[child].is_par_in = self.curr_dms.is_dp_available(':'.join([full_dms_key, 'PAR_IN']))
				self.dp_dict[child].is_par_out = self.curr_dms.is_dp_available(':'.join([full_dms_key, 'PAR_OUT']))
				self.dp_dict[child].is_plc = self.curr_dms.is_dp_available(':'.join([full_dms_key, 'PLC']))

		else:
			# invalid BMO instance ->resetting all values
			self.object = ''
			self.comment = ''
			self.name = ''

class TiepointGui(tk.Tk):

	CLIPBOARD_POLLING_CYCLE = 2000      # 5s

	def __init__(self, tiepoint, clipboard):
		tk.Tk.__init__(self)
		self.title("BMO Tie-Point-Info v0.0.1")
		self.resizable(0, 0)
		self.tiepoint = tiepoint
		self.clipboard = clipboard
		self.clip_frm = None
		self.selected_bmo = tk.StringVar()
		self.bmo_frm = None
		self.dp_frm = None
		self.currfilter = None
		self.filter_frm = None
		self._draw_structure()

	def _draw_structure(self):
		lab = tk.Label(master=self, text="BMO instances in your clipboard:")
		lab.grid(row=0, column=0, padx=5, pady=5)

		self._cb_draw_clipframe()

		btn = tk.Button(master=self, text="Update shown information", command=self._cb_draw_infoframes)
		btn.grid(row=2, column=0, padx=5, pady=5)

		self._cb_draw_infoframes()

	def _cb_draw_clipframe(self):
		if self.clip_frm != None:
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self.clip_frm.pack_forget()
			self.clip_frm.destroy()
		self.clip_frm = _Clip_frame(master=self, tiepoint=self.tiepoint, clipboard=self.clipboard, selected_bmo=self.selected_bmo, relief=tk.SUNKEN, borderwidth=2)
		self.clip_frm.grid(row=1, column=0, padx=5, pady=5)

		# trigger background task (polling clipboard)
		self.after(TiepointGui.CLIPBOARD_POLLING_CYCLE, self._cb_draw_clipframe)


	def _cb_draw_infoframes(self):
		# process BMO instance selection
		self.tiepoint.update_bmo_instance(self.selected_bmo.get())

		if self.bmo_frm != None:
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self.bmo_frm.pack_forget()
			self.bmo_frm.destroy()
		self.bmo_frm = _Bmo_frame(master=self, tiepoint=self.tiepoint, clipboard=self.clipboard, relief=tk.SUNKEN, borderwidth=2)
		self.bmo_frm.grid(row=3, column=0, padx=5, pady=5)

		if self.dp_frm != None:
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self.dp_frm.pack_forget()
			self.dp_frm.destroy()

		if self.currfilter == None:
			# default: show all parts
			self.currfilter = Bmo_dp.get_display_filter()
		self.dp_frm = _Dp_frame(master=self, displayfilter=self.currfilter, tiepoint=self.tiepoint, clipboard=self.clipboard, relief=tk.SUNKEN, borderwidth=2)
		self.dp_frm.grid(row=4, column=0, padx=5, pady=5)

		if self.filter_frm != None:
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self.filter_frm.pack_forget()
			self.filter_frm.destroy()
		self.filter_frm = _Filter_frame(master=self, parent_widget=self, relief=tk.SUNKEN, borderwidth=2)
		self.filter_frm.grid(row=5, column=0, padx=5, pady=5)

class _Clip_frame(tk.Frame):
	def __init__(self, tiepoint, clipboard, selected_bmo, *kargs, **kwargs):
		tk.Frame.__init__(self, *kargs, **kwargs)
		self.tiepoint = tiepoint
		self.clipboard = clipboard
		self.selected_bmo = selected_bmo

		self._draw_structure()

	def _draw_structure(self):
		bmo_list = []
		dms_keylist, cp_hash = self.clipboard.paste_c()
		for dms_key in dms_keylist:
			if self.tiepoint.curr_dms.is_dp_available(dms_key + ':OBJECT'):
				bmo_list.append(dms_key)

		if len(bmo_list) > 0:
			row_idx = 0
			for curr_bmo in bmo_list:
				# create radio buttons of available BMO instances
				btn = tk.Radiobutton(master=self, text=curr_bmo, variable=self.selected_bmo, value=curr_bmo, indicatoron=False)
				btn.grid(row=row_idx, column=0, padx=1, pady=1, sticky='NSEW')
				row_idx += 1
		else:
			lab = tk.Label(master=self, text='no PROMOS object in clipboard...', borderwidth=1, relief=tk.SUNKEN, anchor=tk.W)
			lab.grid(row=0, column=0, padx=1, pady=1, sticky='NSEW')


class _Bmo_frame(tk.Frame):
	def __init__(self, tiepoint, clipboard, *kargs, **kwargs):
		tk.Frame.__init__(self, *kargs, **kwargs)
		self.tiepoint = tiepoint
		self.clipboard = clipboard

		self._draw_structure()

	def _draw_structure(self):
		text_list = [('BMO instance:', self.tiepoint.bmo_instance),
		             ('BMO name:', self.tiepoint.name),
		             ('BMO object:', self.tiepoint.object),
		             ('BMO comment:', self.tiepoint.comment)]

		row_idx = 0
		for curr_tuple in text_list:
			lab = tk.Label(master=self, text=curr_tuple[0], borderwidth=1, relief=tk.SUNKEN, anchor=tk.W)
			lab.grid(row=row_idx, column=0, padx=1, pady=1, sticky='NSEW')

			lab = tk.Label(master=self, text=curr_tuple[1], borderwidth=1, relief=tk.SUNKEN, anchor=tk.W)
			lab.grid(row=row_idx, column=1, padx=1, pady=1, sticky='NSEW')

			myfunc = functools.partial(self._cb_button_to_clipboard, curr_tuple[1])
			btn = tk.Button(master=self, text='to clipboard', command=myfunc)
			btn.grid(row=row_idx, column=2, padx=1, pady=1, sticky='NSEW')

			# popup window with BMO instance in serialized format
			if row_idx == 0:
				myfunc = functools.partial(self._cb_button_popup_serialized, curr_tuple[1])
				btn = tk.Button(master=self, text='popup serialized format', command=myfunc)
				btn.grid(row=row_idx, column=3, padx=1, pady=1, sticky='NSEW')

			row_idx = row_idx + 1


	def _cb_button_to_clipboard(self, text):
		self.clipboard.copy_c(text)


	def _cb_button_popup_serialized(self, dms_key_str):
		curr_text = self.tiepoint.curr_dms.get_serialized_dms_format(dms_key_str)
		popup_win = _Popup_text(curr_text)


class _Dp_frame(tk.Frame):
	def __init__(self, tiepoint, displayfilter, clipboard, *kargs, **kwargs):
		tk.Frame.__init__(self, *kargs, **kwargs)

		self.tiepoint = tiepoint
		self.displayfilter = displayfilter
		self.clipboard = clipboard

		# adding vertical scrollbar to a frame isn't possible...
		# ->we have to create a canvas, then add the scrollbar and a inner frame to current frame
		# http://stackoverflow.com/questions/3085696/adding-a-scrollbar-to-a-group-of-widgets-in-tkinter
		self.canvas = tk.Canvas(self, borderwidth=0, background="gray", width=800, height=500)
		self.frame = tk.Frame(self.canvas, background="gray")
		self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
		self.hsb = tk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
		self.canvas.configure(yscrollcommand=self.vsb.set)
		self.canvas.configure(xscrollcommand=self.hsb.set)

		self.vsb.pack(side="right", fill="y")
		self.hsb.pack(side="bottom", fill="x")
		self.canvas.pack(side="left", fill="both", expand=True)
		self.canvas.create_window((4,4), window=self.frame, anchor="nw",
                                  tags="self.frame")

		self.frame.bind("<Configure>", self._onFrameConfigure)

		self._draw_structure()


	def _onFrameConfigure(self, event):
		'''Reset the scroll region to encompass the inner frame'''
		self.canvas.configure(scrollregion=self.canvas.bbox("all"))


	def _draw_structure(self):
		row_idx = 0

		# table header line
		column_idx = 0
		for curr_text in ['datapoint', 'datatype', 'comment', 'PAR_OUT', 'SDriver datapoint', 'PAR_IN']:
			lab = tk.Label(master=self.frame, text=curr_text, borderwidth=1, relief=tk.SUNKEN)
			lab.grid(row=row_idx, column=column_idx, padx=1, pady=1, sticky='NSEW')
			column_idx = column_idx + 1
		# special header cell: copy to clipboard
		lab = tk.Label(master=self.frame, text='copy DMS-key to clipboard', borderwidth=1, relief=tk.SUNKEN)
		lab.grid(row=row_idx, column=column_idx, padx=1, pady=1, columnspan=2, sticky='NSEW')
		column_idx = column_idx + 2
		# header cell: open popup window with serialized DMS format
		lab = tk.Label(master=self.frame, text='serialized DMS', borderwidth=1, relief=tk.SUNKEN)
		lab.grid(row=row_idx, column=column_idx, padx=1, pady=1, columnspan=2, sticky='NSEW')

		row_idx = row_idx + 1
		for child in sorted(self.tiepoint.dp_dict):
			# check if this datapoint matches the display filter
			curr_dp_property = Bmo_dp.get_dp_properties(self.tiepoint.dp_dict[child])
			if curr_dp_property.issuperset(self.displayfilter):
				# current datapoint has one or more required properties (according to current displayfilter)

				# datapoint
				lab = tk.Label(master=self.frame, text=child, borderwidth=1, relief=tk.SUNKEN, anchor=tk.W)
				lab.grid(row=row_idx, column=0, padx=1, pady=1, sticky='NSEW')

				# datatype
				if self.tiepoint.dp_dict[child].is_digital:
					curr_text, curr_color = 'digital', 'red'
				elif self.tiepoint.dp_dict[child].is_analog:
					curr_text, curr_color = 'analog', 'green'
				else:
					curr_text, curr_color = '', 'gray'
				lab = tk.Label(master=self.frame, text=curr_text, background=curr_color, borderwidth=1, relief=tk.SUNKEN)
				lab.grid(row=row_idx, column=1, padx=1, pady=1, sticky='NSEW')

				# comment
				lab = tk.Label(master=self.frame, text=self.tiepoint.dp_dict[child].comment, borderwidth=1, relief=tk.SUNKEN, anchor=tk.W)
				lab.grid(row=row_idx, column=2, padx=1, pady=1, sticky='NSEW')

				# PAR_OUT
				if self.tiepoint.dp_dict[child].is_par_out:
					curr_text, curr_color = 'PAR_OUT', 'yellow'
				else:
					curr_text, curr_color = '', None
				lab = tk.Label(master=self.frame, text=curr_text, borderwidth=1, relief=tk.SUNKEN)
				if curr_color != None:
					lab.config(background=curr_color)
				lab.grid(row=row_idx, column=3, padx=1, pady=1, sticky='NSEW')

				# SDriver datapoint (communicated between DMS and PLC)
				if self.tiepoint.dp_dict[child].is_plc:
					curr_text, curr_color = 'PLC', 'yellow'
				else:
					curr_text, curr_color = '', None
				lab = tk.Label(master=self.frame, text=curr_text, borderwidth=1, relief=tk.SUNKEN)
				if curr_color != None:
					lab.config(background=curr_color)
				lab.grid(row=row_idx, column=4, padx=1, pady=1, sticky='NSEW')

				# PAR_IN
				if self.tiepoint.dp_dict[child].is_par_in:
					curr_text, curr_color = 'PAR_IN', 'yellow'
				else:
					curr_text, curr_color = '', None
				lab = tk.Label(master=self.frame, text=curr_text, borderwidth=1, relief=tk.SUNKEN)
				if curr_color != None:
					lab.config(background=curr_color)
				lab.grid(row=row_idx, column=5, padx=1, pady=1, sticky='NSEW')

				# button: copy to clipboard
				# Warning: Tkinter callbacks can't be defined directly with arguments
				# ->Using a lambda function works only when the argument is a fixed value:
				#   command=lambda: self._cb_button_activate(1)
				# ->"child" is always the last loop value when called this way:
				#   command=lambda: self._cb_button_to_clipboard(child)
				# =>using "partial" from functools:
				# http://stackoverflow.com/questions/6920302/how-to-pass-arguments-to-a-button-command-in-tkinter
				myfunc = functools.partial(self._cb_button_to_clipboard_normal, child)
				btn = tk.Button(master=self.frame, text='normal', command=myfunc)
				btn.grid(row=row_idx, column=6, sticky=tk.N + tk.S + tk.E + tk.W)

				if self.tiepoint.dp_dict[child].is_plc:
					myfunc = functools.partial(self._cb_button_to_clipboard_pg5, child)
					btn = tk.Button(master=self.frame, text='PG5 Symbol', command=myfunc)
					btn.grid(row=row_idx, column=7, sticky=tk.N + tk.S + tk.E + tk.W)

				# button: show datapoint in serialized DMS format in a popup window
				myfunc = functools.partial(self._cb_button_popup_serialized, child)
				btn = tk.Button(master=self.frame, text='popup window', command=myfunc)
				btn.grid(row=row_idx, column=8, sticky=tk.N + tk.S + tk.E + tk.W)


				row_idx = row_idx  + 1


	def _cb_button_to_clipboard_normal(self, child):
		"""
		copy DMS-key as string in format <BMO instance>:<PLC DMS-datapoint> to clipboard
		=>ready to include into property fields of Visi.Plus graphic elements or PAR_IN / PAR_DATA links
		"""
		self.clipboard.copy_c(':'.join([self.tiepoint.bmo_instance, child]))

	def _cb_button_to_clipboard_pg5(self, child):
		"""
		copy DMS-key as string <BMO instance>.<PLC DMS-datapoint> to clipboard,
		but in PG5 symbol format (character replacement same as defined in "sdriver.pet")
		=>ready to insert as PG5 symbol in Fupla editor, should exist in Fupla resource file after regular code generation

		Details: usually names of DMS nodes build an own PG5 symbol group (means replacement of ':' by '.', BUT THERE ARE EXCEPTIONS!
		"""
		plc_dp_list = self.tiepoint.bmo_instance.split(':')
		plc_dp_list.append(child)

		# remove PLC-part
		plc_dp_list = plc_dp_list[1:]

		# combine string (DMS nodes starting with digit were appended with '_' to the previous DMS node)
		plc_dp_str = ''
		for idx, node in enumerate(plc_dp_list):
			if node[0].isdigit():
				# PG5 groups beginning with digit are invalid!
				if idx == 0:
					# PG5 symbols beginning with digit are invalid!
					# first DMS level has to start with character, otherwise PET generates invalid symbol!!!
					plc_dp_str = 'INVALID_SYMBOL__DMS_NODE_MUST_START_WITH_CHARACTER'
					break
				else:
					# DMS nodes beginning with digits don't create own PG5 symbol group, they were appended to previous group...
					plc_dp_str = '_'.join([plc_dp_str, node])
			elif idx == 0:
				# toplevel DMS node -> toplevel PG5 symbol group
				plc_dp_str = node
			else:
				# build a new PG5 symbol group
				plc_dp_str = '.'.join([plc_dp_str, node])

		# do character-based replacements according to conversion rules in "sdriver.pet"
		repl_list = [(' ',  '.'),   # space
		             ('/',   '.'),  # slash
		             ('+',   '.'),  # plus
		             ('-',   '.')]  # minus
		for repl in repl_list:
			plc_dp_str = plc_dp_str.replace(repl[0], repl[1])

		self.clipboard.copy_c(plc_dp_str)


	def _cb_button_popup_serialized(self, child):
		dms_fullkey = ':'.join([self.tiepoint.bmo_instance, child])
		curr_text = self.tiepoint.curr_dms.get_serialized_dms_format(dms_fullkey)
		popup_win = _Popup_text(curr_text)


class _Filter_frame(tk.Frame):
	def __init__(self, parent_widget, *kargs, **kwargs):
		tk.Frame.__init__(self, *kargs, **kwargs)
		self.parent_widget = parent_widget
		currfilter = self.parent_widget.currfilter

		self._show_analog = None
		self._show_digital = None
		self._show_misc = None
		self._show_par_out = None
		self._show_plc = None
		self._show_par_in = None
		self.dp_list = [[self._show_analog, Bmo_dp.ANALOG, 'analog'],
		           [self._show_digital, Bmo_dp.DIGITAL, 'digital'],
		           [self._show_misc, Bmo_dp.MISC , 'miscellaneous'],
		           [self._show_par_out, Bmo_dp.PAR_OUT, 'PAR_OUT'],
		           [self._show_plc, Bmo_dp.PLC, 'communicated/PLC'],
		           [self._show_par_in, Bmo_dp.PAR_IN, 'PAR_IN']]

		# initialize all checkbox-variables to their value of given display filter
		for item in self.dp_list:
			curr_val = item[1] in currfilter
			item[0] = tk.BooleanVar(value=curr_val)

		self._draw_structure()


	def _draw_structure(self):
		lab = tk.Label(master=self, text="Filter: Show only datapoints containing these property:")
		lab.grid(row=0, column=0, columnspan=4)

		curr_col = 0
		for item in self.dp_list:
			cbtn = tk.Checkbutton(master=self, text=item[2], variable=item[0], command=self._cb_checkbutton)
			cbtn.grid(row=1, column=curr_col, padx=5)
			curr_col = curr_col + 1


	def _cb_checkbutton(self):
		# FIXME: it would be more efficient to synchronize only changed variable with the filter,
		# instead of recreating it on every change of one variable...

		# set display filter and redraw the frames
		curr_set = set()
		for item in self.dp_list:
			if item[0].get():
				curr_set.add(item[1])
		self.parent_widget.currfilter = curr_set
		self.parent_widget._cb_draw_infoframes()


class _Popup_text(tk.Toplevel):
	def __init__(self, text_str, *kargs, **kwargs):
		tk.Toplevel.__init__(self, *kargs, **kwargs)
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

	curr_cp = misc.clipboard.Clipboard()
	mytest = ''
	if mytest == '':
		# haven't found a BMO instance on clipboard... setting testvalue
		mytest = 'MSR01_1:H10:Uwp'
	curr_Bmo = Bmo_instance(curr_dms, mytest)
	rootwindow = TiepointGui(curr_Bmo, curr_cp)

	rootwindow.mainloop()

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)