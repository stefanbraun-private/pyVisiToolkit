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
import Tkinter, Tkconstants, ttk
from visu.psc import Parser
import os
import datetime
import collections
import misc.timezone as timezone
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import subprocess
import threading
import queue
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


class BMO_Instance_Metadata(object):
	"""
	metadata per BMO instance
	"""
	def __init__(self):
		self._max_coords = 0, 0, 0, 0
		self._bmo_class = ''

	def set_BMO_class(self, bmo_class):
		self._bmo_class = str(bmo_class)

	def get_BMO_class(self):
		return self._bmo_class

	def set_max_coords(self, *coords):
		self._max_coords = tuple(coords)

	def get_max_coords(self):
		return self._max_coords


class BMO_Elements_Handler(object):
	"""
	extracts data of PSC BMO elements
	"""
	def __init__(self):
		self.fname = None

		self._bmo_instances = {}

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


	def draw_elements(self, canvas_visu, bmo_check_func):
		self._bmo_instances = {}

		# collect information for draw this element
		for elem, instance, bmo_class in self._filtered_elements():
			coords = elem.get_property(u'selection-area').get_coordinates()
			try:
				# FIXME: write these comparisons in a cleaner way
				_x1, _y1, _x2, _y2 = self._bmo_instances[instance].get_max_coords()
				x1 = coords[0] if coords[0] < _x1 else _x1
				x2 = coords[2] if coords[2] > _x2 else _x2
				y1 = coords[1] if coords[1] < _y1 else _y1
				y2 = coords[3] if coords[3] > _y2 else _y2
				self._bmo_instances[instance].set_max_coords(x1, y1, x2, y2)
			except KeyError:
				# first appearance of this BMO instance
				self._bmo_instances[instance] = BMO_Instance_Metadata()
				self._bmo_instances[instance].set_max_coords(*coords)

			self._bmo_instances[instance].set_BMO_class(bmo_class)

		# draw this list on main canvas
		for instance, metadata in self._bmo_instances.items():
			logger.debug('draw_elements(): BMO instance "' + instance + '" [' + self._bmo_instances[instance].get_BMO_class() + '] has maximum coordinates ' + repr(metadata.get_max_coords()))
			if bmo_check_func(instance):
				# BMO instance does exist
				fillcolor = "green"
				tags = (MyGUI.BMO_EXISTS_TAG, instance)
			else:
				fillcolor = "red"
				tags = (MyGUI.BMO_MISSING_TAG, instance)
			# hint about using tags: http://effbot.org/tkinterbook/canvas.htm#item-specifiers
			canvas_visu.create_rectangle(*metadata.get_max_coords(), fill=fillcolor, outline="blue", tags=tags)

			# add text into rectangle
			# help from https://stackoverflow.com/questions/39087139/tkinter-label-text-in-canvas-rectangle-python
			# calculate center:
			x1, y1, x2, y2 = metadata.get_max_coords()
			x = (x1 + x2) / 2
			y = (y1 + y2) / 2
			canvas_visu.create_text((x, y), text=self._bmo_instances[instance].get_BMO_class())



