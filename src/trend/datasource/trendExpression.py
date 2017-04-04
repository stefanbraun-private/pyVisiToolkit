#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.trendExpression.py

Evaluate trenddata expressions


Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

DEBUGGING = True

import datetime
import misc.timezone as timezone
from trend.datasource.trendInterpolation import Interpolation
from operator import itemgetter


class Variable(object):
	TYPE_BOOLEAN = 1
	TYPE_INTEGER = 2
	TYPE_FLOAT = 3

	def __init__(self, projectpath_str, dms_dp_str, var_name_str, interpolation_type_int, value_type_int):
		self._interpolation = Interpolation(projectpath_str, dms_dp_str, interpolation_type_int)
		self._var_name_str = var_name_str
		self._value_type_int = value_type_int

	def get_interpolation(self):
		return self._interpolation

	def get_var_name(self):
		return self._var_name_str

	def get_value(self, timestamp_datetime):
		if self._value_type_int == Variable.TYPE_BOOLEAN:
			return self._interpolation.get_value_as_boolean(timestamp_datetime)
		elif self._value_type_int == Variable.TYPE_INTEGER:
			return self._interpolation.get_value_as_int(timestamp_datetime)
		else:
			# default: returning float
			return self._interpolation.get_value_as_float(timestamp_datetime)

	def get_age(self, timestamp_datetime):
		# difference between given timestamp and last available trenddata timestamp in seconds
		# =>this "freshness" shows holes in trenddata
		return self._interpolation.get_age(timestamp_datetime)


class Expression(object):
	_tz = timezone.Timezone().get_tz()

	def __init__(self, variables_list):
		self._variables_list = variables_list

	def _get_timestamps_generator(self, start_datetime=None, stop_datetime=None):
		"""
		getting generators of all timestamp sources,
		then always yield the oldest timestamp of all active timestamp sources
		=>this allows comparison of values of all involved variables at all available timestamps
		"""
		# FIXME: some code sharing with MetaTrendfile.get_dbdata_timestamps_generator()... =>refactor if possible!

		if not start_datetime:
			start_datetime = datetime.datetime.fromtimestamp(0, tz=Expression._tz)
		if not stop_datetime:
			stop_datetime = datetime.datetime(year=3000, month=1, day=1).replace(tzinfo=Expression._tz)

		tstamp_generator_list = []
		for var in self._variables_list:
			try:
				source = var.get_interpolation().get_dbdata_timestamps_generator(start_datetime, stop_datetime)
				# this list always contains head element from iterator, and iterator itself
				new_source = [source.next(), source]
				tstamp_generator_list.append(new_source)
			except StopIteration:
				pass

		# request items from all generators, always returning smaller value
		while tstamp_generator_list:
			# consuming timestamps, returning always oldest one, updating first element
			# sorting list of tuples: http://stackoverflow.com/questions/10695139/sort-a-list-of-tuples-by-2nd-item-integer-value
			# =>getting source list with oldest timestamp
			tstamp_generator_list = sorted(tstamp_generator_list, key=itemgetter(0))
			oldest_source_list = tstamp_generator_list[0]
			curr_tstamp, curr_iter = oldest_source_list[0], oldest_source_list[1]
			yield curr_tstamp
			try:
				# update head-element of current timestamp source
				oldest_source_list[0] = curr_iter.next()
			except StopIteration:
				# iterator is empty... =>removing this timestamp-source
				tstamp_generator_list = tstamp_generator_list[1:]


	def get_evaluation_generator(self, expr_str, start_datetime=None, stop_datetime=None):
		"""
		evaluate given expression at every available timestamp
		"""

		if not start_datetime:
			start_datetime = datetime.datetime.fromtimestamp(0, tz=Expression._tz)
		if not stop_datetime:
			stop_datetime = datetime.datetime(year=3000, month=1, day=1).replace(tzinfo=Expression._tz)

		# looping through all available timestamps
		for tstamp_obj in self._get_timestamps_generator(start_datetime, stop_datetime):

			# set test condition for eval(): building local variables dictionary with all values
			# updating "age" as maximum of "age" of all variables (higher means less relevant)
			curr_age = 0
			mylocals = {}
			for curr_var in self._variables_list:
				var_name = curr_var.get_var_name()
				curr_val = curr_var.get_value(tstamp_obj.tstamp_dt)
				mylocals[var_name] = curr_val
				curr_age = max(curr_age, curr_var.get_age(tstamp_obj.tstamp_dt))

			# evaluate given expression with current variable values
			try:
				# calling eval() mostly safe (according to http://lybniz2.sourceforge.net/safeeval.html )
				tstamp_obj.value = eval(expr_str, {}, mylocals)
			except Exception as ex:
				# current expression contains errors...
				print('\tExpression.get_evaluation_generator() throwed exception during evaluation: "' + repr(ex) + '"')
				tstamp_obj.value = None
			yield tstamp_obj



def main(argv=None):
	curr_tz = timezone.Timezone().get_tz()

	my_vars_list = []
	my_vars_list.append(Variable(projectpath_str='C:\Promos15\proj\Foo',
	                             dms_dp_str='NS_MSR01a:H01:AussenTemp:Istwert',
	                             var_name_str='AT',
	                             interpolation_type_int=Interpolation.INTERPOLATION_ANALOG,
	                             value_type_int=Variable.TYPE_FLOAT))

	my_vars_list.append(Variable(projectpath_str='C:\Promos15\proj\Foo',
	                             dms_dp_str='NS_MSR01a:H01:VerdUwp:RM_Ein',
	                             var_name_str='UWP',
	                             interpolation_type_int=Interpolation.INTERPOLATION_DIGITAL,
	                             value_type_int=Variable.TYPE_BOOLEAN))

	curr_expr = Expression(my_vars_list)

	for tstamp_obj in curr_expr.get_evaluation_generator(
			expr_str='AT > 0.0 and UWP',
			start_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=0, tzinfo=curr_tz),
			stop_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=10, tzinfo=curr_tz),
	):
		print(str(tstamp_obj.tstamp_dt) + ': expression is ' + str(tstamp_obj.value) + ', highest age in seconds: ' + str(tstamp_obj.age))

	return 0  # success


if __name__ == '__main__':
	status = main()
