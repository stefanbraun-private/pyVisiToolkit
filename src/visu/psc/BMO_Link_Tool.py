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
import math
import datetime
import collections
import misc.timezone as timezone
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

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


class Filewatcher(threading.Thread):

	# used integer values in Queue for signalling to GUI
	HAS_CHANGED = 1

	def __init__(self):
		threading.Thread.__init__(self)
		self.has_changed_queue = queue.Queue()     # signalling to GUI
		self._keep_running = False
		self._fullpath = ''
		self._pause = 1          #
		self._modification_time = 0
		self.daemon = True

	def run(self):
		while self._keep_running:
			if self._fullpath:
				modtime = os.stat(self._fullpath).st_mtime
				if not self._modification_time:
					# first run
					self._modification_time = modtime
				elif modtime != self._modification_time:
					self.has_changed_queue.put(Filewatcher.HAS_CHANGED)
					self._modification_time = modtime
			time.sleep(self._pause)

	def set_fullpath(self, fullpath):
		logger.debug('Filewatcher.set_fullpath(): new file for watching: ' + fullpath)
		self._modification_time = 0
		self._fullpath = fullpath

	def start_watching(self, pause=1):
		self._keep_running = True
		self._pause = pause
		self.start()

	def stop_watching(self):
		self._keep_running = False


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

	def get_center_coords(self):
		# calculate center
		x1, y1, x2, y2 = self.get_max_coords()
		x = (x1 + x2) / 2
		y = (y1 + y2) / 2
		return x, y

	def get_border_intersection(self, x, y):
		""" calculate point, where line to (x,y) crosses rectangle-border of max. coordinates
			(used when drawing arrows between centers of BMO instances,
			for prevention of invisible arrow heads)
		"""
		# mathematic help from Wikipedia...
		# https://de.wikipedia.org/wiki/Koordinatenform#Aus_der_Zweipunkteform
		# https://de.wikipedia.org/wiki/Schnittpunkt#Schnittpunkt_zweier_Geraden

		xs, ys = self.get_center_coords()
		x1, y1, x2, y2 = self.get_max_coords()

		# no need for calculation if other point is directly above, under, left or right
		if x == xs:
			ys = y1 if y < y1 else y2
			return xs, ys
		elif y == ys:
			xs = x1 if x < x1 else x2
			return xs, ys

		# four lines through our rectangle-endpoints will have an intersection...
		# =>we need lines where intersection is BETWEEN endpoints
		line_to_target = self._get_line_koordinatenform(xs, ys, x, y)

		# four sides of our rectangle
		rect_lines = [(x1, y1, x2, y1),
		              (x2, y1, x2, y2),
		              (x2, y2, x1, y2),
		              (x1, y2, x1, y1)]

		rect_koordform_lines = []
		for endpoints in rect_lines:
			rect_koordform_lines.append(self._get_line_koordinatenform(*endpoints))

		intersection_list = []
		for idx, side_line in enumerate(rect_koordform_lines):
			a1, b1, c1 = side_line
			a2, b2, c2 = line_to_target
			xs, ys = self._get_schnittpunkt(a1, b1, c1, a2, b2, c2)

			# check if intersection is between endpoints
			# then calculate distance for choosing shortest path
			endp_x1, endp_y1, endp_x2, endp_y2 = rect_lines[idx]
			min_endp_x = min(endp_x1, endp_x2)
			max_endp_x = max(endp_x1, endp_x2)
			min_endp_y = min(endp_y1, endp_y2)
			max_endp_y = max(endp_y1, endp_y2)
			if min_endp_x <= xs <= max_endp_x and min_endp_y <= ys <= max_endp_y:
				distance = self._get_distance(x, y, xs, ys)
				intersection_list.append((distance, xs, ys))

		# choosing best match
		# (distance is first tuple item =>sorting is easy)
		distance, xs, ys = sorted(intersection_list)[0]
		return xs, ys

	def _get_line_koordinatenform(self, x1, y1, x2, y2):
		# https://de.wikipedia.org/wiki/Koordinatenform#Aus_der_Zweipunkteform
		a = y1 - y2
		b = x2 - x1
		c = x2*y1 - x1*y2
		return a, b, c

	def _get_schnittpunkt(self, a1, b1, c1, a2, b2, c2):
		# https://de.wikipedia.org/wiki/Schnittpunkt#Schnittpunkt_zweier_Geraden
		xs = 1.0*(c1*b2 - c2*b1)/(a1*b2 - a2*b1)
		ys = 1.0*(a1*c2 - a2*c1)/(a1*b2 - a2*b1)
		return int(xs), int(ys)

	def _get_distance(self, x1, y1, x2, y2):
		# Pythagoras
		a = x2 - x1
		b = y2 - y1
		return math.sqrt(a**2 + b**2)


