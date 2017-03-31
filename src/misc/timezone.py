#!/usr/bin/env python
# encoding: utf-8
"""
timezone.py
provides timezone object for trenddata

Copyright (C) 2017 Stefan Braun

# =>using datetime object with timezone awareness for correct trenddata interpretation
# https://docs.python.org/2/library/datetime.html
# https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
# https://pypi.python.org/pypi/pytz/

######## examples #########
# time jump: summertime to wintertime:
# 2016-10-30 01:46:53     2016-10-30 01:46:53+02:00
# 2016-10-30 02:01:53     2016-10-30 02:01:53+02:00
# 2016-10-30 02:16:53     2016-10-30 02:16:53+02:00
# 2016-10-30 02:31:53     2016-10-30 02:31:53+02:00
# 2016-10-30 02:46:53     2016-10-30 02:46:53+02:00
# 2016-10-30 02:01:53     2016-10-30 02:01:53+01:00
# 2016-10-30 02:16:53     2016-10-30 02:16:53+01:00
# 2016-10-30 02:31:53     2016-10-30 02:31:53+01:00
# 2016-10-30 02:46:53     2016-10-30 02:46:53+01:00
# 2016-10-30 03:01:53     2016-10-30 03:01:53+01:00
# 2016-10-30 03:16:53     2016-10-30 03:16:53+01:00
# 2016-10-30 03:31:53     2016-10-30 03:31:53+01:00
#
# time jump: wintertime to summertime:
# 2017-03-26 00:55:06     2017-03-26 00:55:06+01:00
# 2017-03-26 01:10:06     2017-03-26 01:10:06+01:00
# 2017-03-26 01:25:06     2017-03-26 01:25:06+01:00
# 2017-03-26 01:40:06     2017-03-26 01:40:06+01:00
# 2017-03-26 01:55:06     2017-03-26 01:55:06+01:00
# 2017-03-26 03:10:06     2017-03-26 03:10:06+02:00
# 2017-03-26 03:25:06     2017-03-26 03:25:06+02:00
# 2017-03-26 03:40:06     2017-03-26 03:40:06+02:00
# 2017-03-26 03:55:06     2017-03-26 03:55:06+02:00
# 2017-03-26 04:10:06     2017-03-26 04:10:06+02:00


# different timestamps, same localtime:
# (happens during time change summertime to wintertime)
# timestamp in hex: 0x58153871
# 2016-10-30 02:01:53     2016-10-30 02:01:53+02:00
#
# timestamp in hex: 0x58154681
# 2016-10-30 02:01:53     2016-10-30 02:01:53+01:00

#timedelta calculations
#without awareness:
#2016-10-30 02:01:53 - 2016-10-30 02:01:53 = 0:00:00
#with awareness:
#2016-10-30 02:01:53+01:00 - 2016-10-30 02:01:53+02:00 = 1:00:00





This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import pytz

class Timezone(object):

	# strange.... when using 'Europe/Zurich', then datetime.datetime objects can have
	# wrong timezone offset: tzinfo=<DstTzInfo 'Europe/Zurich' BMT+0:30:00 STD> ?!?!?
	#def __init__(self, tz_database_str='Europe/Zurich'):
	# =>with "Middle European Time" it works as expected... tzinfo=<DstTzInfo 'MET' MET+1:00:00 STD>
	def __init__(self, tz_database_str='MET'):
		self._tz =  pytz.timezone(tz_database_str)

	def get_tz(self):
		return self._tz






def main(argv=None):
	# application code here, like:

	return 0  # success


if __name__ == '__main__':
	status = main()
	# sys.exit(status)