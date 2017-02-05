#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.trendfile.py

Handling and parsing of trendfiles (*.hdb)

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import bisect
import struct
import time

from trend.datasource.dbdata import DBData

DEBUGGING = False


class Trendfile(object):
    TRENDDATA_OFFSET = 1024

    def __init__(self, fileFullpath, collectAll=False):
        self.fileFullpath = fileFullpath
        self.dmsDatapoint = ''
        self.trendDataDict = {}
        self._collectAll = collectAll    # enable collection list of suppressed datapoints (same timestamp!)
        self._suppressedTrenddataList = []
        self._parseFile_()

    def _parseFile_(self):
        # reading binary files:
        # http://stackoverflow.com/questions/1035340/reading-binary-file-in-python-and-looping-over-each-byte

        with open(self.fileFullpath, "rb") as f:
            # read DMS datapoint name
            bytestring = f.read(Trendfile.TRENDDATA_OFFSET)
            if bytestring != "":
                # size of DMS-datapoint is AFAIK max. 80 characters, but simply convert whole bytestring to a usable python string,
                # then treat first NULL char as terminator
                # http://stackoverflow.com/questions/5074043/convert-zero-padded-bytes-to-utf-8-string
                structFormatstring = str(len(bytestring)) + 'c'
                self.dmsDatapoint = b''.join(struct.unpack(structFormatstring, bytestring)).split(b'\0', 1)[0]
                if DEBUGGING:
                    print('found DMS datapoint "' + str(self.dmsDatapoint) + '"\n')

                nofBytesTrendStruct = struct.calcsize(DBData.STRUCT_FORMAT)

                bytestring = f.read(nofBytesTrendStruct)
                while bytestring != "":
                    curr_trenddata = DBData(bytestring)
                    if curr_trenddata.getTimestamp() in self.trendDataDict:
                        if self._collectAll:
                            self._suppressedTrenddataList.append(curr_trenddata)
                        if DEBUGGING:
                            print('WARNING: trend datum with same timestamp already exists... replacing existing trend datum...!\n')
                            print('\told trend datum: "' + str(self.trendDataDict[curr_trenddata.getTimestamp()]) + '"\n')
                            print('\tnew trend datum: "' + str(curr_trenddata) + '"\n')
                    self.trendDataDict[curr_trenddata.getTimestamp()] = curr_trenddata
                    bytestring = f.read(nofBytesTrendStruct)

        if DEBUGGING:
            outputText = ''
            for dictKey in sorted(self.trendDataDict.keys()):
                outputText = outputText + 'found Trenddata: ' + str(self.trendDataDict[dictKey]) + '\n'
            print(outputText)

    def getSuppressedTrenddataList(self):
        """
        returns all suppressed trenddata items (same timestamp already exists) as list of DBData()
        =>activate collection by flag "collectAll"
        """
        return self._suppressedTrenddataList

    def getTrendDataCount(self):
        return len(self.trendDataDict)

    def getFirstTrendData(self):
        dictKey = sorted(self.trendDataDict.keys())[0]
        return self.trendDataDict[dictKey]

    def getLastTrendData(self):
        dictKey = sorted(self.trendDataDict.keys())[-1]
        return self.trendDataDict[dictKey]

    def getdmsDatapoint(self):
        return self.dmsDatapoint

    def getTrendDataFilteredTimestampRanges(self, timestamp_sec_start, timestamp_sec_end, binExpr, minMatchTime_sec=0):
        """ return a list of lists containing timestamps of ranges of matched TrendDataItems according to binary expression with a minimal matching time:
			lists of timestamps: these are keys to TrendData dictionary for direkt access to historical data
			binary expression: "VALUE" is replaced by value of the current TrendDataItem and is evaluated via "eval()" (=>possible security hole!!!)
			Example: get timestamp ranges where temperature is for a minimum of 1h below 15°C:
					getTrendDataFilteredTimestampRanges(<timestamp 1.1.2015>, <timestamp 1.1.2016>, 3600, 'VALUE < -15.0')
		"""
        currItemList = self.getTrendDataItemsList(timestamp_sec_start, timestamp_sec_end)
        currMatchedTimestampLists = []
        if len(currItemList) > 0 and (timestamp_sec_start + minMatchTime_sec <= timestamp_sec_end):
            # we have trenddata items within search range
            currRangeList = []
            currRangeStart = currItemList[0].getTimestamp()
            currRangeDuration = 0
            for item in currItemList:
                binExpr = binExpr.replace('VALUE', str(item.getValue()))
                if eval(binExpr):
                    # filter expression matched ->adding timestamp to temporary List
                    currRangeList.append(item.getTimestamp())
                    currRangeDuration = item.getTimestamp() - currRangeStart
                else:
                    # range of matched items ended... restart search process
                    if currRangeDuration >= minMatchTime_sec:
                        currMatchedTimestampLists.append(currRangeList)
                    currRangeStart = item.getTimestamp()
                    currRangeDuration = 0
                    currRangeList = []
            if currRangeDuration >= minMatchTime_sec:
                currMatchedTimestampLists.append(currRangeList)
        return currMatchedTimestampLists

    def getTrendDataItemsList(self, timestamp_sec_start, timestamp_sec_end):
        currItemList = []
        if timestamp_sec_start <= timestamp_sec_end and (
                        timestamp_sec_start <= self.getLastTrendData().getTimestamp() or timestamp_sec_end >= self.getFirstTrendData().getTimestamp()):
            # right parameter order and we have trends in this timespan...

            for dictKey in sorted(self.trendDataDict.keys()):
                currTimestamp = self.trendDataDict[dictKey].getTimestamp()
                if currTimestamp >= timestamp_sec_start and currTimestamp <= timestamp_sec_end:
                    currItemList.append(self.trendDataDict[dictKey])

        return currItemList

    def getTrendDataValue(self, timestamp_sec, offset=0):
        if timestamp_sec in self.trendDataDict:
            return self.trendDataDict[timestamp_sec].getValue(offset)
        else:
            # we return just the trend datum before this timestamp (interpolation is dangerous: could return wrong values between 0.0 and 1.0 in boolean trend data...)
            if timestamp_sec < self.getFirstTrendData().getTimestamp() or timestamp_sec > self.getLastTrendData().getTimestamp():
                # there's no Trenddata available for this timestamp... how to handle this situation?
                return None
            else:
                # using built-in binary search ( http://stackoverflow.com/questions/2591159/find-next-lower-item-in-a-sorted-list )
                sortedKeyList = sorted(self.trendDataDict.keys())
                index = bisect.bisect_left(sortedKeyList, timestamp_sec) - 1
                dictKey = sortedKeyList[index]
                return self.trendDataDict[dictKey].getValue(offset)