class BMO_Elements_Handler(object):
	"""
	extracts data of PSC BMO elements
	"""

	# margin around elements most right and most down
	MARGIN_SIZE = 10

	def __init__(self):
		self.fname = None

		self._bmo_instances = {}

		self._existing_bmos_list = []

		# maximal size of canvas for drawing all BMOs
		self._used_area = 100, 100

	def set_psc_file(self, fname):
		if fname:
			# new PSC file
			self.fname = fname
		self.curr_file = Parser.PscFile(self.fname)
		self.curr_file.parse_file()
		self._used_area = 100, 100

	def is_ready(self):
		return self.fname != None

	def _filtered_elements(self):
		"""
		returns PSC elements which contains BMO instances
		"""

		for elem in self.curr_file.get_psc_elem_list():
			# ignore elements without BMO instance
			bmo_instance = elem.get_property(u'bmo-instance').get_value()
			if bmo_instance != "":
				# do we have to check this PSC element?
				bmo_class = elem.get_property(u'bmo-class').get_value().replace("BMO:", '')
				yield elem, bmo_instance, bmo_class


	def draw_elements(self, canvas_visu, bmo_check_func):
		self._bmo_instances = {}
		self._existing_bmos_list = []

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

				# update size of canvas
				max_x = max(self._used_area[0], x2)
				max_y = max(self._used_area[1], y2)
				self._used_area = max_x, max_y
			except KeyError:
				# first appearance of this BMO instance
				self._bmo_instances[instance] = BMO_Instance_Metadata()
				self._bmo_instances[instance].set_max_coords(*coords)

			self._bmo_instances[instance].set_BMO_class(bmo_class)

		# draw rectangles on main canvas
		for instance, metadata in self._bmo_instances.items():
			logger.debug('draw_elements(): BMO instance "' + instance + '" [' + self._bmo_instances[instance].get_BMO_class() + '] has maximum coordinates ' + repr(metadata.get_max_coords()))
			if bmo_check_func(instance):
				# BMO instance does exist
				if instance.startswith("BMO:"):
					# BMO is not reinitialized!
					fillcolor = "gray"
					tags = (MyGUI.BMO_TEMPLATE_TAG, instance)
				else:
					fillcolor = "green"
					tags = (MyGUI.BMO_EXISTS_TAG, instance)
					self._existing_bmos_list.append(instance)
			else:
				fillcolor = "red"
				tags = (MyGUI.BMO_MISSING_TAG, instance)
			# hint about using tags: http://effbot.org/tkinterbook/canvas.htm#item-specifiers
			canvas_visu.create_rectangle(*metadata.get_max_coords(), fill=fillcolor, outline="blue", tags=tags)

			# add text over rectangle (and reusing same tags for event binding)
			# help from https://stackoverflow.com/questions/39087139/tkinter-label-text-in-canvas-rectangle-python
			x, y = metadata.get_center_coords()
			canvas_visu.create_text((x, y), text=self._bmo_instances[instance].get_BMO_class(), tags=tags)

			# update minimal size of canvas
			canvas_visu.configure(width=self._used_area[0] + BMO_Elements_Handler.MARGIN_SIZE,
			                      height=self._used_area[1] + BMO_Elements_Handler.MARGIN_SIZE)


	def draw_connections(self, dms_ws, canvas_visu, bmo_inst_str):
		""" draw connections from/to other BMO instances """

		# some ideas:
		# -drawing lines behind other items from center to center
		# -digital = red, analog = green
		# -arrows for showing signal direction (PAR_OUT -> PAR_IN; convention: "pull", not "push")

		class Linkpoint(object):
			def __init__(self, name, type):
				self.name = name
				self.type = type

		if bmo_inst_str:
			# FIXME: perhaps we can combine both directions into a simpler code fragment?
			# links to this instance
			incoming_list = []
			for resp in dms_ws.dp_get(path="",
			                          query=dms.Query(regExPath=r'^' + bmo_inst_str + r':\w+:PAR_IN$',
			                                          isType="string",
			                                          maxDepth=0)):
				if resp.value:
					# FIXME: we need to check DMS datatype of link source and link drain!!!
					# FIXME: we need to check if it's a valid PAR_IN and PAR_OUT!!!
					for inst in self._bmo_instances:
						if inst in resp.value:
							# BMO link is on current PSC file

							# getting datatype of PLC datapoint
							# =>assuming other side is a valid PAR_OUT of inst
							# =>assuming other side has same datatype as our PAR_IN
							plc_dp = resp.path.split(":PAR_IN")[0]
							plc_dp_resp = dms_ws.dp_get(path=plc_dp)[0]
							if not plc_dp_resp.message:
								incoming_list.append(Linkpoint(name=inst, type=plc_dp_resp.type))
								break
			#logger.debug('BMO_Elements_Handler.draw_connections(): incoming_list=' + repr(incoming_list))

			# drawing links to this instance
			for src in incoming_list:
				# arrow source: center of BMO instance
				#x1, y1 = self._bmo_instances[src.name].get_center_coords()
				# arrow destination: center of BMO instance
				# x2, y2 = self._bmo_instances[bmo_inst_str].get_center_coords

				# better results: always use intersection on rectangle of BMO instance
				# (not drawing lines inside of rectangles)
				src_x, src_y = self._bmo_instances[src.name].get_center_coords()
				dst_x, dst_y = self._bmo_instances[bmo_inst_str].get_center_coords()

				x1, y1 = self._bmo_instances[src.name].get_border_intersection(dst_x, dst_y)
				x2, y2 = self._bmo_instances[bmo_inst_str].get_border_intersection(src_x, src_y)

				curr_color = "dark red" if src.type == "bool" else "dark green"
				canvas_visu.create_line(x1, y1, x2, y2, fill=curr_color, width=2.0, arrow="last",
				                        tags=MyGUI.CANVAS_BG_LINK_LINE_TAG)

			# links from this instance
			outgoing_list = []
			for resp in dms_ws.dp_get(path="",
			                          query=dms.Query(regExValue=r'^' + bmo_inst_str + r':\w+',
			                                          isType="string",
			                                          maxDepth=0)):
				if not resp.message and resp.path.endswith(':PAR_IN'):
					# FIXME: we need to check DMS datatype of link source and link drain!!!
					# FIXME: we need to check if it's a valid PAR_IN and PAR_OUT!!!
					for inst in self._bmo_instances:
						if inst in resp.path:
							# BMO link is on current PSC file

							# getting datatype of PLC datapoint
							# =>assuming other side is a valid PAR_IN of inst
							# =>assuming other side has same datatype as our PAR_OUT
							plc_dp = resp.path.split(":PAR_IN")[0]
							plc_dp_resp = dms_ws.dp_get(path=plc_dp)[0]
							if not plc_dp_resp.message:
								outgoing_list.append(Linkpoint(name=inst, type=plc_dp_resp.type))
								break
			#logger.debug('BMO_Elements_Handler.draw_connections(): outgoing_list=' + repr(outgoing_list))

			# drawing links from this instance
			for dst in outgoing_list:
				# arrow source: center of BMO instance
				#x1, y1 = self._bmo_instances[bmo_inst_str].get_center_coords()
				# arrow destination: center of BMO instance
				#x2, y2 = self._bmo_instances[dst.name].get_center_coords()

				# better results: always use intersection on rectangle of BMO instance
				# (not drawing lines inside of rectangles)
				src_x, src_y = self._bmo_instances[bmo_inst_str].get_center_coords()
				dst_x, dst_y = self._bmo_instances[dst.name].get_center_coords()

				x1, y1 = self._bmo_instances[bmo_inst_str].get_border_intersection(dst_x, dst_y)
				x2, y2 = self._bmo_instances[dst.name].get_border_intersection(src_x, src_y)

				curr_color = "dark red" if dst.type == "bool" else "dark green"
				canvas_visu.create_line(x1, y1, x2, y2, fill=curr_color, width=2.0, arrow="last",
				                        tags=MyGUI.CANVAS_BG_LINK_LINE_TAG)

			## put all lines into background
			#canvas_visu.tag_lower(MyGUI.CANVAS_BG_LINK_LINE_TAG)
			# =>better results: put all lines into foreground
			canvas_visu.tag_raise(MyGUI.CANVAS_BG_LINK_LINE_TAG)


