#!/usr/bin/env python
# encoding: utf-8
"""
tools.Renumber_tool.py
Assign PLC ressources for SDriver (automate renumbering in PET)

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
import functools

DEBUGGING = True


def keyfunc_dmskey(dmskey_str):
	# Used as key function for Python's built-in function "sorted()"
	# https://docs.python.org/2/library/functions.html#sorted
	# returns a tuple used by sorted() for sorting an iterable in a similar order as PET
	# (copy behaviour of PET needs some tricks, because it uses other ordering as ASCII...)
	# FIXME: WARNING: it's possible to use non-alphanumeric characters as DMS key, but I simply ignore this special case
	#        (means ordering in PET can be different to ordering done by this Python tool...!
	#         This shouldn't have any negative effect for resource allocation of flags and register,
	#         but WOULD POSSIBLY CORRUPT DATABLOCKS because we expect all parts of the same datablock directly after "CFG_CONFIG_DB"...)

	# replacing underscore (PET places underscore before alphanumerics =>replace by ASCII-character before 'A' for same result)
	# and doublepoint (PET places it between underscore and alphanumerics =>replace by ASCII-character before 'A' for same result)
	my_key = dmskey_str.replace(':', ' ').replace('_', '!')

	# PET sorts in order 'A', 'a', 'B', 'b', ... =>ignoring case in first item of this tuple
	# second tuple is case-sensitive string ('a' is after 'A' in PET, same as in ASCII)
	return (my_key.upper(), my_key)



class Plc(object):
	def __init__(self, name_str):
		self.name = name_str
		self.analogue_dict = {}
		self.digital_dict = {}
		self.datablock_dict = {}
		self.station_int = -1
		self.channel_str = ''

	def add_analogue(self, dpname, plc_string):
		self.analogue_dict[dpname] = Analogue_resource(dpname, plc_string)

	def add_digital(self, dpname, plc_string):
		self.digital_dict[dpname] = Digital_resource(dpname, plc_string)

	def add_datablock(self, dpname, plc_string):
		self.datablock_dict[dpname] = Datablock_resource(0, dpname, plc_string)

	def read_details_from_dms(self, curr_dms):
		for dp in self.analogue_dict:
			self.analogue_dict[dp].read_from_dms(curr_dms)
		for dp in self.digital_dict:
			self.digital_dict[dp].read_from_dms(curr_dms)
		for dp in self.datablock_dict:
			self.datablock_dict[dp].read_from_dms(curr_dms)


	def renumber_resources(self):
		# process digital datapoints first (this way we're ready when we need to start analogue datapoints with higher telegram number)
		# using built-in "sorted()" function for getting same ordering as in PET (DMS-keys are case-sensitive)
		# =>but: Python's "sorted()" seems to sort by ASCII-code, and Visi+ by AaBbCcDd... =>need to help sorted() with own key-function:
		# http://stackoverflow.com/questions/13954841/python-sort-upper-case-and-lower-case
		# https://docs.python.org/2/library/functions.html#sorted

		# digital datapoints
		Digital_resource.reset_addr_generator()
		for dp in sorted(self.digital_dict, key=keyfunc_dmskey):
			curr_telegr, curr_addr = Digital_resource.get_next_addr()
			self.digital_dict[dp].set_addr(station_int=self.station_int,
			                               channel_str=self.channel_str,
			                               telegr_int=curr_telegr,
			                               addr_int=curr_addr)

		# analogue datapoints
		my_telegram = max(curr_telegr + 1, Analogue_resource.DEFAULT_TELEGRAM)
		Analogue_resource.reset_addr_generator(my_telegram)
		for dp in sorted(self.analogue_dict, key=keyfunc_dmskey):
			curr_telegr, curr_addr = Analogue_resource.get_next_addr()
			self.analogue_dict[dp].set_addr(station_int=self.station_int,
			                               channel_str=self.channel_str,
			                               telegr_int=curr_telegr,
			                               addr_int=curr_addr)

		# datablock datapoints
		# FIXME:
		Datablock_resource.reset_addr_generator()
		for dp in sorted(self.datablock_dict, key=keyfunc_dmskey):
			is_config_db = self.datablock_dict[dp].dp_name.split(':')[-1].upper() == 'CFG_CONFIG_DB'
			curr_telegr, curr_addr, curr_dbidx = Datablock_resource.get_next_addr(is_config_db)
			self.datablock_dict[dp].set_addr(station_int=self.station_int,
			                                channel_str=self.channel_str,
			                                telegr_int=curr_telegr,
			                                addr_int=curr_addr,
			                                db_index_int=curr_dbidx)


	def write_details_to_dms(self, curr_dms):
		for dp in self.analogue_dict:
			self.analogue_dict[dp].write_to_dms(curr_dms)
		for dp in self.digital_dict:
			self.digital_dict[dp].write_to_dms(curr_dms)
		for dp in self.datablock_dict:
			self.datablock_dict[dp].write_to_dms(curr_dms)

	def set_station_channel(self, station_int, channel_str):
		self.station_int = station_int
		self.channel_str = channel_str


class Resource(object):
	def __init__(self, dp_name, plc_string, address=0, channel='', station=0, telegram=0, type=''):
		self.dp_name = dp_name
		self.address = address
		self.channel = channel
		self.station = station
		self.telegram = telegram
		self.type = ''
		self.plc_string = plc_string

	def read_from_dms(self, curr_dms):
		self.address = curr_dms.pyDMS_ReadDWSEx(self.dp_name + ':PLC:Address')
		self.channel = curr_dms.pyDMS_ReadSTREx(self.dp_name + ':PLC:Channel')
		self.station = curr_dms.pyDMS_ReadDWSEx(self.dp_name + ':PLC:Station')
		self.telegram = curr_dms.pyDMS_ReadDWSEx(self.dp_name + ':PLC:Telegram')
		self.type = curr_dms.pyDMS_ReadSTREx(self.dp_name + ':PLC:Type')


	def set_addr(self, station_int, channel_str, telegr_int, addr_int):
		self.station = station_int
		self.channel = channel_str
		self.telegram = telegr_int
		self.address = addr_int
		# update PLC-string in this instance
		self.concat_combined_string()


	def write_to_dms(self, curr_dms):
		curr_dms.pyDMS_WriteDWSEx(self.dp_name + ':PLC:Address', self.address)
		curr_dms.pyDMS_WriteSTREx(self.dp_name + ':PLC:Channel', self.channel)
		curr_dms.pyDMS_WriteDWSEx(self.dp_name + ':PLC:Station', self.station)
		curr_dms.pyDMS_WriteDWSEx(self.dp_name + ':PLC:Telegram', self.telegram)
		curr_dms.pyDMS_WriteSTREx(self.dp_name + ':PLC:Type', self.type)
		curr_dms.pyDMS_WriteSTREx(self.dp_name + ':PLC', self.plc_string)


class Analogue_resource(Resource):
	MINIMUM_ADDR = 1000
	ADDR_PER_TELEGR = 3500        # max. amount of datapoints per telegram
	DEFAULT_TYPE = 'Register'
	DEFAULT_TELEGRAM = 3

	nof_dp = 0
	first_telegr = 0

	def __init__(self, *args, **kwargs):
		Resource.__init__(self, *args, **kwargs)

	@classmethod
	def reset_addr_generator(cls, telegram=0):
		cls.nof_dp = 0
		if telegram > 0:
			cls.first_telegr = telegram
		else:
			cls.first_telegr = cls.DEFAULT_TELEGRAM

	@classmethod
	def get_next_addr(cls):
		cls.nof_dp = cls.nof_dp + 1
		curr_addr = cls.MINIMUM_ADDR - 1 + cls.nof_dp
		curr_telegr = (cls.nof_dp - 1) / cls.ADDR_PER_TELEGR + cls.first_telegr
		if DEBUGGING:
			if curr_addr < cls.MINIMUM_ADDR:
				print('get_next_addr() returns wrong value: cls.nof_dp=' + str(cls.nof_dp) )
		return curr_telegr, curr_addr

	def concat_combined_string(self):
		self.plc_string = self.channel + ' ' + 'R' + str(self.address).zfill(4)

	def set_addr(self, **kwargs):
		Resource.set_addr(self, **kwargs)

		# setting right PLC datatype
		self.type = Analogue_resource.DEFAULT_TYPE


class Digital_resource(Resource):
	MINIMUM_ADDR = 1000
	ADDR_PER_TELEGR = 3500        # max. amount of datapoints per telegram
	DEFAULT_TYPE = 'Flag'
	DEFAULT_TELEGRAM = 1
	DEFAULT_INVERSE_LOGIC = False   # PET and SDriver: True = inverse logic, False = normal logic

	nof_dp = 0
	first_telegr = 0

	def __init__(self, *args, **kwargs):
		Resource.__init__(self, *args, **kwargs)
		self.inverse_logic = False

	@classmethod
	def reset_addr_generator(cls, telegram=0):
		cls.nof_dp = 0
		if telegram > 0:
			cls.first_telegr = telegram
		else:
			cls.first_telegr = cls.DEFAULT_TELEGRAM

	@classmethod
	def get_next_addr(cls):
		cls.nof_dp = cls.nof_dp + 1
		curr_addr = cls.MINIMUM_ADDR - 1 + cls.nof_dp
		curr_telegr = (cls.nof_dp - 1) / cls.ADDR_PER_TELEGR + cls.first_telegr
		return curr_telegr, curr_addr

	def read_from_dms(self, curr_dms):
		self.inverse_logic = curr_dms.pyDMS_ReadDWSEx(self.dp_name + ':PLC:Logic')
		Resource.read_from_dms(self, curr_dms)

	def concat_combined_string(self):
		self.plc_string = self.channel + ' ' + 'F' + str(self.address).zfill(4)

	def set_addr(self, **kwargs):
		Resource.set_addr(self, **kwargs)

		# setting right PLC datatype
		self.type = Digital_resource.DEFAULT_TYPE

		# setting default logic interpretation
		self.inverse_logic = Digital_resource.DEFAULT_INVERSE_LOGIC

	def write_to_dms(self, curr_dms):
		curr_dms.pyDMS_WriteBITEx(self.dp_name + ':PLC:Logic', self.inverse_logic)
		Resource.write_to_dms(self, curr_dms)


class Datablock_resource(Resource):
	MINIMUM_ADDR = 0
	DEFAULT_TYPE = 'Datablock DWU'
	DBINDEX_PER_ADDR = 10         # datablock: DBIndex 0..9 per datablock-address (and only one datablock per telegram)
	DEFAULT_TELEGRAM = 101

	next_telegr = 0
	next_addr = 0
	next_dbidx = 0

	def __init__(self, db_index=0, *args, **kwargs):
		Resource.__init__(self, *args, **kwargs)
		self.db_index = db_index

	@classmethod
	def reset_addr_generator(cls, telegram=0):
		cls.next_telegr = cls.DEFAULT_TELEGRAM
		cls.next_addr = cls.MINIMUM_ADDR
		cls.next_dbidx = 0
		if telegram > 0:
			cls.curr_telegr = telegram
		else:
			cls.curr_telegr = cls.DEFAULT_TELEGRAM

	@classmethod
	def get_next_addr(cls, is_config_db):
		# datablock: DBIndex 0..9 per datablock-address (and only one datablock per telegram)
		# EXCEPTION: datapoints 'CFG_CONFIG_DB' start always a separate address/telegram,
		#            all following "CFG_*"/"VIS_*" PLC-parts of the same BMO instance are part of the same address/telegram

		# handling special cases for THIS datablock
		if is_config_db:
			if cls.next_dbidx != 0:
				# begin new address/telegram
				cls.next_telegr += 1
				cls.next_addr += 1
				cls.next_dbidx = 0

		# current addressing
		curr_telegr = cls.next_telegr
		curr_addr = cls.next_addr
		curr_dbidx = cls.next_dbidx

		# setting addressing of NEXT datablock
		# usual processing: increasing DBIndex, and increase address/telegram when needed
		cls.next_dbidx += 1
		if cls.next_dbidx >= (cls.DBINDEX_PER_ADDR):
			cls.next_telegr += 1
			cls.next_addr += 1
			cls.next_dbidx = 0

		return curr_telegr, curr_addr, curr_dbidx


	def read_from_dms(self, curr_dms):
		self.db_index = curr_dms.pyDMS_ReadDWSEx(self.dp_name + ':PLC:DBIndex')
		Resource.read_from_dms(self, curr_dms)

	def set_addr(self, **kwargs):
		try:
			self.db_index = kwargs['db_index_int']
		except KeyError:
			raise TypeError('set_addr() got wrong arguments')

		# calling function of superclass without this argument
		del kwargs['db_index_int']
		Resource.set_addr(self, **kwargs)

		# setting right PLC datatype
		self.type = Datablock_resource.DEFAULT_TYPE

	def write_to_dms(self, curr_dms):
		curr_dms.pyDMS_WriteDWSEx(self.dp_name + ':PLC:DBIndex', self.db_index)
		Resource.write_to_dms(self, curr_dms)

	def concat_combined_string(self):
		self.plc_string = self.channel + ' ' + 'D' + str(self.address).zfill(4) + '.' + str(self.db_index)


class Renumber_tool(object):
	def __init__(self, curr_dms):
		self.plc_dict = {}
		self.curr_dms = curr_dms
		self.nof_communicated_dps = 0
		self.curr_prj = self.curr_dms.pyDMS_ReadSTREx('System:Project')
		assert self.curr_prj != '', 'Unable to retrieve datapoint "System:Project"... Is DMS running?'
		print('CONNECTED TO DMS.')

	def collect_comm_dps(self):
		# collect all communicated datapoints into our list of PLCs
		for item in self.curr_dms.get_DMS_keyvalue_list_by_keypart('PLC'):
			curr_key_str, curr_value = item

			curr_plc = curr_key_str.split(':')[0]
			if curr_plc != 'BMO':
				if not curr_plc in self.plc_dict:
					self.plc_dict[curr_plc] = Plc(curr_plc)

				self.nof_communicated_dps += 1
				curr_comm_dp = ':'.join(curr_key_str.split(':')[:-1])

				# sorting datapoints into one of the three possible SDriver datatypes
				if self.curr_dms.is_dp_available(curr_key_str + ':Logic'):
					# found a digital datapoint
					self.plc_dict[curr_plc].add_digital(curr_comm_dp, curr_value)
				elif self.curr_dms.is_dp_available(curr_key_str + ':Diff'):
					# found an analogue datapoint
					self.plc_dict[curr_plc].add_analogue(curr_comm_dp, curr_value)
				elif self.curr_dms.is_dp_available(curr_key_str + ':DBIndex'):
					# found a datablock
					self.plc_dict[curr_plc].add_datablock(curr_comm_dp, curr_value)
				else:
					print('Warning: SDriver/PLC properties of DMS datapoint "' + curr_comm_dp + '" seem corrupted, ignoring it!')

				# # ATTENTION: following part is wrong (didn't work with analogue value "BMO:ZSP02:ZF_Wahl", it has DMS datatype "DWU",
				# # it seems that we can't depend on DMS datatype...)
				# curr_comm_dp_type = dms.datapoint.Dms_dp_Factory.dp_numeric_types_dict[curr_dms.pyDMS_ReadTypeEx(curr_comm_dp)]
				#
				# if curr_comm_dp_type == 'FLT':
				# 	plc_dict[curr_plc].add_analogue(curr_comm_dp, curr_value)
				# elif curr_comm_dp_type == 'BIT':
				# 	plc_dict[curr_plc].add_digital(curr_comm_dp, curr_value)
				# elif curr_comm_dp_type == 'DWU':
				# 	plc_dict[curr_plc].add_datablock(curr_comm_dp, curr_value)
				# else:
				# 	print('Warning: DMS datapoint "' + curr_comm_dp + '" seems to have wrong DMS-type, no further processing!')

		print('GOT LIST OF ' + str(self.nof_communicated_dps) + ' SDRIVER-DATAPOINTS.')


	def read_dp_details(self):
		# read all SDriver details from DMS
		for my_plc in sorted(self.plc_dict, key=keyfunc_dmskey):
			print('\treading PLC "' + my_plc + '" from DMS...')
			self.plc_dict[my_plc].read_details_from_dms(self.curr_dms)
		print('READING IS DONE.')


	def renumber_dps(self, station=0, plc_name=''):
		# do renumbering of all datapoints
		# (first set station-ID and SDriver channel)
		# =>using same key-function for sorted() as in Plc.renumber_resources()  (for proper ordering of PLCs with an underscore)

		if station == 0 and plc_name == '':
			# renumber ALL datapoints
			offset = 1
			for idx, my_plc in enumerate(sorted(self.plc_dict, key=keyfunc_dmskey)):
				station = idx + offset
				channel = 'Chan' + str(idx + offset).zfill(2)
				print('\tsettings of PLC "' + my_plc + '": station=' + str(station) + ', channel=' + channel)
				self.plc_dict[my_plc].set_station_channel(station, channel)

			for my_plc in sorted(self.plc_dict, key=keyfunc_dmskey):
				print('\trenumbering PLC "' + my_plc + '"...')
				self.plc_dict[my_plc].renumber_resources()
		else:
			# renumber only the given PLC
			channel = 'Chan' + str(station).zfill(2)
			print('\tsettings of PLC "' + plc_name + '": station=' + str(station) + ', channel=' + channel)
			self.plc_dict[plc_name].set_station_channel(station, channel)

			print('\trenumbering PLC "' + plc_name + '"...')
			self.plc_dict[plc_name].renumber_resources()
		print('RENUMBERING IS DONE.')


	def get_plc_name_list(self):
		if DEBUGGING:
			print('get_plc_name_list() returns "' + repr(sorted(self.plc_dict, key=keyfunc_dmskey)))
		return sorted(self.plc_dict, key=keyfunc_dmskey)


	def write_dp_details(self, station=0, plc_name=''):
		if station == 0 and plc_name == '':
			# write all SDriver details back to DMS
			for my_plc in sorted(self.plc_dict, key=keyfunc_dmskey):
				print('\twriting PLC "' + my_plc + '" to DMS...')
				self.plc_dict[my_plc].write_details_to_dms(self.curr_dms)
		else:
			# write only the given PLC
			print('\twriting PLC "' + plc_name + '" to DMS...')
			self.plc_dict[plc_name].write_details_to_dms(self.curr_dms)
		print('WRITING IS DONE.')


class RenumberGui(tk.Tk):
	def __init__(self, ren_tool):
		tk.Tk.__init__(self)
		self.title("Renumber Tool v0.0.1")
		self.resizable(0, 0)
		self.ren_tool = ren_tool
		self._draw_main_structure()


	def _draw_main_structure(self):
		lab = tk.Label(master=self, text="Renumber Tool - semi-automation of PET")
		lab.pack(padx=10, pady=10)

		lab = tk.Label(master=self, text='->current project: ' + self.ren_tool.curr_prj)
		lab.pack(padx=10, pady=10)

		btn = tk.Button(master=self,  text="Save whole DMS", command=self._cb_button_savedms)
		btn.pack(padx=10, pady=2, fill=tk.X)

		curr_plc_list = self.ren_tool.get_plc_name_list()
		if curr_plc_list != []:

			lab = tk.Label(master=self, text='These PLCs were found in DMS:\n(set SBus-station-ID, channel is "Chan<ID>")')
			lab.pack(padx=10, pady=2)

			offset = 1
			for ixd, plc_name in enumerate(sorted(curr_plc_list, key=keyfunc_dmskey)):
				frm = _PlcFrame(ren_tool=self.ren_tool, station_no=(ixd + offset), plc_name=plc_name, master=self, relief=tk.SUNKEN, borderwidth=2)
				frm.pack(padx=10, pady=5, fill=tk.X)

		else:
			lab = tk.Label(master=self, text="(DMS doesn't contain any PLC! There's nothing to do...)")
			lab.pack(padx=10, pady=2)

		frm = _SdriverFrame(rootwindow=self, ren_tool=self.ren_tool, master=self, relief=tk.SUNKEN, borderwidth=2)
		frm.pack(padx=10, pady=5)

		btn = tk.Button(master=self,  text="Quit", command=self._cb_button_quit)
		btn.pack(padx=10, pady=10)

	def _cb_button_savedms(self):
		self.ren_tool.curr_dms.pyDMS_WriteBITEx('System:NT:SaveDMS', 'True')

	def _cb_button_quit(self):
		self.destroy()


class _PlcFrame(tk.Frame):
	def __init__(self, ren_tool, station_no, plc_name, *args, **kwargs):
		tk.Frame.__init__(self, *args, **kwargs)
		self.ren_tool = ren_tool
		self.station_no = station_no
		self.station_no_tk = tk.IntVar()
		self.plc_name = plc_name
		self.station_choosing = tk.IntVar()

		self._draw_main_structure()


	def _draw_main_structure(self):
		lab = tk.Label(master=self, text=self.plc_name, font=("Helvetica", 12), background='lightblue')
		lab.grid(row=0, column=0, padx=5, pady=1)

		lab = tk.Label(master=self, text='Auto [' + str(self.station_no) + ']')
		lab.grid(row=0, column=2, padx=1, pady=1, sticky=tk.E)
		rad = tk.Radiobutton(master=self, text="", variable=self.station_choosing, value=1)
		rad.grid(row=0, column=3, padx=1, pady=1, sticky=tk.E)
		# set this as default value
		self.station_choosing.set(1)

		# default of OptionMenu: choose same station/channel as in auto
		self.station_no_tk.set(self.station_no)
		self.optmenu = tk.OptionMenu(self, self.station_no_tk, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
		self.optmenu.grid(row=1, column=2, padx=1, pady=1)
		#self.entry = tk.Entry(master=self, state=tk.NORMAL)
		#self.entry.insert(0, str(self.station_no))
		#self.entry.grid(row=1, column=2, padx=1, pady=1)
		rad = tk.Radiobutton(master=self, text="", variable=self.station_choosing, value=2)
		rad.grid(row=1, column=3, padx=1, pady=1)


		btn = tk.Button(master=self,  text="Save DMS-subtree", command=self._cb_button_savetree)
		btn.grid(row=0, column=4, padx=5, pady=1, sticky=tk.W+tk.E+tk.N+tk.S)

		btn = tk.Button(master=self,  text="Renumber & Write to DMS", command=self._cb_button_renumber)
		btn.grid(row=1, column=4, padx=5, pady=1, sticky=tk.W+tk.E+tk.N+tk.S)


	def _cb_button_savetree(self):
		export_fname =  'Renumber_' + self.plc_name + '_' + time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime()) + '.dms'
		export_fullpath = os.path.join(self.ren_tool.curr_prj, 'cfg', export_fname)
		print('\nExporting subtree of DMS into exportfile "' + export_fullpath + '"')
		self.ren_tool.curr_dms.write_DMS_subtree_serialization(self.plc_name, export_fullpath)


	def _cb_button_renumber(self):
		if self.station_choosing.get() == 1:
			# automatic station number
			curr_station = self.station_no
		elif self.station_choosing.get() == 2:
			# get users choice
			curr_station = int(self.station_no_tk.get())
		else:
			# something went wrong... do nothing
			print('internal error: "self.station_choosing.get()" has unexpected value ' + str(self.station_choosing.get()) + ' ... ignoring renumber-request...!')
			return
		self.ren_tool.renumber_dps(curr_station, self.plc_name)
		self.ren_tool.write_dp_details(curr_station, self.plc_name)


class _SdriverFrame(tk.Frame):
	def __init__(self, rootwindow, ren_tool, *args, **kwargs):
		tk.Frame.__init__(self, *args, **kwargs)
		self.rootwindow = rootwindow
		self.ren_tool = ren_tool
		self.channel_dict_of_dicts = {}
		self.sdriver_label = None

		# update interval of background tasks
		self.BGTASKINTERVAL = 3000

		self._draw_table()

	def _draw_table(self):
		lab = tk.Label(master=self, text='SDriver status:\n(red and orange means BE CAREFUL)')
		lab.grid(row=0, column=0, padx=2, pady=2)

		# label SDriver state
		sdrv_state = self._get_sdriver_state()
		lab = tk.Label(master=self, text=sdrv_state[0], background=sdrv_state[1])
		lab.grid(row=0, column=1, padx=2, pady=2)
		self.sdriver_label = lab

		lab = tk.Label(master=self, text='SDriver channels:\n(not every channel is in use)')
		lab.grid(row=3, column=0, padx=2, pady=2)


		for item in sorted(self.ren_tool.curr_dms.get_DMS_keyvalue_list_by_keypart('Activated')):
			if item[0].startswith('System:Driver:SDriver:'):
				dms_parts = item[0].split(':')[:-1]
				mychan = ':'.join(dms_parts)
				self.channel_dict_of_dicts[mychan] = {}


		if len(self.channel_dict_of_dicts) > 0:
			# Header:
			# build a table-similar structure:
			# http://stackoverflow.com/questions/11047803/creating-a-table-look-a-like-tkinter
			lab = tk.Label(master=self, text='name', relief=tk.RIDGE)
			lab.grid(row=4, column=0, sticky=tk.N + tk.S + tk.E + tk.W)

			lab = tk.Label(master=self, text='activated', relief=tk.RIDGE)
			lab.grid(row=4, column=1, sticky=tk.N + tk.S + tk.E + tk.W)

			lab = tk.Label(master=self, text='state', relief=tk.RIDGE)
			lab.grid(row=4, column=2, sticky=tk.N + tk.S + tk.E + tk.W)


			row_idx = 4
			for channel in self.channel_dict_of_dicts:
				row_idx = row_idx + 1

				lab = tk.Label(master=self, text=channel, relief=tk.RIDGE)
				lab.grid(row=row_idx, column=0, sticky=tk.N + tk.S + tk.E + tk.W)

				# DMS datapoint *:Activated
				state = self._get_activation(channel)
				lab = tk.Label(master=self, text=state[0], background=state[1], relief=tk.RIDGE)
				lab.grid(row=row_idx, column=1, sticky=tk.N + tk.S + tk.E + tk.W)
				self.channel_dict_of_dicts[channel]['Activated'] = lab


				# DMS datapoint *:Status
				curr_val, curr_color = self._get_status(channel)
				lab = tk.Label(master=self, text=str(curr_val), background=curr_color, relief=tk.RIDGE)
				lab.grid(row=row_idx, column=2, sticky=tk.N + tk.S + tk.E + tk.W)
				self.channel_dict_of_dicts[channel]['Status'] = lab

				# button for activation/deactivation
				# Warning: Tkinter callbacks can't be defined directly with arguments
				# ->Using a lambda function works only when the argument is a fixed value:
				#   command=lambda: self._cb_button_activate(1)
				# ->"channel" is always the last loop value when called this way:
				#   command=lambda: self._cb_button_activate(channel)
				# =>using "partial" from functools:
				# http://stackoverflow.com/questions/6920302/how-to-pass-arguments-to-a-button-command-in-tkinter
				myfunc = functools.partial(self._cb_button_activate, channel)
				btn = tk.Button(master=self, text=state[2], command=myfunc)
				btn.grid(row=row_idx, column=3, sticky=tk.N + tk.S + tk.E + tk.W)
				self.channel_dict_of_dicts[channel]['button'] = btn


			# start background task for keeping Status label updated
			# http://stackoverflow.com/questions/459083/how-do-you-run-your-own-code-alongside-tkinters-event-loop
			self.rootwindow.after(self.BGTASKINTERVAL, self._update_status)

		else:
			lab = tk.Label(master=self, text='(No channels found...)', background='green')
			lab.grid(row=4, column=0, padx=2, pady=2)

	def _get_sdriver_state(self):
		# returns string for label SDriver state
		# index0: text of label
		# index1: color of label
		if self.ren_tool.curr_dms.pyDMS_ReadBITEx('System:Prog:SDRIVER_UP'):
			return 'is running', 'orange'
		else:
			return 'is not running', 'green'


	def _get_activation(self, channel):
		# return strings for GUI elements:
		# index 0: text of label
		# index 1: color of label
		# index 2: text of button
		if self.ren_tool.curr_dms.pyDMS_ReadBITEx(channel + ':Activated'):
			return 'True', 'red', 'disable'
		else:
			return 'False', 'green', 'enable'

	def _get_status(self, channel):
		# return strings for GUI elements:
		# index 0: current value
		# index 1: current color
		curr_val = self.ren_tool.curr_dms.pyDMS_ReadDWSEx(channel + ':Status')

		if curr_val == 0:
			# channel is off
			curr_color = 'green'
		elif curr_val == 1:
			# channel is on => mark it as dangerous!
			curr_color = 'red'
		else:
			curr_color = 'orange'
		return curr_val, curr_color


	def _update_status(self):
		# background task: ask DMS for actual status, update the GUI elements
		for channel in self.channel_dict_of_dicts:
			curr_val, curr_color = self._get_status(channel)
			self.channel_dict_of_dicts[channel]['Status'].config(text=str(curr_val), background=curr_color)

		# update SDriver state
		sdrv_state = self._get_sdriver_state()
		self.sdriver_label.config(text=sdrv_state[0], background=sdrv_state[1])

		self.rootwindow.after(self.BGTASKINTERVAL, self._update_status)


	def _cb_button_activate(self, channel):
		# activate or deactivate this SDriver channel
		is_activated = self.ren_tool.curr_dms.pyDMS_ReadBITEx(channel + ':Activated')

		# invert activation, update all GUI elements
		self.ren_tool.curr_dms.pyDMS_WriteBITEx(channel + ':Activated', not is_activated)

		# ask DMS for actual state (it should represent the changes of the lines above)
		state = self._get_activation(channel)
		self.channel_dict_of_dicts[channel]['Activated'].config(text=state[0], background=state[1])
		## functools.partial() seems to call callback, but that's too early for us... =>exclude this case
		#if 'button' in self.channel_dict_of_dicts[channel]:
		self.channel_dict_of_dicts[channel]['button'].config(text=state[2])


def main(argv=None):

	curr_dms = dms.dmspipe.Dmspipe()
	ren_tool = Renumber_tool(curr_dms)
	ren_tool.collect_comm_dps()
	ren_tool.read_dp_details()

	root_window = RenumberGui(ren_tool)
	root_window.mainloop()

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)