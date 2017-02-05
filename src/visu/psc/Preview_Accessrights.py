#!/usr/bin/env python
# encoding: utf-8
"""
visu.psc.Preview_Accessrights.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import os
import sys
from visu.psc import Parser
import Tkinter, Tkconstants, tkFileDialog
import re



DEBUGGING = False
ENCODING_FILES_PSC = 'cp1252'
ENCODING_SRC_FILE = 'utf-8'
ENCODING_STDOUT = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

rights_list = None


def get_encoding():
	global ENCODING_STDOUT
	# following code doesn't work in IDE
	ENCODING_STDOUT = sys.stdout.encoding or sys.getfilesystemencoding()

def my_print(line):
	"""
	wrapper for print()-function:
	-does explicit conversion from unicode to encoded byte-string
	-when parameter is already a encoded byte-string, then convert to unicode using "encoding cookie" and then to encoded byte-string
	"""
	unicode_line = ''
	if type(line) == str:
		# conversion byte-string -> unicode -> byte-string
		# (first encoding is source file encoding, second one is encoding of console)
		unicode_line = line.decode(ENCODING_SRC_FILE)
	else:
		# assuming unicode-string (we don't care about other situations, when called with wrong datatype then print() will throw exception)
		unicode_line = line

	if not ENCODING_STDOUT:
		get_encoding()
	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	print(unicode_line.encode(ENCODING_STDOUT, errors='replace'))


class PSC_Input_Element(object):
	"""
	drawing informations of one PSC input element
	"""
	COLORS_LIST = ["red", "blue", "green", "yellow", "orange"]
	def __init__(self, rectangle_obj, draw_order):
		self.rectangle_obj = rectangle_obj
		# every element should have a color which doesn't change
		self.draw_order = draw_order
		nof_colors = len(PSC_Input_Element.COLORS_LIST)
		self.color = PSC_Input_Element.COLORS_LIST[draw_order % nof_colors]

	def get_coordinates(self):
		return self.rectangle_obj.get_coordinates()


class Input_Elements_Handler(object):
	"""
	extracts data of PSC input elements
	"""
	def __init__(self):
		self.fname = None

	def set_psc_file(self, fname):
		self.fname = fname
		self.curr_file = Parser.PscFile(self.fname)
		self.curr_file.parse_file()

	def is_ready(self):
		return self.fname != None

	def _filter_elements(self, user_accessrights_set, draw_options={}):
		"""
		returns PSC elements which are active with given accessrights
		"""

		curr_elem_list = []
		input_elements = [u'Button', u'Checkbox', u'Combobox', u'Editbox', u'Icon', u'Radio Button']
		global rights_list
		for elem in self.curr_file.get_psc_elem_list():
			curr_id = elem.get_property(u'id')
			if curr_id in input_elements:
				element_rights_set = set()
				for right in rights_list:
					try:
						if elem.get_property(right):
							element_rights_set.add(right)
					except KeyError:
						# PSC element doesn't contain initialisation
						pass
				if DEBUGGING:
					my_print(u'_filter_elements(): element_rights_set=' + repr(element_rights_set))

				# PSC element is for a user not usable when...
				#  -element has one or more levels set and user doesn't have one of these userlevels
				#  -this element is invisible (by a PSDV field or initialisation with DMS key e.g. "System:User:<HOSTNAME>:Rights:Level<LEVEL>")

				# apply access levels
				show_elem_level = False
				if len(element_rights_set) == 0:
					# input element has no levels set =>always show it
					show_elem_level = True
				elif len(user_accessrights_set & element_rights_set) > 0:
					# user has at least one common level with input element.. =>show it
					show_elem_level = True

				show_elem_visibility = False
				# apply visibility (only elements which have configured "visibility" are clickable)
				if elem.get_property(u'visibility'):
					show_elem_visibility = True
				try:
					# analyze initialisiation for user level DMS key
					dmskey = elem.get_property(u'init-visibility-dmskey')
					re_pattern = r'System:User:[\w_\.]+:Rights:Level(\d+)'
					m = re.match(re_pattern, dmskey)
					if m:
						# regex match group contains now userlevel
						level_str = m.group(1)
						if (u'accessrights-userlevel' + level_str) in element_rights_set:
							# user has at least one common level with input element.. =>show it
							show_elem_visibility = True
				except KeyError:
					# PSC element (does not have initialisation for visibility)
					show_elem_visibility = True


				hide_elem_according_draw_option = False
				if "show_only_restricted" in draw_options:
					# hide elements without restriction
					if len(element_rights_set) == 0:
						hide_elem_according_draw_option = True

				# combine access level, visibility and draw option
				if DEBUGGING:
					my_print(u'_filter_elements(): show_elem_level=' + repr(show_elem_level) + u', show_elem_visibility=' + repr(show_elem_visibility))
				if show_elem_level and show_elem_visibility and not hide_elem_according_draw_option:
					# we have to draw this PSC element
					curr_elem_list.append(elem)
		if DEBUGGING:
			my_print(u'_filter_elements(): curr_elem_list contains now ' + str(len(curr_elem_list)) + u' items')
		return curr_elem_list


	def draw_elements(self, user_accessrights_set, canvas_visu, draw_options=None):
		curr_draw_list = []

		# collect information for draw this element
		for elem in self._filter_elements(user_accessrights_set, draw_options):
			rect_obj = elem.get_property(u'selection-area')
			draw_order = elem.get_property(u'draw-order')
			curr_draw_list.append(PSC_Input_Element(rect_obj, draw_order))

		# draw this list on main canvas
		for elem in curr_draw_list:
			if DEBUGGING:
				my_print(u'draw_elements(): elem.get_coordinates()=' + repr(elem.get_coordinates()))
			x1, y1, x2, y2 = elem.get_coordinates()
			canvas_visu.create_rectangle(x1, y1, x2, y2, fill=elem.color, outline=elem.color)

		return curr_draw_list



class myGUI(Tkinter.Frame):
	# example code from http://zetcode.com/gui/tkinter/layout/

	ROOT_TITLE = "ViSi+ PSC userlevel previewer"
	SIDEVIEW_DEPTH = 3  # the boxes per element has a imaginary "depth" in pixels when watched from side...
	def __init__(self, parent, psc_handler):
		Tkinter.Frame.__init__(self, parent)
		self.parent = parent
		# settings of rootwindow
		self.parent.title(myGUI.ROOT_TITLE + u' - no PSC file loaded')

		self.psc_handler = psc_handler
		self.user_accessrights_set = set()

		self._userlevels_dict = {}
		self._buildFormular()
		self._draw_frame = Tkinter.Frame(master=self)
		self._canvas_sideview = None
		self._buildSideview(parent=self._draw_frame)
		self._canvas_visu = None
		self._buildCanvasVisu(parent=self._draw_frame)
		self._draw_frame.pack(fill=Tkinter.BOTH, expand=True)
		self.pack(fill=Tkinter.BOTH, expand=True)

	def _buildFormular(self):

		self._frame_formular = Tkinter.Frame(master=self)

		btn = Tkinter.Button(self._frame_formular, text='Select PSC file...', command=self._cb_button_selectfile)
		btn.pack(fill=Tkconstants.BOTH, padx=5, pady=5)

		lab = Tkinter.Label(self._frame_formular, text='userlevels of previewed user:', anchor=Tkinter.W)
		lab.pack(padx=5, pady=5, fill=Tkinter.BOTH, expand=True)

		frame_checkboxes = Tkinter.Frame(master=self._frame_formular)
		global rights_list
		for right in rights_list:
			right_int = int(right[-2:])
			self._userlevels_dict[right_int] = Tkinter.BooleanVar(False)
			checkbox = Tkinter.Checkbutton(master=frame_checkboxes,
			                               text=str(right_int),
			                               variable=self._userlevels_dict[right_int],
			                               command=self._cb_checkbox_userlevel)
			checkbox.pack(side=Tkinter.LEFT)

		# button for resetting all userlevels
		btn = Tkinter.Button(master=frame_checkboxes,
		                     text="reset userlevels",
		                     command=self._cb_button_reset_userlevels)
		btn.pack(side=Tkinter.LEFT)

		# button for setting all userlevels
		btn = Tkinter.Button(master=frame_checkboxes,
		                     text="set all userlevels",
		                     command=self._cb_button_set_all_userlevels)
		btn.pack(side=Tkinter.LEFT)


		# checkbox for showing only input elements with restrictions
		self._show_only_restricted = Tkinter.BooleanVar(False)
		checkbox = Tkinter.Checkbutton(master=frame_checkboxes,
		                               text="show only restricted elements",
		                               variable=self._show_only_restricted,
		                               command=self._cb_checkbox_show_only_restricted)
		checkbox.pack(side=Tkinter.LEFT)

		frame_checkboxes.pack(fill=Tkconstants.BOTH, padx=5, pady=5)

		self._frame_formular.pack(fill=Tkconstants.BOTH, padx=5, pady=5)
		#for right in rights_list:


	def _buildCanvasVisu(self, parent):
		if self._canvas_visu:
			# widget already exists... =>delete it for redrawing
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self._canvas_visu.grid_forget()
			self._canvas_visu.destroy()
		self._canvas_visu = Tkinter.Canvas(parent, width=1280, height=1024, background="white")
		self._canvas_visu.grid(row=0, column=1, padx=5)


	def _buildSideview(self, parent, nofelements=0):
		if self._canvas_sideview:
			# widget already exists... =>delete it for redrawing
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self._canvas_sideview.grid_forget()
			self._canvas_sideview.destroy()

		self._canvas_sideview = Tkinter.Canvas(parent, width=max(nofelements * myGUI.SIDEVIEW_DEPTH, 50), height=1024, background="white")
		self._canvas_sideview.grid(row=0, column=0, padx=5)


	def _cb_button_selectfile(self):
		# file browser
		# (example from http://tkinter.unpythonic.net/wiki/tkFileDialog )

		# define options for opening or saving a file
		file_opt = options = {}
		options['defaultextension'] = '.psc'
		options['filetypes'] = [('PSC files', '.psc'), ('all files', '.*')]
		options['initialdir'] = 'C:\\'
		options['initialfile'] = ''
		options['parent'] = self._frame_formular
		options['title'] = 'Select PSC file for preview'

		filename = tkFileDialog.askopenfilename(**file_opt)
		if filename:
			# settings of rootwindow
			self.parent.title(myGUI.ROOT_TITLE + u' - ' + filename)

			# preset parser and load PSC image
			self.psc_handler.set_psc_file(filename)
			self._cb_checkbox_userlevel()
			self._update_canvas()


	def _cb_checkbox_userlevel(self):
		# user changed checkbox =>update userlevel
		global rights_list
		for right in rights_list:
			right_int = int(right[-2:])
			if self._userlevels_dict[right_int].get():
				# this level is set
				self.user_accessrights_set.add(right)
			else:
				# this level is not set
				self.user_accessrights_set.discard(right)

		# when PSC file is loaded then update canvas
		if self.psc_handler.is_ready():
			self._update_canvas()


	def _cb_button_reset_userlevels(self):
		# reset all userlevels
		global rights_list
		for right in rights_list:
			self.user_accessrights_set.discard(right)
			right_int = int(right[-2:])
			self._userlevels_dict[right_int].set(False)

		# when PSC file is loaded then update canvas
		if self.psc_handler.is_ready():
			self._update_canvas()

	def _cb_button_set_all_userlevels(self):
		# set all userlevels
		global rights_list
		for right in rights_list:
			self.user_accessrights_set.add(right)
			right_int = int(right[-2:])
			self._userlevels_dict[right_int].set(True)

		# when PSC file is loaded then update canvas
		if self.psc_handler.is_ready():
			self._update_canvas()


	def _cb_checkbox_show_only_restricted(self):
		# when PSC file is loaded then update canvas
		if self.psc_handler.is_ready():
			self._update_canvas()


	def _update_canvas(self):
		self._buildCanvasVisu(parent=self._draw_frame)
		if DEBUGGING:
			my_print(u'_update_canvas(): self.user_accessrights_set' + repr(self.user_accessrights_set) + u', self._canvas_visu=' + repr(self._canvas_visu))

		draw_options = {}
		if self._show_only_restricted.get():
			draw_options["show_only_restricted"] = True

		curr_draw_list = self.psc_handler.draw_elements(user_accessrights_set=self.user_accessrights_set, canvas_visu=self._canvas_visu, draw_options=draw_options)

		# draw sideview canvas
		self._buildSideview(parent=self._draw_frame, nofelements=len(self.psc_handler.curr_file.get_psc_elem_list()))
		for elem in curr_draw_list:
			x1, y1, x2, y2 = elem.get_coordinates()
			# position on sideview:
			# y1 <= Y <= y2
			# X-axes is "draw-order" * myGUI.SIDEVIEW_DEPTH
			# =>place all pixels on right place without overlapping
			x1 = (elem.draw_order - 1) * myGUI.SIDEVIEW_DEPTH + 1
			x2 = elem.draw_order * myGUI.SIDEVIEW_DEPTH
			self._canvas_sideview.create_rectangle(x1, y1, x2, y2, fill=elem.color, outline=elem.color)



def main(argv=None):
	# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
	Parser.PscParser.load_config(Parser.PARSERCONFIGFILE)

	global rights_list
	rights_list = map(lambda x: u'accessrights-userlevel' + unicode(x).zfill(2), range(1, 17))

	curr_psc_handler = Input_Elements_Handler()

	# Build a gui
	rootWindow = Tkinter.Tk()
	app = myGUI(rootWindow, curr_psc_handler)

	# Keeps GUI mainloop running until GUI is closed
	rootWindow.mainloop()

	return 0        # success


if __name__ == '__main__':
	get_encoding()
	status = main()
	# sys.exit(status)