#!/usr/bin/env python
# encoding: utf-8
"""
trend.plot-TEST.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


# based on example from http://matplotlib.org/1.2.1/examples/api/histogram_demo.html

"""
Make a histogram of normally distributed random numbers and plot the
analytic PDF over it
"""
import array

import matplotlib.pyplot as plt

from trend.datasource import trendfile as trf


def main(argv=None):

    currTrf = trf.RawTrendfile("D:\Trend\S0622_G01428_702_T01_C01_P01_U_L1.hdb")

    # create float array
    myArr = array.array('f')
    timestampStart = currTrf.getFirstTrendData().getTimestamp()
    timestampEnd = currTrf.getLastTrendData().getTimestamp()
    for item in currTrf.getTrendDataItemsList(timestampStart, timestampEnd):
        myArr.append(item.getValue() )

    fig = plt.figure()
    ax = fig.add_subplot(111)

    # the histogram of the data
    n, bins, patches = ax.hist(myArr, 50, normed=1, facecolor='green')

    # hist uses np.histogram under the hood to create 'n' and 'bins'.
    # np.histogram returns the bin edges, so there will be 50 probability
    # density values in n, 51 bin edges in bins and 50 patches.  To get
    # everything lined up, we'll compute the bin centers
    bincenters = 0.5*(bins[1:]+bins[:-1])

    ax.set_xlabel(currTrf.getdmsDatapoint() + ' [V]')
    ax.set_ylabel('Probability')
    ax.set_xlim(225, 240)
    ax.set_ylim(0, 0.6)
    ax.grid(True)



    plt.show()

    return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)