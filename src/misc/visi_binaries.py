#!/usr/bin/env python
# encoding: utf-8
"""
misc.visi_binaries.py
search location of Visi.Plus(c) binaries for allowing loading dmspipe/pdbs DLLs

Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

#import sys
import subprocess
import os

DEBUGGING = False
DMS_FILENAME = u'dms.exe'

def _search_tasklist():
	# first try: search executable in currently executed tasks
	# help from http://stackoverflow.com/questions/3429250/determining-running-programs-in-python
	# remark: WMI command-line (WMIC) utility works on Windows >Vista and Server >2008
	#  (according to https://msdn.microsoft.com/en-us/library/windows/desktop/aa394531(v=vs.85).aspx )
	# =>following command gives wrong info: 'WMIC PROCESS get Commandline'
	#  because Visi.Plus(c) >=v1.6 DMS.exe has no more fullpath in attribute "Commandline"...
	# help from http://superuser.com/questions/768984/show-exe-file-path-of-running-processes-on-the-command-line-in-windows
	cmd = 'WMIC PROCESS get ExecutablePath'
	proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
	for line in proc.stdout:
		if DMS_FILENAME in line:
			if DEBUGGING:
				print(u'_search_tasklist(): current path of DMS: ' + line)
			return line
	return None

def _search_usual_locations():
	# fallback: in case DMS is not running, search at usual locations:
	# (search order is from left to right)
	DIRECTORIES = ['c:\\PromosNT', 'c:\\Promos17', 'c:\\Promos16', 'c:\\Promos15']
	BIN_FOLDER = 'bin'
	for directory in DIRECTORIES:
		# FIXME: os.path.join() doesn't work in every case... is there a better way?
		# http://stackoverflow.com/questions/2422798/python-os-path-join-on-windows
		filename = os.path.join(directory, BIN_FOLDER, DMS_FILENAME)
		if os.path.isfile(filename):
			return filename
	return None

def get_fullpath(name_of_binary=u''):
	'''
	return fullpath of Visi.Plus(c) binaries,
	currently running instance is prefered over other installations
	=>optional argument allows getting fullpath for one specific binary
	'''

	# go through all binary-path-detection-possibilities
	PATH_FUNCTIONS = [_search_tasklist, _search_usual_locations]

	for curr_func in PATH_FUNCTIONS:
		dms_path = curr_func()
		# using first usable result
		if dms_path:
			bin_path = os.path.split(dms_path)[0]
			if name_of_binary:
				# FIXME: why does the following "clean" solution doesn't work?!? Now we just replace strings...
				# exception is "AttributeError: 'list' object has no attribute 'replace'"
				#return os.path.join([bin_path, name_of_binary])
				return dms_path.replace(DMS_FILENAME, name_of_binary)
			else:
				return bin_path

def main(argv=None):
	print('with argument "test.exe": ' + get_fullpath('test.exe'))
	print('without argument: ' + get_fullpath())

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)