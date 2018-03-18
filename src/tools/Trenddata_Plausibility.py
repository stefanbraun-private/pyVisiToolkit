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


class MyGUI(Tkinter.Tk):

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

	PATH = "MSR01:Ala101:Output_Lampe"

	def __init__(self, curr_DMS):
		Tkinter.Tk.__init__(self)
		self.minsize(width=800, height=700)
		self.wm_title(ROOTWINDOW_TITLE)

		self._curr_DMS = curr_DMS
		self._datatype = None
		self._histDataArr = None
		self._timedelta = None
		self._resolution = None
		self._interval = None
		self._curr_tz = timezone.Timezone().get_tz()

		self._resolution_var = Tkinter.StringVar()
		self._resolution_var.set('24h')  # default

		self._interval_var = Tkinter.StringVar()
		self._interval_var.set('year')  # default

		self._nof_rows_var = Tkinter.IntVar()
		self._nof_rows_var.set(2)   # default


		self._btn_grab_data = Tkinter.Button(master=self,
		                                   text='grab trenddata',
		                                     command=self._cb_btn_grab_data)

		# optionmenu: example from http://effbot.org/tkinterbook/optionmenu.htm
		# "apply" seems deprecated... https://stackoverflow.com/questions/26744366/adding-command-to-a-tkinter-optionmenu
		options = MyGUI.RESOLUTIONS.keys()
		self._optmenu_resolutions = Tkinter.OptionMenu(self, self._resolution_var, *options, command=self._cb_optmenu_resolution)
		options = MyGUI.INTERVALS.keys()
		self._optmenu_intervals = Tkinter.OptionMenu(self, self._interval_var, *options, command=self._cb_optmenu_interval)

		self._optmenu_rows = Tkinter.OptionMenu(self, self._nof_rows_var, *range(1, 11))

		Tkinter.Label(master=self, text='Heatmap').grid(row=0, column=0, columnspan=2)

		Tkinter.Label(master=self, text='Heatmap resolution').grid(row=1, column=0)
		self._optmenu_resolutions.grid(row=1, column=1)

		Tkinter.Label(master=self, text='Heatmap interval').grid(row=2, column=0)
		self._optmenu_intervals.grid(row=2, column=1)

		Tkinter.Label(master=self, text='number of rows').grid(row=3, column=0)
		self._optmenu_rows.grid(row=3, column=1)

		self._btn_grab_data.grid(row=4, column=0, columnspan=2)


	def _cb_optmenu_resolution(self, *args):
		self._resolution = MyGUI.RESOLUTIONS[args[0]]

	def _cb_optmenu_interval(self, *args):
		self._interval = MyGUI.INTERVALS[args[0]]

	def _cb_btn_grab_data(self):
		try:
			# executing callbacks manually if needed
			if not self._resolution:
				self._cb_optmenu_resolution(self._resolution_var.get())
			if not self._interval:
				self._cb_optmenu_interval(self._interval_var.get())

			#
			resp = self._curr_DMS.dp_get(path=MyGUI.PATH,
			                             query=dms.Query(hasHistData=True))
			try:
				one_resp = resp[0]
				if one_resp.code == 'ok':
					self._datatype = one_resp.type
				else:
					logger.error('MyGUI._cb_btn_grab_data(): ERROR:' + one_resp.message)
			except IndexError:
				logger.error('MyGUI._cb_btn_grab_data(): ERROR: datapoint "' + MyGUI.PATH + '" is not available or has no trending!')
				return

			if self._datatype in ("int", "double", "bool"):
				# trenddata retrieving from past until now
				# workaround: when second and millisecond is not null in HistData, then DMS doesn't handle "end"...
				now_dt = datetime.datetime.now(tz=self._curr_tz).replace(second=0, microsecond=0)

				if self._datatype == "bool":
					# boolean values: asking for EVERY trenddata point
					interv = 0
				else:
					# other datatypes: asking for INTERPOLATED trenddata
					interv = self._resolution.days * 3600 * 24 + self._resolution.seconds
				histDataObj = dms.HistData(start=now_dt - self._nof_rows_var.get() * self._interval,
				                           end=now_dt,
				                           format="detail",
				                           interval=interv
				                           )
				logger.debug('MyGUI._cb_btn_grab_data(): histDataObj=' + repr(histDataObj))
				resp = self._curr_DMS.dp_get(path=MyGUI.PATH,
				                             histData=histDataObj,
				                             showExtInfos=dms.INFO_ALL
				                             )
				one_resp = resp[0]
				if one_resp.code == 'ok':
					self._histDataArr = one_resp.histData
				else:
					logger.error('MyGUI._cb_btn_grab_data(): ERROR: ' + one_resp.message)
			else:
				logger.error('MyGUI._cb_btn_grab_data(): ERROR: datapoint has unexpected datatype ' + self._datatype)
		except Exception as ex:
			logger.exception(ex)


	def _update_buttons(self):
		btn_frame = Tkinter.Frame(master=self)

		btn_frequency = Tkinter.Button(master=btn_frame, text="show frequency")
		btn_frequency.grid(row=1, column=0)



		if self._datatype == "bool":
			# frequency, ontime
			pass
		else:
			# lines, heatmap, histogram
			pass

	def _foo(self):
		# FIXME!!!
		nof_histData = len(one_resp.histData)
		logger.debug('MyGUI._cb_btn_grab_data(): number of histData objects: ' + str(nof_histData))
		if nof_histData:
			nof_rows = self._nof_rows_var.get()
			interval_secs = self._interval.days * 3600 * 24 + self._interval.seconds
			resolution_secs = self._resolution.days * 3600 * 24 + self._resolution.seconds
			nof_columns = interval_secs / resolution_secs

			## empty array: https://docs.scipy.org/doc/numpy/reference/generated/numpy.zeros.html#numpy.zeros
			#missing_points = np.zeros(shape=nof_rows * nof_columns - nof_histData)

			# filling array: https://docs.scipy.org/doc/numpy/reference/generated/numpy.fromiter.html
			iterable = (item['value'] for item in one_resp.histData)
			a = np.fromiter(iterable, np.float)

			# resizing (missing values get zeros): https://docs.scipy.org/doc/numpy-1.13.0/reference/generated/numpy.resize.html
			a = np.resize(a, nof_rows * nof_columns)

			# reshape: https://docs.scipy.org/doc/numpy/reference/generated/numpy.reshape.html
			a = np.reshape(a, (nof_rows, nof_columns))

			logger.debug('MyGUI._cb_btn_grab_data(): numpy array a=' + repr(a))

			# FIXME: embedding plot into Tkinter
			# https://stackoverflow.com/questions/33282368/plotting-a-2d-heatmap-with-matplotlib
			plt.imshow(a, cmap='hot', interpolation='nearest')
			plt.show()


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