#!/usr/bin/env python
# encoding: utf-8
"""
tools.BMO_Link_Tool.py      v0.0.1
Manipulate links between BMO instances by drag and drop.

[inspired by workflow in "Priva Top Control"(tm)]


Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



import dms.dmswebsocket as dms
import logging
import argparse
import Tkinter, Tkconstants, tkFileDialog
from visu.psc import Parser
import os
import ttk
import datetime
import collections
import misc.timezone as timezone
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import subprocess
import threading
import Queue
import shlex
import re
import time


# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('tools.BMO_Link_Tool')
logger.setLevel(logging.DEBUG)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)



class BMO_Elements_Handler(object):
	"""
	extracts data of PSC BMO elements
	"""
	def __init__(self):
		self.fname = None

		# maximum size for drawing BMO instances
		self._bmo_sizes = {}
		self._bmo_classes = {}

	def set_psc_file(self, fname):
		self.fname = fname
		self.curr_file = Parser.PscFile(self.fname)
		self.curr_file.parse_file()

	def is_ready(self):
		return self.fname != None

	def _filtered_elements(self):
		"""
		returns PSC elements which contains BMO instances
		"""

		for elem in self.curr_file.get_psc_elem_list():
			# ignore elements without BMO instance
			bmo_instance = elem.get_property(u'bmo-instance').get_value()
			if bmo_instance != "" and not bmo_instance.startswith("BMO:"):
				# do we have to check this PSC element?
				bmo_class = elem.get_property(u'bmo-class').get_value().replace("BMO:", '')
				yield elem, bmo_instance, bmo_class


	def draw_elements(self, canvas_visu):
		self._bmo_sizes = {}
		self._bmo_classes = {}

		# collect information for draw this element
		for elem, instance, bmo_class in self._filtered_elements():
			coords = elem.get_property(u'selection-area').get_coordinates()
			try:
				# FIXME: write these comparisons in a cleaner way
				_x1, _y1, _x2, _y2 = self._bmo_sizes[instance]
				x1 = coords[0] if coords[0] < _x1 else _x1
				x2 = coords[2] if coords[2] > _x2 else _x2
				y1 = coords[1] if coords[1] < _y1 else _y1
				y2 = coords[3] if coords[3] > _y2 else _y2
				self._bmo_sizes[instance] = x1, y1, x2, y2
			except KeyError:
				# first appearance of this BMO instance
				self._bmo_sizes[instance] = coords

			if not instance in self._bmo_classes:
				self._bmo_classes[instance] = bmo_class

		# draw this list on main canvas
		for key, coords in self._bmo_sizes.items():
			logger.debug('draw_elements(): BMO instance "' + key + '" [' + self._bmo_classes[instance] + '] has maximum coordinates ' + repr(coords))
			canvas_visu.create_rectangle(*coords, fill="white", outline="blue")

			# add text into rectangle
			# help from https://stackoverflow.com/questions/39087139/tkinter-label-text-in-canvas-rectangle-python
			# calculate center:
			x1, y1, x2, y2 = coords
			x = (x1 + x2) / 2
			y = (y1 + y2) / 2
			canvas_visu.create_text((x, y), text=self._bmo_classes[instance])



class MyGUI(Tkinter.Frame):
	# example code from http://zetcode.com/gui/tkinter/layout/

	ROOT_TITLE = u'BMO Link Tool v0.0.1'
	def __init__(self, parent, psc_handler, dms, prj):
		Tkinter.Frame.__init__(self, parent)
		self.parent = parent
		# settings of rootwindow
		self.parent.title(MyGUI.ROOT_TITLE + u' - no PSC file loaded')

		self.psc_handler = psc_handler
		self._dms = dms
		self._prj = prj

		self._buildFormular()
		self._draw_frame = Tkinter.Frame(master=self)
		self._canvas_visu = None
		self._buildCanvasVisu(parent=self._draw_frame)
		self._draw_frame.pack(fill=Tkconstants.BOTH, expand=True)
		self.pack(fill=Tkconstants.BOTH, expand=True)

	def _buildFormular(self):

		self._frame_formular = Tkinter.Frame(master=self)

		btn = Tkinter.Button(self._frame_formular, text='Select PSC file...', command=self._cb_button_selectfile)
		btn.pack(fill=Tkconstants.BOTH, padx=5, pady=5)

		self._frame_formular.pack(fill=Tkconstants.BOTH, padx=5, pady=5)


	def _buildCanvasVisu(self, parent):
		if self._canvas_visu:
			# widget already exists... =>delete it for redrawing
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self._canvas_visu.grid_forget()
			self._canvas_visu.destroy()
		self._canvas_visu = Tkinter.Canvas(parent, width=1280, height=1024, background="white")
		self._canvas_visu.grid(row=0, column=1, padx=5)


	def _cb_button_selectfile(self):
		# file browser
		# (example from http://tkinter.unpythonic.net/wiki/tkFileDialog )

		# define options for opening or saving a file
		file_opt = options = {}
		options['defaultextension'] = '.psc'
		options['filetypes'] = [('PSC files', '.psc'), ('all files', '.*')]
		options['initialdir'] = os.path.join(self._prj, 'scr')
		options['initialfile'] = ''
		options['parent'] = self._frame_formular
		options['title'] = 'Select PSC file for preview'

		filename = tkFileDialog.askopenfilename(**file_opt)
		if filename:
			# settings of rootwindow
			self.parent.title(MyGUI.ROOT_TITLE + u' - ' + filename)

			# preset parser and load PSC image
			self.psc_handler.set_psc_file(filename)
			self._update_canvas()


	def _update_canvas(self):
		self._buildCanvasVisu(parent=self._draw_frame)
		self.psc_handler.draw_elements(canvas_visu=self._canvas_visu)



def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.BMO_Link_Tool',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		curr_proj = dms_ws.dp_get(path='System:Project')[0]['value']
		logger.info('current project is "' + curr_proj + '")')

		# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
		Parser.PscParser.load_config(Parser.PARSERCONFIGFILE)

		curr_psc_handler = BMO_Elements_Handler()

		# Build a gui
		rootWindow = Tkinter.Tk()
		app = MyGUI(parent=rootWindow, psc_handler=curr_psc_handler, dms=dms_ws, prj=curr_proj)

		# Keeps GUI mainloop running until GUI is closed
		rootWindow.mainloop()

	logger.info('Quitting "BMO_Link_Tool"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Manipulate links between BMO instances by drag and drop.')

	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port)
	#sys.exit(status)