#!/usr/bin/env python
# encoding: utf-8
"""
setup_py2exe_DMS_tracer.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

from distutils.core import setup
import py2exe
import dms.dmspipe
import dms.datapoint
import argparse
import time
from datetime import datetime

# some help from
# http://stackoverflow.com/questions/5811960/is-there-a-way-to-specify-the-build-directory-for-py2exe
# http://www.py2exe.org/index.cgi/ListOfOptions

options = {'py2exe': {
           'dist_dir': r'..\py2exe_output\DMS_tracer'
           }}
		   
setup(console=[r'tools\DMS_tracer.py'], options=options)