def main(argv=None):
    #for filename in ["D:\Trend\MSR186_Allg_Aussentemp_Istwert.hdb", "D:\Trend\MSR186_Allg_Alarm_Alm01_Output_Alm.hdb",
    #                 "D:\Trend\S0622_G01428_702_T01_C01_P01_U_L1.hdb"]:
    for filename in ['C:\Promos15\proj\Winterthur_MFH_Schaffhauserstrasse\dat\MSR01_Allg_Aussentemp_Istwert.hdb']:
        trf = Trendfile(filename)
        print('Trendfile "' + filename + '" contains ' + str(
            trf.getTrendDataCount()) + ' stored trenddata of DMS datapoint ' + trf.getdmsDatapoint() + '\n')
        print(
        '\t(trending between ' + trf.getFirstTrendData().getTimestampString() + ' and ' + trf.getLastTrendData().getTimestampString() + ')\n')

        # Test: retrieve trenddata value for 'Thu, 05 Nov 2015 09:55:48' (output of following command: >time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(1446713748))
        timeToCheck = 1446713748
        print('Test: retrieving trenddata value for ' + time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(
            timeToCheck)) + ': returned value is "' + str(trf.getTrendDataValue(timeToCheck)) + '"\n')
        print('\n\n')

        print('Test: get values in range\n')
        print('*************************\n')
        testcases = []
        testcases.append(('outside Trend (in past): ', trf.getTrendDataItemsList(0, 1446704963)))
        testcases.append(('outside Trend (in future): ', trf.getTrendDataItemsList(1446743575, 1446743576)))
        testcases.append(('wrong parameter order: ', trf.getTrendDataItemsList(1446743576, 1446743575)))
        testcases.append(('first Trend item: ', trf.getTrendDataItemsList(1446704964, 1446704964)))
        testcases.append(('last Trend item: ', trf.getTrendDataItemsList(1446743574, 1446743574)))
        testcases.append(('first three items: ', trf.getTrendDataItemsList(0, 1446705174)))
        testcases.append(('last three items: ', trf.getTrendDataItemsList(1446743510, 14469999999)))
        testcases.append(('three items in between: ', trf.getTrendDataItemsList(1446706991, 1446707055)))
        testcases.append(('three items in between (again): ', trf.getTrendDataItemsList(1446706991, 1446707055)))
        for currTest in testcases:
            print(currTest[0] + str(len(currTest[1])) + '\t')
            if len(currTest[1]) > 0:
                myStringList = []
                for item in currTest[1]:
                    myStringList.append(str(item.getTimestamp()))
                print('(timestamps: ' + ','.join(myStringList) + ')')
            print('\n')

        currTimestamps = trf.getTrendDataFilteredTimestampRanges(0, 99999999999, 'VALUE > 0 and VALUE < 5', 300)
        print('timestamps filtered with binary expression: =>we found "' + str(len(currTimestamps)) + '" times a matching range')
        for currList in currTimestamps:
            print(str(currList))

        curr_timestamp = 1452050844
        item = trf.trendDataDict[curr_timestamp]
        print('current trenddata: timestamp=' + str(curr_timestamp) + '(' + time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(curr_timestamp)) + ')' +
                 ', value='+str(item.getValue()) + ', status=' + item.getStatusBitsString())
    return 0  # success


if __name__ == '__main__':
    status = main()
    # disable closing of Notepad++
    # sys.exit(status)
