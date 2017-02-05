#!/usr/bin/env python
# encoding: utf-8
"""
tools.PSC_file_selector.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

# KNOWN BUGS:
# -I tried to print debugging messages to STDOUT of the used Regex-Patterns (filename, textsearch),
# but couldn't solve encoding problems with German umlaute on German Windows 7 command prompt (executing a py2exe compilation of this script)


# loosely based on directory browser using Ttk Treeview.
# , which based on the demo found in Tk 8.5 library/demos/browse
# example from http://svn.python.org/projects/python/trunk/Demo/tkinter/ttk/dirbrowser.py

import locale
import dms.dmspipe
import os
import sys
import Tkinter
import ttk
import re
import datetime
from operator import itemgetter
import codecs
import subprocess
import misc.clipboard

ROOTWINDOW_TITLE = u'PSC file selector v0.2.0'
USAGE_HINT_TEXT = u'Usage hints: double-click = open in GE // right-click = context-menu // header-click = sorting columns'


ENCODING_FILES_PSC = 'windows-1252'
ENCODING_SRC_FILE = 'utf-8'
ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = True

def get_encoding():
	global ENCODING_STDOUT1
	# following code seems only to work in IDE...
	ENCODING_STDOUT1= sys.stdout.encoding or sys.getfilesystemencoding()

	# hint from http://stackoverflow.com/questions/9226516/python-windows-console-and-encodings-cp-850-vs-cp1252
	# following code doesn't work in IDE because PyCharm uses UTF-8 and not encoding from Windows command prompt...
	global ENCODING_STDOUT2
	ENCODING_STDOUT2 = locale.getpreferredencoding()

	# another try: using encoding-guessing of IDE "IDLE"
	# hint from https://mail.python.org/pipermail/tkinter-discuss/2010-December/002602.html
	global ENCODING_LOCALE
	import idlelib.IOBinding
	ENCODING_LOCALE = idlelib.IOBinding.encoding
	print(u'Using encoding "' + ENCODING_LOCALE + u'" for input and trying "' + ENCODING_STDOUT1 + u'" or "' + ENCODING_STDOUT2 + u'" for STDOUT')

def my_print(line):
	"""
	wrapper for print()-function:
	-does explicit conversion from unicode to encoded byte-string
	-when parameter is already a encoded byte-string, then convert to unicode using "encoding cookie" and then to encoded byte-string
	"""
	unicode_line = u''
	if type(line) == str:
		# conversion byte-string -> unicode -> byte-string
		# (first encoding is source file encoding, second one is encoding of console)
		if not ENCODING_LOCALE:
			get_encoding()
		unicode_line = line.decode(ENCODING_LOCALE)
	else:
		# assuming unicode-string (we don't care about other situations, when called with wrong datatype then print() will throw exception)
		unicode_line = line

	if not (ENCODING_STDOUT1 and ENCODING_STDOUT2):
		get_encoding()
	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	try:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT1, errors='strict')
	except UnicodeEncodeError:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT2, errors='strict')
	print(bytestring_line)



class PscFile(object):
	def __init__(self, fullpath):
		self._fullpath = fullpath
		self._whole_file = u''
		self._modification_time = 0
		self._filesize = 0
		self._last_readtime = -1

	def _read_metadata(self):
		stat = os.stat(self._fullpath)
		self._filesize = stat.st_size
		self._modification_time = stat.st_mtime

	def get_whole_file(self):
		self._read_metadata()
		if self._last_readtime <> self._modification_time:
			# first reading or file changed
			with codecs.open(self._fullpath, 'r', encoding=ENCODING_FILES_PSC) as f:
				self._whole_file = f.read()
				self._last_readtime = self._modification_time
		return self._whole_file

	def get_metadata(self):
		# examples from http://stackoverflow.com/questions/39359245/from-stat-st-mtime-to-datetime
		# and http://stackoverflow.com/questions/6591931/getting-file-size-in-python
		# and https://docs.python.org/2/library/stat.html
		# and http://stackoverflow.com/questions/455612/limiting-floats-to-two-decimal-points
		# and http://stackoverflow.com/questions/311627/how-to-print-date-in-a-regular-format-in-python
		self._read_metadata()
		size = float("{0:.2f}".format(self._filesize / 1024.0))
		mod_time = datetime.datetime.fromtimestamp(self._modification_time).strftime("%Y.%m.%d %H:%M:%S")
		return size, mod_time


class PscFileHandler(object):
	def __init__(self):
		self._pscfiles_dict = {}
		self._selected_files = set()

	def get_file(self, filename):
		return self._pscfiles_dict[filename]

	def select_file(self, filename, fullpath):
		self._selected_files.add(filename)
		if filename not in self._pscfiles_dict:
			self._pscfiles_dict[filename] = PscFile(fullpath)

	def deselect_file(self, filename):
		self._selected_files.discard(filename)

	def clear_file_selection(self):
		self._selected_files.clear()

	def get_file_selection(self):
		return list(self._selected_files)


class Dirlister(object):
	def __init__(self, path):
		self._path = path
		self._filehandler = PscFileHandler()

	def get_listing(self, re_fname_pattern='', re_string_pattern='', sort_item=0, reversed=False):
		# collecting filenames
		self._filehandler.clear_file_selection()
		for entry in os.listdir(self._path):
			fullpath = os.path.join(self._path, entry)
			if os.path.isfile(fullpath):
				if entry.split(os.extsep)[-1].upper() == u'PSC':
					if re.search(re_fname_pattern, entry):
						# regex search returned a match object =>mark filename for further filtering
						self._filehandler.select_file(entry, fullpath)

		# analyze PSC files content
		# =>removing file when it doesn't match
		# (currently only a very basic textsearch)
		for filename in self._filehandler.get_file_selection():
			curr_file = self._filehandler.get_file(filename)
			if not re.search(re_string_pattern, curr_file.get_whole_file()):
				# regex search didn't returned a match object...
				self._filehandler.deselect_file(filename)

		# collect metadata
		detail_list = []
		for filename in self._filehandler.get_file_selection():
			curr_file = self._filehandler.get_file(filename)
			size, mod_time = curr_file.get_metadata()

			# search for color "magenta" (integer value 16711935=magenta) =>we ignore false positive results...
			if u'16711935' in curr_file.get_whole_file():
				contains_magenta = True
			else:
				contains_magenta = False

			# add everything together as tuple
			detail_list.append((filename, size, mod_time, contains_magenta))

		# sort list by item specified by caller
		# based on example from http://stackoverflow.com/questions/10695139/sort-a-list-of-tuples-by-2nd-item-integer-value
		return sorted(detail_list, key=itemgetter(sort_item), reverse=reversed)



class FileSelectorGUI(Tkinter.Tk):
	RE_PATTERN_UNDERSCORE = r'__.*'
	RE_PATTERN_ALL_PSC = r'.*'
	RE_PATTERN_VLO_COLLECTION = r'VLO-Collection_Part\d+'

	def __init__(self, curr_DMS, curr_image_dp, curr_src_path, curr_clipboard):
		Tkinter.Tk.__init__(self)
		self.minsize(width=800, height=700)
		self.wm_title(ROOTWINDOW_TITLE)

		self._curr_DMS = curr_DMS
		self._curr_image_dp = curr_image_dp
		self.curr_src_path = curr_src_path
		self._curr_clipboard = curr_clipboard
		self._dirlister = Dirlister(self.curr_src_path)

		# sorting order in tuple returned by Dirlister.get_listing()
		self._sort_by_column_no = 0
		self._inverse_sorting = False

		self.tree = None

		self.file_regex_pattern = Tkinter.StringVar()
		self.file_regex_pattern.trace('w', self._cb_entry_filepattern)

		self.string_regex_pattern = Tkinter.StringVar()
		self.string_regex_pattern.trace('w', self._cb_entry_stringpattern)

		file_regex_entrybox = Tkinter.Entry(self, textvariable=self.file_regex_pattern)
		file_regex_entrybox.insert(0, FileSelectorGUI.RE_PATTERN_UNDERSCORE)
		file_regex_entrybox.config(width=80)

		file_regex_label = Tkinter.Label(self, text=u'Regex-pattern for filenames (re.search):')

		string_regex_entrybox = Tkinter.Entry(self, textvariable=self.string_regex_pattern)
		string_regex_entrybox.insert(0, '')
		string_regex_entrybox.config(width=80)

		string_regex_label = Tkinter.Label(self, text=u'Regex-pattern for strings (re.search):')

		button_frame = Tkinter.Frame(master=self, bd=1, relief='sunken')
		btn_underscore = Tkinter.Button(button_frame, text=u'Set Pattern "UNDERSCORE"', command=self._cb_btn_underscore)
		btn_all_psc = Tkinter.Button(button_frame, text=u'Set Pattern "ALL_PSC"', command=self._cb_btn_all_psc)
		btn_vlo_collection = Tkinter.Button(button_frame, text=u'Set Pattern "VLO_COLLECTION"', command=self._cb_btn_vlo_collection)
		btn_Quit = Tkinter.Button(button_frame, text='Quit', command=self.quit)

		self._draw_tree()
		self.populate_tree()

		# preparation of popup window (context menu on right-click)
		# code example from http://effbot.org/zone/tkinter-popup-menu.htm
		self.context_menu = Tkinter.Menu(self, tearoff=0)
		self.context_menu.add_command(label="open in GE", font="-weight bold", command=self._cb_open_grafikeditor)
		self.context_menu.add_command(label="open Windows Explorer", command=self._cb_open_windows_explorer)
		self.context_menu.add_command(label="open in Notepad++", command=self._cb_open_notepad)
		self.context_menu.add_command(label="copy filename to clipboard", command=self._cb_fname_to_clipboard)

		# display usage/hint label with bold text:
		# http://stackoverflow.com/questions/4072150/how-to-change-a-widgets-font-style-without-knowing-the-widgets-font-family-siz
		usage_label = Tkinter.Label(self, text=USAGE_HINT_TEXT, font="-weight bold")
		usage_label.grid(row=2, column=0, sticky='w', padx=4, pady=8)

		file_regex_entrybox.grid(row=3, column=0, sticky='e', padx=4 , pady=4)
		file_regex_label.grid(row=3, column=0, sticky='w', padx=4 , pady=4)

		string_regex_entrybox.grid(row=4, column=0, sticky='e', padx=4 , pady=4)
		string_regex_label.grid(row=4, column=0, sticky='w', padx=4 , pady=4)

		btn_underscore.pack(side='left')
		btn_all_psc.pack(side='left')
		btn_vlo_collection.pack(side='left')
		# FIXME: Button "btn_Quit" doesn't gets placed on the right side...Why?!?
		btn_Quit.pack(side='right', padx=30, anchor='e')
		button_frame.grid(row=5, column=0, sticky='w', padx=4 , pady=4)

		self.grid_columnconfigure(0, weight=1)
		self.grid_rowconfigure(0, weight=1)


	def _draw_tree(self):
		# first run: create tree
		vsb = ttk.Scrollbar(orient="vertical")
		hsb = ttk.Scrollbar(orient="horizontal")

		self.tree = ttk.Treeview(master=self,
		                         yscrollcommand=vsb.set,
		                         xscrollcommand=hsb.set)

		self.tree.bind('<Button-1>', self.singleclick_handler)
		self.tree.bind('<Double-Button-1>', self.doubleclick_handler)
		self.tree.bind('<Button-3>', self.rightclick_handler)

		self.tree["columns"] = ("two", "three", "four")
		self.tree.column("two", stretch=1, width=50, anchor='e')
		self.tree.column("three", stretch=1, width=50, anchor='center')
		self.tree.column("four", stretch=1, width=50, anchor='center')
		self.tree.heading("#0", text=u"PSC filename")
		self.tree.heading("two", text=u"size [kByte]")
		self.tree.heading("three", text=u"modification date")
		self.tree.heading("four", text=u"contains magenta")

		self.tree.grid(row=0, column=0, sticky='nswe')

		vsb['command'] = self.tree.yview
		hsb['command'] = self.tree.xview

		# Arrange the scrollbars in the toplevel
		vsb.grid(row=0, column=1, sticky='ns')
		hsb.grid(row=1, column=0, sticky='ew')


	def populate_tree(self):
		if self.tree:
			# tree does exist... first delete all items of this tree
			# code from http://stackoverflow.com/questions/8830507/how-to-clear-items-from-a-ttk-treeview-widget
			children = self.tree.get_children()
			for item in children:
				self.tree.delete(item)

			# fill tree with content
			for mytuple in self._dirlister.get_listing(re_fname_pattern=self.file_regex_pattern.get(),
			                                           re_string_pattern=self.string_regex_pattern.get(),
			                                           sort_item=self._sort_by_column_no,
			                                           reversed=self._inverse_sorting):
				if len(mytuple) == 4:
					# problems with umlaut in filename...
					# https://bytes.com/topic/python/answers/34606-how-display-unicode-label-tkinter
					fname = unicode(mytuple[0], encoding=ENCODING_FILENAMES, errors='strict')
					#fname = unicode(mytuple[0], encoding='iso8859-1', errors='replace')
					self.tree.insert("", "end", text=fname, values=(mytuple[1], mytuple[2], mytuple[3]))

	def _get_clicked_filename(self, event=None):
		"""
		called by Tkinter callbacks for getting the filename of a clicked tree entry
		"""
		if event:
			# idea from http://stackoverflow.com/questions/3794268/command-for-clicking-on-the-items-of-a-tkinter-treeview-widget
			curr_item = self.tree.identify('item', event.x, event.y)
		else:
			# getting item-ID of the first selected tree item
			# (used when there's no direct click event on row, e.g. in popup context menu)
			# help from https://docs.python.org/dev/library/tkinter.ttk.html#treeview
			curr_item = self.tree.selection()[0]
		return self.tree.item(curr_item, "text")

	def _get_clicked_fullpath(self, event=None):
		"""
		called by Tkinter callbacks for getting the fullpath of a clicked tree entry
		"""
		fname = self._get_clicked_filename(event)
		return os.path.join(self.curr_src_path, fname)

	def doubleclick_handler(self, event):
		fullpath = self._get_clicked_filename(event)

		# set this file in GE (Grafikeditor) if possible
		if fullpath.split('.')[-1].upper() == u'PSC':
			# write filename to the right DMS datapoint
			self._curr_DMS.pyDMS_WriteSTREx(self._curr_image_dp, fullpath)

	def singleclick_handler(self, event):
		"""
		clicking onto header =>sort by this column
		click a second time on same header =>inverse sorting of this column
		"""
		# idea from http://stackoverflow.com/questions/31584415/how-to-bind-an-action-to-the-heading-of-a-tkinter-treeview-in-python
		# format is a string '#x' where x stands for column number (#0 is "icon column", #1 is first column, ...)

		region = self.tree.identify("region", event.x, event.y)
		if region == "heading":
			old_sort_column = self._sort_by_column_no

			column_str = self.tree.identify_column(event.x)
			#print('user clicked in column "' + repr(column) + '"')
			self._sort_by_column_no = int(column_str[1:])
			if old_sort_column == self._sort_by_column_no:
				# user clicked a second time on same heading =>inverse sorting
				self._inverse_sorting = not self._inverse_sorting
			self.populate_tree()


	def rightclick_handler(self, event):
		"""
		display context menu as popup menu
		"""
		# with hints from http://effbot.org/zone/tkinter-popup-menu.htm
		# and http://stackoverflow.com/questions/12014210/python-tkinter-app-adding-a-right-click-context-menu
		# and https://docs.python.org/dev/library/tkinter.ttk.html#ttk-treeview
		try:
			# set selection on current row
			iid = self.tree.identify_row(event.y)
			self.tree.selection_set(iid)

			# display popup menu at clicked position
			self.context_menu.tk_popup(event.x_root, event.y_root, 0)
		finally:
			# make sure to release the grab (Tk 8.0a1 only)
			self.context_menu.grab_release()


	def _cb_open_grafikeditor(self):
		if DEBUGGING:
			my_print(u'popup menu "open in GE": filename="' + self._get_clicked_filename() + u'", fullpath="' + self._get_clicked_fullpath() + u'"')
		# FIXME: following code part is the same as in "doubleclick_handler(self, event)"... we should refactor both callbacks...

		fullpath = self._get_clicked_filename()

		# set this file in GE (Grafikeditor) if possible
		if fullpath.split('.')[-1].upper() == u'PSC':
			# write filename to the right DMS datapoint
			self._curr_DMS.pyDMS_WriteSTREx(self._curr_image_dp, fullpath)


	def _cb_open_windows_explorer(self):
		if DEBUGGING:
			my_print(u'popup menu "open Windows Explorer": filename="' + self._get_clicked_filename() + u'", fullpath="' + self._get_clicked_fullpath() + u'"')
		# help from http://stackoverflow.com/questions/281888/open-explorer-on-a-file
		subprocess.Popen(r'explorer /select,"' + self._get_clicked_fullpath() + '"')

	def _cb_open_notepad(self):
		"""
		trying to open selected file in Notepad++
		(we only care about default installation directories)
		"""
		if DEBUGGING:
			print('popup menu "open in Notepad++": filename="' + self._get_clicked_filename() + '", fullpath="' + self._get_clicked_fullpath() + '"')
		NPP_EXES = [r'C:\Program Files (x86)\Notepad++\notepad++.exe', r'C:\Program Files\Notepad++\notepad++.exe']
		curr_exe = None
		for exefile in NPP_EXES:
			if os.path.exists(exefile):
				curr_exe = exefile
		if curr_exe:
			cmd_str = '"' + curr_exe + '" "' + self._get_clicked_fullpath() + '"'
			if DEBUGGING:
				my_print(u'\tcommand string for subprocess.Popen: ' + cmd_str)
			subprocess.Popen(cmd_str)

	def _cb_fname_to_clipboard(self):
		if DEBUGGING:
			print('popup menu "copy filename to clipboard": filename="' + self._get_clicked_filename() + '", fullpath="' + self._get_clicked_fullpath() + '"')
		self._curr_clipboard.copy_c(self._get_clicked_filename())


	def _cb_entry_filepattern(self, *args):
		self.populate_tree()

		## hint from http://stackoverflow.com/questions/8036499/unicodewarning-special-characters-in-tkinter
		#mystr = self.file_regex_pattern.get()
		# if isinstance(mystr, unicode):
		# 	uni_mystr = mystr
		# else:
		# 	try:
		# 		uni_mystr = mystr.decode(encoding=ENCODING_LOCALE, errors='strict')
		# 	except UnicodeDecodeError:
		# 		# FIXME: how to handle wrong encodings?!?
		# 		pass
		# my_print(u'value of "self.file_regex_pattern" is "' + uni_mystr + u'"')


	def _cb_entry_stringpattern(self, *args):
		self.populate_tree()

		# # hint from http://stackoverflow.com/questions/8036499/unicodewarning-special-characters-in-tkinter
		# mystr = self.string_regex_pattern.get()
		# if isinstance(mystr, unicode):
		# 	uni_mystr = mystr
		# else:
		# 	try:
		# 		uni_mystr = mystr.decode(encoding=ENCODING_LOCALE, errors='strict')
		# 	except UnicodeDecodeError:
		# 		# FIXME: how to handle wrong encodings?!?
		# 		pass
		# my_print(u'value of "self.string_regex_pattern" is "' + uni_mystr + '"')


	def _cb_btn_underscore(self, *args):
		self.file_regex_pattern.set(FileSelectorGUI.RE_PATTERN_UNDERSCORE)
		if self.string_regex_pattern.get() != '':
			self.string_regex_pattern.set('')

	def _cb_btn_all_psc(self, *args):
		self.file_regex_pattern.set(FileSelectorGUI.RE_PATTERN_ALL_PSC)
		if self.string_regex_pattern.get() != '':
			self.string_regex_pattern.set('')

	def _cb_btn_vlo_collection(self, *args):
		self.file_regex_pattern.set(FileSelectorGUI.RE_PATTERN_VLO_COLLECTION)
		if self.string_regex_pattern.get() != '':
			self.string_regex_pattern.set('')



def main(argv=None):
	get_encoding()

	my_print(u'PSC_file_selector.py')
	my_print(u'*******************')

	curr_dms = dms.dmspipe.Dmspipe()

	prj = curr_dms.pyDMS_ReadSTREx('System:Project')
	computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
	my_print(u'"System:Project"=' + prj)
	my_print(u'"System:NT:Computername"=' + computer)

	#curr_psc = curr_dms.pyDMS_ReadSTREx('System:Node:' + computer + ':Image')
	#curr_ReInit = curr_dms.pyDMS_ReadSTREx('System:Node:' + computer + ':ImgReInit')

	#filename = os.path.join(curr_prj, 'scr' , curr_psc)
	#curr_visuparser = visu.psc.Parser.PscFile(filename)
	#curr_visuparser.parse_file()

	curr_ge_instance = None
	for running_ge in curr_dms.get_DMS_sons_list_by_key('System:Prog:GE'):
		ge_up_bit = ':'.join(['System:Prog:GE', running_ge[0], 'UP'])
		if ge_up_bit:
			my_print(u'GE instance with flag "' + ge_up_bit + u'" seems to be in use...')
			curr_ge_instance = running_ge[0]

	if curr_ge_instance:
		curr_image_dp = 'System:Node:' + curr_ge_instance + ':Image'
		curr_src_path = os.path.join(prj, 'scr')
		curr_clipboard = misc.clipboard.Clipboard()

		my_print(u'\n\tUsage: Select on second GUI which PSC file has to be displayed in GE (Grafikeditor)\n')
		root = FileSelectorGUI(curr_dms, curr_image_dp, curr_src_path, curr_clipboard)
		root.mainloop()
	else:
		my_print(u'\nERROR: Grafikeditor is not running!!!')




	return 0        # success


if __name__ == '__main__':
	status = main()
	# sys.exit(status)