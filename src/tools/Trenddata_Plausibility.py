#!/usr/bin/env python
# encoding: utf-8
"""
tools.Trenddata_Plausibility.py      v0.0.1
Shows trenddata in diagrams for visual plausibility check

Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



import dms.dmswebsocket as dms
import logging
import argparse
import Tkinter
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
logger = logging.getLogger('tools.Trenddata_Plausibility')
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

ROOTWINDOW_TITLE = u'Trenddata Plausibility v0.0.1'


class Param_Frame(Tkinter.Frame):

	# interval texts and timedelta: we need always same sorting...
	INTERVALS = collections.OrderedDict()
	INTERVALS['day'] = datetime.timedelta(days=1)
	INTERVALS['week'] = datetime.timedelta(days=7)
	INTERVALS['month'] = datetime.timedelta(days=31)
	INTERVALS['year'] = datetime.timedelta(days=365)

	RESOLUTIONS = collections.OrderedDict()
	RESOLUTIONS['1h'] = datetime.timedelta(hours=1)
	RESOLUTIONS['2h'] = datetime.timedelta(hours=2)
	RESOLUTIONS['3h'] = datetime.timedelta(hours=3)
	RESOLUTIONS['4h'] = datetime.timedelta(hours=4)
	RESOLUTIONS['6h'] = datetime.timedelta(hours=6)
	RESOLUTIONS['12h'] = datetime.timedelta(hours=12)
	RESOLUTIONS['24h'] = datetime.timedelta(days=1)



	def __init__(self, parent):
		self._parent = parent
		Tkinter.Frame.__init__(self, master=parent, borderwidth=1, relief=Tkinter.SUNKEN)

		self._interval = None
		self._resolution = None

		self._interval_var = Tkinter.StringVar()
		self._interval_var.set('year')  # default

		self._nof_rows_var = Tkinter.IntVar()
		self._nof_rows_var.set(2)   # default

		self._resolution_var = Tkinter.StringVar()
		self._resolution_var.set('24h')  # default


		self._draw_gui()

	def _draw_gui(self):
		# optionmenu: example from http://effbot.org/tkinterbook/optionmenu.htm
		# "apply" seems deprecated... https://stackoverflow.com/questions/26744366/adding-command-to-a-tkinter-optionmenu
		options = Param_Frame.INTERVALS.keys()
		self._optmenu_intervals = Tkinter.OptionMenu(self, self._interval_var, *options, command=self._cb_optmenu_interval)

		self._optmenu_rows = Tkinter.OptionMenu(self, self._nof_rows_var, *range(1, 11))

		options = Param_Frame.RESOLUTIONS.keys()
		self._optmenu_resolution = Tkinter.OptionMenu(self, self._resolution_var, *options, command=self._cb_optmenu_resolution)

		Tkinter.Label(master=self, text='general parameters').grid(row=0, column=0, columnspan=2)


		Tkinter.Label(master=self, text='interval').grid(row=2, column=0)
		self._optmenu_intervals.grid(row=1, column=1)

		Tkinter.Label(master=self, text='number of rows').grid(row=3, column=0)
		self._optmenu_rows.grid(row=2, column=1)

		Tkinter.Label(master=self, text='resolution').grid(row=1, column=0)
		self._optmenu_resolution.grid(row=3, column=1)


	def _cb_optmenu_interval(self, *args):
		self._interval = Param_Frame.INTERVALS[args[0]]

	def _cb_optmenu_resolution(self, *args):
		self._resolution = Param_Frame.RESOLUTIONS[args[0]]


	def get_interval(self):
		# executing callback manually if needed
		if not self._interval:
			self._cb_optmenu_interval(self._interval_var.get())
		return self._interval

	def get_nof_rows(self):
		return self._nof_rows_var.get()

	def get_resolution(self):
		# executing callback manually if needed
		if not self._resolution:
			self._cb_optmenu_resolution(self._resolution_var.get())
		return self._resolution


class Interpretation(Tkinter.Frame):
	def __init__(self, parent, histData):
		self._parent = parent
		self._histData = histData
		self._histData_ts = None      # pandas timeseries
		Tkinter.Frame.__init__(self, master=parent, borderwidth=1, relief=Tkinter.SUNKEN)

		Tkinter.Label(master=self, text="show diagram").grid(row=0, column=0, columnspan=3)

		Tkinter.Button(master=self, text='line', command=self._cb_btn_line).grid(row=1, column=0)
		Tkinter.Button(master=self, text='heatmap', command=self._cb_btn_heatmap).grid(row=1, column=1)
		Tkinter.Button(master=self, text='histogram', command=self._cb_btn_histogram).grid(row=1, column=2)


	def _cb_btn_line(self):
		logger.debug('Interpretation._cb_btn_line()')

	def _cb_btn_heatmap(self):
		logger.debug('Interpretation._cb_btn_heatmap()')

	def _cb_btn_histogram(self):
		logger.debug('Interpretation._cb_btn_histogram()')


class InterprDigital(Interpretation):
	def __init__(self, *args, **kwargs):
		Interpretation.__init__(self, *args, **kwargs)


class InterprDigitalFrequency(InterprDigital):
	def __init__(self, *args, **kwargs):
		InterprDigital.__init__(self, *args, **kwargs)

class InterprDigitalDutycycle(InterprDigital):
	def __init__(self, *args, **kwargs):
		InterprDigital.__init__(self, *args, **kwargs)


class InterprAnalog(Interpretation):
	def __init__(self, *args, **kwargs):
		Interpretation.__init__(self, *args, **kwargs)

class InterprAnalogAbsolut(InterprAnalog):
	def __init__(self, *args, **kwargs):
		InterprAnalog.__init__(self, *args, **kwargs)

class InterprAnalogChange(InterprAnalog):
	def __init__(self, *args, **kwargs):
		InterprAnalog.__init__(self, *args, **kwargs)


class ChooseInterpretation(Tkinter.Frame):
	def __init__(self, parent, datatype):
		self._parent = parent
		self._datatype = datatype
		Tkinter.Frame.__init__(self, master=parent, borderwidth=1, relief=Tkinter.SUNKEN)

		self._radiobtn_var = Tkinter.IntVar()
		self._radiobtn_var.set(-1)  # default: none of the radiobuttons is selected
		self._radiobtn_var.trace("w", self._cb_radiobtn_changed)

		# used in factory of interpretation instances
		# (index is radiobutton value)
		self._interpr_class_list = []

		if self._datatype == 'bool':
			rbtn = Tkinter.Radiobutton(master=self, text="frequency", variable=self._radiobtn_var, value=0)
			rbtn.grid(row=1, column=0)
			self._interpr_class_list.append(InterprDigitalFrequency)

			rbtn = Tkinter.Radiobutton(master=self, text="duty cycle", variable=self._radiobtn_var, value=1)
			rbtn.grid(row=1, column=1)
			self._interpr_class_list.append(InterprDigitalDutycycle)
		else:
			rbtn = Tkinter.Radiobutton(master=self, text="absolut", variable=self._radiobtn_var, value=0)
			rbtn.grid(row=1, column=0)
			self._interpr_class_list.append(InterprAnalogAbsolut)

			rbtn = Tkinter.Radiobutton(master=self, text="change", variable=self._radiobtn_var, value=1)
			rbtn.grid(row=1, column=1)
			self._interpr_class_list.append(InterprAnalogChange)


	def _cb_radiobtn_changed(self, *args):
		histData = self._parent.get_histdata()
		idx = self._radiobtn_var.get()
		obj = self._interpr_class_list[idx](parent=self._parent, histData=histData)
		self._parent.add_diabutton_frame(obj)



class MyGUI(Tkinter.Tk):

	# Testproject
	#PATH = "MSR01:Ala101:Output_Lampe"

	# analogue
	PATH = "MSR01_A:Allg:Aussentemp:Istwert"

	# digital
	#PATH = "MSR01_C:H07:LG_FunUeb_ErZae:EingangsSig:Input"


	def __init__(self, curr_DMS):
		Tkinter.Tk.__init__(self)
		self.minsize(width=800, height=700)
		self.wm_title(ROOTWINDOW_TITLE)

		self._curr_DMS = curr_DMS
		self._datatype = None

		self._curr_tz = timezone.Timezone().get_tz()



		Tkinter.Label(master=self, text="datapoint: " + MyGUI.PATH).grid(row=0, column=0, columnspan=2)

		self._radiobtn_alldata_var = Tkinter.BooleanVar()
		self._radiobtn_alldata_var.set(False)  # default

		rbtn0 = Tkinter.Radiobutton(master=self, text="preview", variable=self._radiobtn_alldata_var, value=False)
		rbtn0.grid(row=1, column=0)

		rbtn1 = Tkinter.Radiobutton(master=self, text="all trenddata", variable=self._radiobtn_alldata_var, value=True)
		rbtn1.grid(row=1, column=1)

		self._param_frame = Param_Frame(parent=self)
		self._param_frame.grid(row=3, column=0, columnspan=2)

		btn_grab_data = Tkinter.Button(master=self,
		                                   text='grab trenddata',
		                                     command=self._cb_btn_grab_data)
		btn_grab_data.grid(row=4, column=0, columnspan=2)


		self._choose_interpr_frame = None

		self._diabutton_frame = None


	def add_diabutton_frame(self, frame):
		if frame:
			self._diabutton_frame = frame
			self._diabutton_frame.grid(row=6, column=0, columnspan=2)
		else:
			self._diabutton_frame = None

	def get_histdata(self):
		return self._histData


	def _cb_btn_grab_data(self):
		try:

			resp = self._curr_DMS.dp_get(path=MyGUI.PATH,
			                             query=dms.Query(hasHistData=True))
			try:
				one_resp = resp[0]
				if one_resp.code == 'ok':
					self._datatype = one_resp.type
				else:
					logger.error('MyGUI._cb_btn_grab_data(): ERROR from DMS: ' + one_resp.message)
			except IndexError:
				logger.error('MyGUI._cb_btn_grab_data(): ERROR: datapoint "' + MyGUI.PATH + '" is not available or has no trending!')
				return

			if self._datatype in ("int", "double", "bool"):
				# trenddata retrieving from past until now
				# workaround: when second and millisecond is not null in HistData, then DMS doesn't handle "end"...
				now_dt = datetime.datetime.now(tz=self._curr_tz).replace(second=0, microsecond=0)


				if self._radiobtn_alldata_var.get():
					# alldata mode: retrieve all trenddata
					histData_interval = 0
				else:
					# preview mode: retrieve only minimum trenddata
					resolution_td = self._param_frame.get_resolution()
					histData_interval = resolution_td.days * 3600 * 24 + resolution_td.seconds

				histDataObj = dms.HistData(start=now_dt - self._param_frame.get_nof_rows() * self._param_frame.get_interval(),
				                           end=now_dt,
				                           format="detail",
				                           interval=histData_interval
				                           )
				#logger.debug('MyGUI._cb_btn_grab_data(): histDataObj=' + repr(histDataObj))
				resp = self._curr_DMS.dp_get(path=MyGUI.PATH,
				                             histData=histDataObj,
				                             showExtInfos=dms.INFO_ALL
				                             )
				one_resp = resp[0]
				if one_resp.code == 'ok':
					self._histData = one_resp.histData

					# update GUI
					self._choose_interpr_frame = ChooseInterpretation(parent=self, datatype=one_resp.type)
					self._choose_interpr_frame.grid(row=5, column=0, columnspan=2)

					# FIXME!!!
					#self._btn_frame = self._get_buttons_frame()
					#self._btn_frame.grid(row=5, column=0, columnspan=2)

					## short demonstration
					#plt.figure()
					#self._histData_ts.plot()
					## help from https://stackoverflow.com/questions/16522380/matplotlib-plot-is-a-no-show
					#plt.show()

				else:
					logger.error('MyGUI._cb_btn_grab_data(): ERROR: ' + one_resp.message)

					# update GUI
					self._choose_interpr_frame = None
			else:
				logger.error('MyGUI._cb_btn_grab_data(): ERROR: datapoint has unexpected datatype ' + str(self._datatype))
		except Exception as ex:
			logger.exception(ex)


	def _get_nof_rows(self):
		return self._param_frame.get_nof_rows()


	def _histData_as_timeseries(self, histdata):
		if histdata:
			nof_histData = len(histdata)
			logger.debug('MyGUI._histData_as_timeseries(): number of histData objects: ' + str(nof_histData))

			# based on example from https://pandas-docs.github.io/pandas-docs-travis/timeseries.html
			# (iteratively appending to a pandas Series is not recommended!)
			#  read https://pandas.pydata.org/pandas-docs/stable/generated/pandas.Series.append.html
			# and usage hint from https://stackoverflow.com/questions/10839701/time-weighted-average-with-pandas/10856106#10856106
			tstamps = []
			states = []
			values = []
			recs = []
			for item in histdata:
				tstamps.append(pd.Timestamp(item['stamp']))
				states.append(item['state'])
				values.append(item['value'])
				recs.append(item['rec'])
			return pd.Series(data={'value': values, 'state': states, 'rec': recs}, index=tstamps)
		else:
			return None






def main(dms_server, dms_port):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.Trenddata_Plausibility',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		root = MyGUI(dms_ws)
		root.mainloop()

	logger.info('Quitting "Trenddata_Plausibility"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Shows trenddata in diagrams for visual plausibility check.')

	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port)
	#sys.exit(status)