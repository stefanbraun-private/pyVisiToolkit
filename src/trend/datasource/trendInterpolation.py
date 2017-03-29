#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.trendInterpolation.py

Interpolation and interpretation of trenddata search results


Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

DEBUGGING = True

from trend.datasource.trendfile import MetaTrendfile

class Interpolation(object):
	INTERPOLATION_ANALOGUE = 1
	INTERPOLATION_DIGITAL = 2

	def __init__(self, projectpath_str, dms_dp_str, interpolation_type_int):
		self._interpolation_type_int = interpolation_type_int
		self._meta_trf = MetaTrendfile(projectpath_str, dms_dp_str)

	def _get_value(self, timestamp_datetime):
		curr_sr = self._meta_trf.get_DBData_Timestamp_Search_Result(timestamp_datetime)

		# analyzing of search result
		if curr_sr.exact_list:
			# exact search hit
			return self._choose_val_from_list(curr_sr.exact_list)
		else:
			# need to interpolate

	def _choose_val_from_list(self, dbdata_list):


	def _has_trenddata(self, timestamp_datetime):
		first = self._meta_trf.get_first_timestamp()
		last = self._meta_trf.get_last_timestamp()
		return timestamp_datetime >= first and timestamp_datetime <= last

	def get_value_as_boolean(self, timestamp_datetime):
		if self._has_trenddata(timestamp_datetime):
			return self._get_value(timestamp_datetime) > 0.0
		else:
			return None

	def get_value_as_int(self, timestamp_datetime):
		if self._has_trenddata(timestamp_datetime):
			return int(self._get_value(timestamp_datetime))
		else:
			return None

	def get_value_as_float(self, timestamp_datetime):
		if self._has_trenddata(timestamp_datetime):
			return self._get_value(timestamp_datetime)
		else:
			return None


def main(argv=None):
	return 0  # success


if __name__ == '__main__':
	status = main()
