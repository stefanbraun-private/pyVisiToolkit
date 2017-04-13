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
import collections
import sys


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

		class _TStamp_iter_source(object):
			"""helper class for timestamp generators"""
			def __init__(self, head_elem, iterator):
				self.head_elem = head_elem
				self.iterator = iterator

		tstamp_generator_list = []
		for var in self._variables_list:
			try:
				curr_iter = var.get_interpolation().get_dbdata_timestamps_generator(start_datetime, stop_datetime)
				# this object always contains head element from iterator, and iterator itself
				new_source = _TStamp_iter_source(curr_iter.next(), curr_iter)
				tstamp_generator_list.append(new_source)
			except StopIteration:
				pass

		# request items from all generators, always returning smaller value
		while tstamp_generator_list:
			# consuming timestamps, returning always oldest one, updating first element
			# sorting list of tuples: http://stackoverflow.com/questions/10695139/sort-a-list-of-tuples-by-2nd-item-integer-value
			# =>getting source list with oldest timestamp
			key_func = lambda tstamp_iter_source: tstamp_iter_source.head_elem.tstamp_dt
			tstamp_generator_list = sorted(tstamp_generator_list, key=key_func)
			oldest_source_obj = tstamp_generator_list[0]
			curr_tstamp_obj = oldest_source_obj.head_elem
			yield curr_tstamp_obj
			try:
				# update head-element of current timestamp source
				oldest_source_obj.head_elem = oldest_source_obj.iterator.next()
			except StopIteration:
				# iterator is empty... =>removing this timestamp-source
				tstamp_generator_list = tstamp_generator_list[1:]


	def get_evaluation_generator(self, binary_expr_str, start_datetime=None, stop_datetime=None):
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
			tstamp_obj.age = curr_age

			# evaluate given expression with current variable values
			try:
				# calling eval() mostly safe (according to http://lybniz2.sourceforge.net/safeeval.html )
				tstamp_obj.value = eval(binary_expr_str, {}, mylocals)
			except Exception as ex:
				# current expression contains errors...
				print('\tExpression.get_evaluation_generator() throwed exception during evaluation: "' + repr(ex) + '"')
				tstamp_obj.value = None
			yield tstamp_obj


	def get_timespans_while_eval_true_generator(self, binary_expr_str, start_datetime=None, stop_datetime=None, duration_seconds=300, max_age_seconds=900):
		"""
		evaluate given expression at every available timestamp,
		yields Timespan objects containing begin and end timestamp,
		when this expression evaluates to True during specific amount of seconds as minimal duration
		and all available values are "fresher" than given max_age_seconds
		(=>caller has to iterate himself over these timespans;
		we got "MemoryError"s when trying to collect lists of all available timestamps)
		"""

		assert duration_seconds >= 0, 'parameter "duration_seconds" has to be a positive integer'
		assert max_age_seconds > 0, 'sane values of maximal age: a bit higher than maximum interval of all involved variables'

		class _Timespan(object):
			def __init__(self, start_datetime):
				self.start_datetime = start_datetime
				self.stop_datetime = None
				self.nof_tstamps = 0

		curr_timespan = None
		for tstamp_obj in self.get_evaluation_generator(binary_expr_str, start_datetime, stop_datetime):
			if tstamp_obj.value and tstamp_obj.age <= max_age_seconds:
				# expression evaluates to True and is "fresh"
				if not curr_timespan:
					# =>begin of new list
					curr_timespan = _Timespan(tstamp_obj.tstamp_dt)
				curr_timespan.nof_tstamps += 1
			else:
				# expression evaluates to False =>return last Timespan object, reset everything
				if curr_timespan:
					curr_duration = abs((curr_timespan.start_datetime - tstamp_obj.tstamp_dt).total_seconds())
					if curr_duration >= duration_seconds:
						# found timespan where expression evaluates long enough to True
						# =>save it for caller
						curr_timespan.stop_datetime = tstamp_obj.tstamp_dt
						yield curr_timespan
					curr_timespan = None


	def get_value_of_variable(self, var_name_str, timestamp_datetime):
		"""retrieving interpolated value of given variable at given timestamp"""

		# searching variable
		for var in self._variables_list:
			if var._var_name_str == var_name_str:
				return var.get_value(timestamp_datetime)
		raise AttributeError('variable "' + var_name_str + '" is unknown to current expression object!')



def main(argv=None):
	curr_tz = timezone.Timezone().get_tz()

	# evaluate expression over trenddata
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
			binary_expr_str='AT > 0.0 and UWP',
			start_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=0, tzinfo=curr_tz),
			stop_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=10, tzinfo=curr_tz),
	):
		print(str(tstamp_obj.tstamp_dt) + ': expression is ' + str(tstamp_obj.value) + ', highest age in seconds: ' + str(tstamp_obj.age))




	# search in trenddata for timeperiods where expression is True
	with open(r'd:\output_timespans_while_eval_true.txt', 'w') as f:
		f.write('\t'.join(['timestamp', 'AT', 'UWP']) + '\n')
		for curr_timespan in curr_expr.get_timespans_while_eval_true_generator(
			binary_expr_str='AT > 0.0 and UWP',
			start_datetime=datetime.datetime(year=2017, month=2, day=1, hour=0, minute=0, tzinfo=curr_tz),
			stop_datetime=datetime.datetime(year=2017, month=2, day=6, hour=0, minute=0, tzinfo=curr_tz),
			duration_seconds=3600
		):
			print('\n' + '*' * 10)
			print('\tfound timespan where expression evaluates to True for more than one hour:')
			print('\tstart: ' + str(curr_timespan.start_datetime))
			print('\tstop: ' + str(curr_timespan.stop_datetime))
			print('\tnumber of timestamps: ' + str(curr_timespan.nof_tstamps))

			# FIXME: the following code doesn't run to the end because of "MemoryError" exception... =>refactoring of trendfile.py needed!!!
			for tstamp_obj in curr_expr._get_timestamps_generator(
					start_datetime=curr_timespan.start_datetime,
					stop_datetime=curr_timespan.stop_datetime
			):
				value1_str = str(curr_expr.get_value_of_variable('AT', tstamp_obj.tstamp_dt))
				value2_str = str(curr_expr.get_value_of_variable('UWP', tstamp_obj.tstamp_dt))
				f.write('\t'.join([str(tstamp_obj.tstamp_dt), value1_str, value2_str]) + '\n')

	return 0  # success


if __name__ == '__main__':
	status = main()