class MyGUI(Tkinter.Frame):
	# example code from http://zetcode.com/gui/tkinter/layout/

	ROOT_TITLE = u'BMO Link Tool v0.0.1'

	BMO_EXISTS_TAG = 'BMO_EXISTS'
	BMO_MISSING_TAG = 'BMO_MISSING'

	def __init__(self, parent, psc_handler, dms, prj, ge_host):
		Tkinter.Frame.__init__(self, parent)
		self.parent = parent
		# settings of rootwindow
		self.parent.title(MyGUI.ROOT_TITLE + u' - no PSC file loaded')

		self.psc_handler = psc_handler
		self._dms = dms
		self._prj = prj
		self._ge_host = ge_host

		# DMS-events when PSC files gets opened in GE
		self._image_queue = queue.Queue()

		self._canvas_frame = Tkinter.Frame(master=self)
		self._canvas_visu = None
		self._buildCanvasVisu(parent=self._canvas_frame)
		self._canvas_frame.pack(fill=Tkconstants.BOTH, expand=True)
		self.pack(fill=Tkconstants.BOTH, expand=True)


		self._register_dms_callback()


	def _buildCanvasVisu(self, parent):
		if self._canvas_visu:
			# widget already exists... =>delete it for redrawing
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self._canvas_visu.grid_forget()
			self._canvas_visu.destroy()

		vsb = ttk.Scrollbar(master=parent, orient="vertical")
		hsb = ttk.Scrollbar(master=parent, orient="horizontal")
		self._canvas_visu = Tkinter.Canvas(parent, width=1280, height=1024, background="white",
		                                   yscrollcommand=vsb.set, xscrollcommand=hsb.set)
		# enabling scrolling: http://effbot.org/tkinterbook/canvas.htm#coordinate-systems
		# FIXME: changing size of rootwindow doesn't affect scrollbars
		# FIXME: should we scale canvas or use scrollbars when user resizes rootwindow? some PSC windows are huge...!
		# FIXME: we should adjust "width" and "heigth" dynamically from max(max coordinates of PSC graphelements, size PSC window)
		# FIXME: we should implement a cleaner design. canvas widget into own class.
		# FIXME: implement drag and drop for setting links (while moving: drawing line. on drop: show popup with PAR_INs/PLCs)
		#       https://stackoverflow.com/questions/44887576/how-make-drag-and-drop-interface
		#       https://stackoverflow.com/questions/15466469/tkinter-drag-and-drop
		# FIXME: implement right-click "delete link" / "show parameters" (edit fields?)
		# FIXME: implement mouse-hover: label showing BMO instance & class under mouse
		# FIXME: checkbox "show links" ->red=digital, green=analog (only from/to one BMO instance, or between all?)
		self._canvas_visu.config(scrollregion=self._canvas_visu.bbox(Tkinter.ALL))
		self._canvas_visu.grid(row=0, column=0, padx=5)

		# Arrange the scrollbars in the toplevel
		vsb.grid(row=0, column=1, sticky='ns')
		hsb.grid(row=1, column=0, sticky='ew')


	def _register_dms_callback(self):
		"""
		monitoring PSC document opening activity in currently running GE instance
		"""

		dms_key_str = ':'.join(['System:Node', self._ge_host, 'Image'])

		logger.debug('MyGUI._register_dms_callback(): trying to subscribe DMS key "' + dms_key_str + '"...')
		sub_obj = self._dms.get_dp_subscription(path=dms_key_str,
		                                        event=dms.ON_SET)
		logger.debug('MyGUI._register_dms_callback(): adding callback for DMS key "' + dms_key_str + '"...')
		msg = sub_obj.sub_response.message
		if not msg:
			sub_obj += self._dms_callback_ge_image_changed

			# first run: use information we got from subscription
			self._ge_image_changed(new_image=sub_obj.sub_response.value)
			logger.info('MyGUI._register_dms_callback(): monitoring of DMS key "' + dms_key_str + '" is ready.')
		else:
			logger.error('MyGUI._register_dms_callback(): monitoring of DMS key "' + dms_key_str + '" failed! [message: ' + msg + '])')
			raise Exception('subscription failed!')


	def _dms_callback_ge_image_changed(self, event):
		""" another PSC file was opened in GE (method is executed in thread of DMS-eventfiring) """
		# against freezing of GUI: thread synchronisation DMS-event -> GUI mainloop
		# (as explained on https://scorython.wordpress.com/2016/06/27/multithreading-with-tkinter/ )
		self._image_queue.put(event)


	def _ge_image_changed(self, new_image=''):
		""" another PSC file was opened in GE """
		filename = new_image
		if not new_image:
			# assumption: called by Tkinter schedule
			try:
				event = self._image_queue.get(block=False)
			except queue.Empty:
				pass
			else:
				# (this is an optional else clause when no exception occured)
				logger.debug('MyGUI._ge_image_changed(): got DMS-event [DMS-key="' + event.path + '" / value=' + event.value + ']')
				filename = event.value

		if filename:
			# only redraw canvas when shown PSC is not a reinit of BMO instance
			dms_key_str = ':'.join(['System:Node', self._ge_host, 'ImgReInit'])
			if not self._dms.dp_get(path=dms_key_str)[0].value:
				logger.info('MyGUI._cb_ge_image_changed(): GE opened PSC file "' + filename + '"')
				self._load_psc_image(filename)

		# scheduling next execution
		self.after(100, self._ge_image_changed)


	def _load_psc_image(self, filename):
		psc_fullpath = os.path.join(self._prj, 'scr', filename)

		# settings of rootwindow
		self.parent.title(MyGUI.ROOT_TITLE + u' - ' + psc_fullpath)

		# preset parser and load PSC image
		self.psc_handler.set_psc_file(psc_fullpath)
		self._update_canvas()


	def _update_canvas(self):
		self._buildCanvasVisu(parent=self._canvas_frame)

		def bmo_exists(instance_str):
			# check if BMO instance does exist
			dms_key_str = ':'.join([instance_str, 'OBJECT'])
			resp = self._dms.dp_get(path=dms_key_str)
			return resp[0].code == 'ok'

		self.psc_handler.draw_elements(canvas_visu=self._canvas_visu,
		                               bmo_check_func=bmo_exists)



def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.BMO_Link_Tool',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		curr_proj = dms_ws.dp_get(path='System:Project')[0].value
		logger.info('current project is "' + curr_proj + '")')

		curr_ge_host = None
		for resp in dms_ws.dp_get(path="", query=dms.Query(regExPath=r'System:Prog:GE:.*:UP', maxDepth=0)):
			if resp.value:
				curr_ge_host = resp.path.replace('System:Prog:GE:', '')[:-3]
				logger.debug('found a running GE instance on host "' + curr_ge_host + '"...')
				break

		if curr_ge_host:
			# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
			Parser.PscParser.load_config(Parser.PARSERCONFIGFILE)

			curr_psc_handler = BMO_Elements_Handler()

			# Build a gui
			rootWindow = Tkinter.Tk()
			app = MyGUI(parent=rootWindow, psc_handler=curr_psc_handler, dms=dms_ws, prj=curr_proj, ge_host=curr_ge_host)

			# Keeps GUI mainloop running until GUI is closed
			rootWindow.mainloop()
		else:
			logger.error('no local instance of GE found! GE is mandatory for using this tool...')

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