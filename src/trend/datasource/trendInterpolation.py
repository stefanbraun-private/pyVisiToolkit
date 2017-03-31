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
import datetime

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
			return self._calc_val_from_list(curr_sr.exact_list)
		else:
			assert curr_sr.before_list and curr_sr.after_list, 'trenddata in the past and the future expected... does "self._has_trenddata()" work as expected?!?'
			# interpolate between "before_list" and "after_list"
			if self._interpolation_type_int == Interpolation.INTERPOLATION_DIGITAL:
				# binary signal: returning last value
				return self._calc_val_from_list(curr_sr.before_list)
			else:
				# if newer trenddata was stored because of CHANGE, then we return older value (it's a more accurate value)
				statusbit_set = set()
				for item in curr_sr.after_list:
					# collect all used statusbits
					statusbit_set = statusbit_set | item.get_statusbits_set()
				if 'bit1' in statusbit_set:
					# spoiler-alarm: "bit1" means "CHANGE"... =>this way it's possible to use this class without "C:\PyVisiToolkit_DBData_Statusbits.yml"
					return self._calc_val_from_list(curr_sr.before_list)
				else:
					# do linear interpolation
					# delta_Y1 / delta_t1 = delta_Y2 / delta_t2
					# =>delta_Y2 = delta_t2 * delta_Y1 / delta_t1
					val_before = self._calc_val_from_list(curr_sr.before_list)
					tstamp_before = curr_sr.before_list[0].get_datetime()
					val_after = self._calc_val_from_list(curr_sr.after_list)
					tstamp_after = curr_sr.after_list[0].get_datetime()

					timedelta_total = (tstamp_after - tstamp_before).seconds
					timedelta_between = (timestamp_datetime - tstamp_before).seconds
					assert timedelta_total > 0, 'trenddata seems corrupted, we expect a rising timestamp with one second resolution!'
					val_delta = timedelta_between * (val_after - val_before) / timedelta_total
					return val_before + val_delta



	def _calc_val_from_list(self, dbdata_list):
		# it's possible that more than one DBData item have the same timestamp
		# =>averaging values
		if len(dbdata_list) > 1:
			myfunc = lambda x: x.get_value_as_float()
			values_list = map(myfunc, dbdata_list)
			return sum(values_list) / len(values_list)
		else:
			return dbdata_list[0].get_value_as_float()


	def _has_trenddata(self, timestamp_datetime):
		first = self._meta_trf.get_first_timestamp()
		last = self._meta_trf.get_last_timestamp()
		return timestamp_datetime >= first and timestamp_datetime <= last

	def get_value_as_boolean(self, timestamp_datetime):
		if self._has_trenddata(timestamp_datetime):
			# rounding up when average value is 0.5
			return self._get_value(timestamp_datetime) >= 0.5
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


	def _interpolated_values_generator(self, start_datetime, stop_datetime, interval_timedelta):
		# generator for sampled values with given interval
		is_direction_forward = abs(interval_timedelta) == interval_timedelta
		is_time_delta_positiv = start_datetime < stop_datetime
		is_time_delta_negativ = start_datetime > stop_datetime
		assert interval_timedelta != datetime.timedelta(), 'interval_timedelta must contain a value lesser or greater than zero!'
		assert is_direction_forward and is_time_delta_positiv, 'forward mode: stop_datetime is assumed after start_datetime!'
		assert not(is_direction_forward) and is_time_delta_negativ, 'reversed mode: stop_datetime is assumed before start_datetime!'
		curr_time = start_datetime
		if is_direction_forward:
			while curr_time <= stop_datetime:
				curr_time = curr_time + interval_timedelta
				yield self.get_value_as_float(curr_time)
		else:
			while curr_time >= stop_datetime:
				curr_time = curr_time + interval_timedelta
				yield self.get_value_as_float(curr_time)


	def interpolated_booleans_generator(self, start_datetime, stop_datetime, interval_timedelta):
		# generator for sampled values with given interval =>values are booleans
		for value in self._interpolated_values_generator(start_datetime, stop_datetime, interval_timedelta):
			yield value >= 0.5

	def interpolated_integers_generator(self, start_datetime, stop_datetime, interval_timedelta):
		# generator for sampled values with given interval =>values are integers
		for value in self._interpolated_values_generator(start_datetime, stop_datetime, interval_timedelta):
			yield int(value)

	def interpolated_floats_generator(self, start_datetime, stop_datetime, interval_timedelta):
		# generator for sampled values with given interval =>values are floats
		for value in self._interpolated_values_generator(start_datetime, stop_datetime, interval_timedelta):
			yield value


def main(argv=None):
	return 0  # success


if __name__ == '__main__':
	status = main()