class MyGUI(Tkinter.Frame):
	# example code from http://zetcode.com/gui/tkinter/layout/

	ROOT_TITLE = u'BMO Link Tool v0.0.1'

	BMO_EXISTS_TAG = 'BMO_EXISTS'
	BMO_MISSING_TAG = 'BMO_MISSING'
	BMO_TEMPLATE_TAG = 'BMO_TEMPLATE'

	BMO_INFO_DICT = {BMO_EXISTS_TAG: 'okay',
	                 BMO_MISSING_TAG: 'not in DMS',
	                 BMO_TEMPLATE_TAG: 'not reinitialized'}

	# arrow during drag and drop
	CANVAS_DND_LINK_LINE_TAG = 'CANVAS_DND_LINK_LINE'

	# background arrows during hovering
	CANVAS_BG_LINK_LINE_TAG = 'CANVAS_BG_LINK_LINE'

	CANVAS_WIDTH = 1920
	CANVAS_HEIGHT = 1080
	# FIXME: test with a smaller screen resolution
	#CANVAS_WIDTH = 800
	#CANVAS_HEIGHT = 600

	def __init__(self, parent, psc_handler, filewatcher, dms_ws, prj, ge_host):
		Tkinter.Frame.__init__(self, parent)
		self.parent = parent
		# settings of rootwindow
		self.parent.title(MyGUI.ROOT_TITLE + u' - no PSC file loaded')

		self.psc_handler = psc_handler
		self._filewatcher = filewatcher
		self._dms_ws = dms_ws
		self._prj = prj
		self._ge_host = ge_host

		# DMS-events when PSC files gets opened in GE
		self._image_queue = queue.Queue()

		self._canvas_frame = Tkinter.Frame(master=self)
		self._canvas_visu = None
		self._buildCanvasVisu(parent=self._canvas_frame)

		# Make the canvas expandable
		self._canvas_frame.rowconfigure(0, weight=1)
		self._canvas_frame.columnconfigure(0, weight=1)

		self._canvas_frame.grid(row=0, column=0, sticky='nsew')
		self.grid(row=1, column=0, sticky='nsew')

		# activate watching of GE
		self._register_dms_callback()

		# activate watching of PSC-file
		self._filewatcher.start_watching()
		self._ge_psc_changed()


	def _buildCanvasVisu(self, parent):
		if self._canvas_visu:
			# widget already exists... =>delete it for redrawing
			# updating information ->first delete the widget, then redraw it
			# http://stackoverflow.com/questions/3962247/python-removing-a-tkinter-frame
			self._canvas_visu.grid_forget()
			self._canvas_visu.destroy()

		self._canvas_visu = Tkinter.Canvas(parent, width=MyGUI.CANVAS_WIDTH, height=MyGUI.CANVAS_HEIGHT, background="white")

		# FIXME: enabling scrolling: http://effbot.org/tkinterbook/canvas.htm#coordinate-systems
		# FIXME: changing size of rootwindow doesn't affect scrollbars
		# FIXME: should we scale canvas or use scrollbars when user resizes rootwindow? some PSC windows are huge...!
		# done: we should adjust "width" and "heigth" dynamically from max(max coordinates of PSC graphelements, size PSC window)
		# FIXME: we should implement a cleaner design. canvas widget into own class.
		# FIXME: implement drag and drop for setting links (while moving: drawing line. on drop: show popup with PAR_INs/PLCs)
		#       https://stackoverflow.com/questions/44887576/how-make-drag-and-drop-interface
		#       https://stackoverflow.com/questions/15466469/tkinter-drag-and-drop
		# FIXME: implement right-click "delete link"? / "show parameters" (edit fields?)
		# done: implement mouse-hover: label showing BMO instance & class under mouse
		# done: checkbox "show links" ->red=digital, green=analog (only from/to one BMO instance, or between all?)
		self._canvas_visu.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

		# show information when mouse is over a BMO instance
		# =>help from https://stackoverflow.com/questions/33121545/how-to-display-canvas-coordinates-when-hovering-cursor-over-canvas
		self._canvas_visu.tag_bind(MyGUI.BMO_EXISTS_TAG, '<Motion>', self._on_mouseover)
		self._canvas_visu.tag_bind(MyGUI.BMO_EXISTS_TAG, '<Enter>', self._on_mouseover)  # handle <Alt>+<Tab> switches between windows
		self._curr_bmo_instance = ''

		# delete background link lines
		# =>help from https://stackoverflow.com/questions/35111894/tkinter-canvas-leave-event-isnt-trigged
		self._canvas_visu.tag_bind(MyGUI.BMO_EXISTS_TAG, '<Leave>', self._on_mouse_leave)


		self._bmo_info_label = Tkinter.Label(master=parent, text='', anchor='w')
		self._bmo_info_label.grid(row=1, column=0, padx=10, pady=10, sticky='ew')

		# create BMO link: drag and drop a line for visualisation
		# help from https://stackoverflow.com/questions/6740855/board-drawing-code-to-move-an-oval/6789351#6789351
		# this data is used to keep track of line being dragged
		self._drag_data = {"x": 0, "y": 0, "source_item": None}
		# add bindings for clicking, dragging and releasing
		self._canvas_visu.bind("<ButtonPress-1>", self._on_mouse_press)
		self._canvas_visu.bind("<ButtonRelease-1>", self._on_mouse_release)
		self._canvas_visu.bind("<B1-Motion>", self._on_mouse_b1motion)


	def _on_mouseover(self, event):
		""" update BMO information """
		# help from http://effbot.org/tkinterbook/canvas.htm#item-specifiers
		# and https://stackoverflow.com/questions/13114953/how-do-i-get-id-of-a-widget-that-invoke-an-event-tkinter

		canvas = event.widget
		x = canvas.canvasx(event.x)
		y = canvas.canvasy(event.y)
		x1 = x - 1
		x2 = x + 1
		y1 = y - 1
		y2 = y + 1
		instance = ''
		try:
			rect = canvas.find_overlapping(x1, y1, x2, y2)[0]
			state = ''
			for tag in self._canvas_visu.gettags(rect):
				if tag in MyGUI.BMO_INFO_DICT:
					state = MyGUI.BMO_INFO_DICT[tag]
				elif ':' in tag:
					# assuming BMO instance
					instance = tag
			curr_text = instance + '\t[' + state + ']'
		except IndexError:
			curr_text = ''
		self._bmo_info_label.configure(text=curr_text)

		# draw background link lines from/to other BMO instances
		if instance is not self._curr_bmo_instance:
			# mouse is over another rectangle
			# =>need to redraw lines
			# =>delete old lines
			event.widget.delete(MyGUI.CANVAS_BG_LINK_LINE_TAG)
			self._curr_bmo_instance = instance
			self.psc_handler.draw_connections(dms_ws=self._dms_ws,
			                                  canvas_visu=canvas,
			                                  bmo_inst_str=instance)


	def _on_mouse_press(self, event):
		'''Beginning dragging of line from source BMO instance'''
		# record the item and its location
		canvas = event.widget
		x = canvas.canvasx(event.x)
		y = canvas.canvasy(event.y)
		x1 = x - 1
		x2 = x + 1
		y1 = y - 1
		y2 = y + 1
		try:
			item = canvas.find_overlapping(x1, y1, x2, y2)[0]
			tags = self._canvas_visu.gettags(item)
			if MyGUI.BMO_EXISTS_TAG in tags:
				self._drag_data["source_item"] = item
				self._drag_data["x"] = event.x
				self._drag_data["y"] = event.y
				logger.debug('MyGUI._on_mouse_press(): found valid link source.')

				# draw link line with length 1
				event.widget.create_line(event.x, event.y, event.x, event.y, width=2.0, arrow="last",
				                         tags=MyGUI.CANVAS_DND_LINK_LINE_TAG)
			else:
				logger.debug('MyGUI._on_mouse_press(): ignoring invalid link source...')
		except IndexError:
			# no BMO instance at press point
			logger.debug('MyGUI._on_mouse_press(): no BMO instance at press point...')
			self._drag_data["source_item"] = None
			self._drag_data["x"] = 0
			self._drag_data["y"] = 0


	def _on_mouse_release(self, event):
		'''End drag of line to destination BMO instance'''

		# delete link line
		event.widget.delete(MyGUI.CANVAS_DND_LINK_LINE_TAG)

		# analyze release point
		dst_instance = ''
		canvas = event.widget
		x = canvas.canvasx(event.x)
		y = canvas.canvasy(event.y)
		x1 = x - 1
		x2 = x + 1
		y1 = y - 1
		y2 = y + 1
		try:
			item = canvas.find_overlapping(x1, y1, x2, y2)[0]
			tags = self._canvas_visu.gettags(item)
			if MyGUI.BMO_EXISTS_TAG in tags:
				for tag in tags:
					if ':' in tag:
						# assuming BMO instance
						dst_instance = tag
						logger.debug('MyGUI._on_mouse_release(): ' + dst_instance + ' is a valid link destination.')
						break
			elif MyGUI.BMO_MISSING_TAG in tags:
				logger.debug('MyGUI._on_mouse_release(): missing BMO instance at release point...')
			elif MyGUI.BMO_TEMPLATE_TAG in tags:
				logger.debug('MyGUI._on_mouse_release(): uninitialized BMO instance at release point...')
		except IndexError:
			# no BMO instance at release point
			logger.debug('MyGUI._on_mouse_release(): no BMO instance at release point...')

		if dst_instance and self._drag_data["source_item"]:
			# open popup window for adjusting link details
			src_instance = ''
			for tag in self._canvas_visu.gettags(self._drag_data["source_item"]):
				if ':' in tag:
					# assuming BMO instance
					src_instance = tag
					break
			logger.info('MyGUI._on_mouse_release(): create BMO link: ' + src_instance + ' -> ' + dst_instance)

		logger.debug('MyGUI._on_mouse_release(): resetting drag & drop information.')
		self._drag_data["source_item"] = None
		self._drag_data["x"] = 0
		self._drag_data["y"] = 0


	def _on_mouse_b1motion(self, event):
		'''Handle drawing line from source BMO instance'''

		if self._drag_data["source_item"]:
			# change coordinates of link line
			# help from http://effbot.org/tkinterbook/canvas.htm#patterns
			# and https://stackoverflow.com/questions/13114953/how-do-i-get-id-of-a-widget-that-invoke-an-event-tkinter
			canvas = event.widget
			canvas.coords(MyGUI.CANVAS_DND_LINK_LINE_TAG, self._drag_data["x"], self._drag_data["y"], event.x, event.y)



	def _on_mouse_leave(self, event):
		""" deleting background lines when mouse leaves BMO rectangle """
		event.widget.delete(MyGUI.CANVAS_BG_LINK_LINE_TAG)


	def _register_dms_callback(self):
		"""
		monitoring PSC document opening activity in currently running GE instance
		"""

		dms_key_str = ':'.join(['System:Node', self._ge_host, 'Image'])

		logger.debug('MyGUI._register_dms_callback(): trying to subscribe DMS key "' + dms_key_str + '"...')
		sub_obj = self._dms_ws.get_dp_subscription(path=dms_key_str,
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

		if new_image:
			# assumption: called during initialisation
			filename = new_image
		else:
			# assumption: called by Tkinter schedule
			try:
				event = self._image_queue.get(block=False)
			except queue.Empty:
				filename = ''
			else:
				# (this is an optional else clause when no exception occured)
				logger.debug('MyGUI._ge_image_changed(): got DMS-event [DMS-key="' + event.path + '" / value=' + event.value + ']')
				filename = event.value

		if filename:
			# only redraw canvas when shown PSC is not a reinit of BMO instance
			dms_key_str = ':'.join(['^System:Node', self._ge_host, 'ImgReInit$'])
			if not self._dms_ws.dp_get(path=dms_key_str)[0].value:
				logger.info('MyGUI._cb_ge_image_changed(): GE opened PSC file "' + filename + '"')
				psc_fullpath = os.path.join(self._prj, 'scr', filename)
				self._load_psc_image(psc_fullpath)

		# scheduling next execution
		self.after(200, self._ge_image_changed)


	def _ge_psc_changed(self):
		""" consume filechanges from filewatcher """

		try:
			change = self._filewatcher.has_changed_queue.get(block=False)
		except queue.Empty:
			pass
		else:
			# (this is an optional else clause when no exception occured)
			if change == Filewatcher.HAS_CHANGED:
				logger.info('MyGUI._ge_psc_changed(): current PSC file was changed... =>reloading it')
				self._load_psc_image(psc_fullpath=None)

		# scheduling next execution
		self.after(200, self._ge_psc_changed)


	def _load_psc_image(self, psc_fullpath):
		if psc_fullpath:
			# settings of rootwindow
			self.parent.title(MyGUI.ROOT_TITLE + u' - ' + psc_fullpath)

			# preset parser and load PSC image
			self.psc_handler.set_psc_file(psc_fullpath)
			self._filewatcher.set_fullpath(psc_fullpath)
		else:
			# need to reload current PSC file
			self.psc_handler.set_psc_file(fname=None)
		self._update_canvas()


	def _update_canvas(self):
		self._buildCanvasVisu(parent=self._canvas_frame)

		def bmo_exists(instance_str):
			# check if BMO instance does exist
			dms_key_str = ':'.join([instance_str, 'OBJECT'])
			resp = self._dms_ws.dp_get(path=dms_key_str)
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
		for resp in dms_ws.dp_get(path="", query=dms.Query(regExPath=r'^System:Prog:GE:.*:UP$', maxDepth=0)):
			if resp.value:
				curr_ge_host = resp.path.replace('System:Prog:GE:', '')[:-3]
				logger.debug('found a running GE instance on host "' + curr_ge_host + '"...')
				break

		if curr_ge_host:
			# FIXME: implement a cleaner way for keeping ONE instance of ParserConfig in whole program...
			Parser.PscParser.load_config(Parser.PARSERCONFIGFILE)

			curr_psc_handler = BMO_Elements_Handler()
			filewatcher = Filewatcher()

			# Build a gui
			rootWindow = Tkinter.Tk()
			app = MyGUI(parent=rootWindow, psc_handler=curr_psc_handler, filewatcher=filewatcher, dms_ws=dms_ws, prj=curr_proj, ge_host=curr_ge_host)

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