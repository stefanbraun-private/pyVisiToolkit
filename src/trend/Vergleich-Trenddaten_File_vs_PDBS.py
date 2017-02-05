#!/usr/bin/env python
# encoding: utf-8
"""
trend.datasource.Vergleich-Trenddaten_File_vs_PDBS.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



"""
Beobachtung:
-Trendgenerator findet bei "Messkoffer01:TEMP:TF07:Messung:Istwert" total 1709 Datensätze
-resultierte CSV-Datei enthält 1278 Datensätze
-Zeitraum Anfang: 18.2.2016 00:00 Uhr (Unix-Zeitstempel Lokalzeit 1455750000s)
-Zeitraum Ende: 19.2.2016 00:00 Uhr (Unix-Zeitstempel 1455836400s )
=>welche Datensätze hat uns PDBS vorenthalten? Analyse der Rohdaten.
"""

from trend.datasource import trendfile as trf
from trend.datasource import pdbs as pdbs
import time

def main(argv=None):

	timestampStart = 1455750000
	timestampEnd = 1455836400

	filename_export_backup_suppressed_str = r'D:\from_backupfile_suppressed.csv'
	filename_export_backup_trendfile_str = r'D:\from_backupfile.csv'
	filename_export_suppressed_str = r'D:\from_dat_suppressed.csv'
	filename_export_trendfile_str = r'D:\from_dat.csv'
	filename_export_pdbs_str = r'D:\from_PDBS.csv'

	# Example: Write into textfile: http://stackoverflow.com/questions/5214578/python-print-string-to-text-file


	###################### trenddata from Visi.Plus PDBS service ##################
	print('\n*** getting Trenddata from Visi.Plus PDBS-service ***')
	dmsDpName = 'Messkoffer01:TEMP:TF07:Messung:Istwert'
	currPdbs = pdbs.Pdbs()
	nofDps = currPdbs.pyPdbsGetCount(dmsDpName, timestampStart, timestampEnd)

	print('Writing "official" Visi.Plus PDBS datapoints into file "' + filename_export_pdbs_str + '"' )
	print('\t(according to PDBS-service there are ' + str(nofDps) + ' trenddata items for DMS key "' + dmsDpName + '"')
	nofWrites = 0
	with open(filename_export_pdbs_str, "w") as text_file:
		for item in currPdbs.pyPdbsGetData(dmsDpName, timestampStart, timestampEnd, nofDps):
			timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.getTimestamp()))
			value = item.getValue()
			status = item._status & 0xFF    # ignoring Backup-Flag (this is set in *.hdb-files)
			text_file.write("%s;%.1f;%i\n" % (timestamp, value, status))
			nofWrites = nofWrites + 1
	print('\t(retrieved ' + str(nofWrites) + ' trenddata items from PDBS and wrote them to file)')
	print('\tDone.')


	trdFilename = r'C:\Promos16\proj\Asenta_Messkoffer_01\dat\Messkoffer01_TEMP_TF07_Messung_Istwert.hdb'
	print('\n*** getting Trenddata from raw file (Visi.Plus Dat-directory) "' + trdFilename + '"')
	currTrf = trf.Trendfile(trdFilename, collectAll=True)

	###################### raw trenddata from file ##################
	print('Writing raw datapoints into file "' + filename_export_trendfile_str + '"' )
	nofWrites = 0
	with open(filename_export_trendfile_str, "w") as text_file:
		for item in currTrf.getTrendDataItemsList(timestampStart, timestampEnd):
			timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.getTimestamp()))
			value = item.getValue()
			status = item._status & 0xFF    # ignoring Backup-Flag (this is set in *.hdb-files)
			text_file.write("%s;%.1f;%i\n" % (timestamp, value, status))
			nofWrites = nofWrites + 1
	print('\t(there exists ' + str(len(currTrf.getTrendDataItemsList(timestampStart, timestampEnd))) + ' trenddata items)')
	print('\t(wrote ' + str(nofWrites) + ' trenddata items)')
	print('\tDone.')

	###################### suppressed raw trenddata from file ##################
	print('Writing suppressed datapoints into file "' + filename_export_suppressed_str + '"' )
	suppressed_trd_from_file = []
	for item in currTrf.getSuppressedTrenddataList():
		if (item.getTimestamp() >= timestampStart) and (item.getTimestamp() <= timestampEnd):
			suppressed_trd_from_file.append(item)

	nofWrites = 0
	with open(filename_export_suppressed_str, "w") as text_file:
		for item in suppressed_trd_from_file:
			timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.getTimestamp()))
			value = item.getValue()
			status = item._status & 0xFF    # ignoring Backup-Flag (this is set in *.hdb-files)
			text_file.write("%s;%.1f;%i\n" % (timestamp, value, status))
			nofWrites = nofWrites + 1
	print('\t(there exists ' + str(len(suppressed_trd_from_file)) + ' trenddata items)')
	print('\t(wrote ' + str(nofWrites) + ' trenddata items)')
	print('\tDone.')



	trdFilename = r'D:\Trenddaten\Month_02.2016\Messkoffer01_TEMP_TF07_Messung_Istwert.hdb'
	print('\n*** getting Trenddata from raw file (backup) "' + trdFilename + '"')
	currTrf = trf.Trendfile(trdFilename, collectAll=True)

	###################### raw trenddata from file ##################
	print('Writing raw datapoints into file "' + filename_export_backup_trendfile_str + '"' )
	nofWrites = 0
	with open(filename_export_backup_trendfile_str, "w") as text_file:
		for item in currTrf.getTrendDataItemsList(timestampStart, timestampEnd):
			timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.getTimestamp()))
			value = item.getValue()
			status = item._status & 0xFF    # ignoring Backup-Flag (this is set in *.hdb-files)
			text_file.write("%s;%.1f;%i\n" % (timestamp, value, status))
			nofWrites = nofWrites + 1
	print('\t(there exists ' + str(len(currTrf.getTrendDataItemsList(timestampStart, timestampEnd))) + ' trenddata items)')
	print('\t(wrote ' + str(nofWrites) + ' trenddata items)')
	print('\tDone.')


	###################### suppressed raw trenddata from file ##################
	print('Writing suppressed datapoints into file "' + filename_export_backup_suppressed_str + '"' )
	suppressed_trd_from_file = []
	for item in currTrf.getSuppressedTrenddataList():
		if (item.getTimestamp() >= timestampStart) and (item.getTimestamp() <= timestampEnd):
			suppressed_trd_from_file.append(item)

	nofWrites = 0
	with open(filename_export_backup_suppressed_str, "w") as text_file:
		for item in suppressed_trd_from_file:
			timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.getTimestamp()))
			value = item.getValue()
			status = item._status & 0xFF    # ignoring Backup-Flag (this is set in *.hdb-files)
			text_file.write("%s;%.1f;%i\n" % (timestamp, value, status))
			nofWrites = nofWrites + 1
	print('\t(there exists ' + str(len(suppressed_trd_from_file)) + ' trenddata items)')
	print('\t(wrote ' + str(nofWrites) + ' trenddata items)')
	print('\tDone.')


	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)