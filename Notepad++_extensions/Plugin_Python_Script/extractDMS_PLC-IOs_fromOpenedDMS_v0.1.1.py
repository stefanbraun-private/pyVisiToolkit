#!/usr/bin/env python
# encoding: utf-8
# (FIXME: problems with german Umlaut when "utf-8" or "windows-1252"... How to do a clean solution?!?)
"""
extractDMS_PLC-IOs_fromOpenedDMS_v0.1.1.py
Export a TAB-separated table with all used PLC ressources

Usage:
******
-open a DMS-file in Notepad++
-run this script via "Erweiterungen" (German) -> "Python script" -> "Scripts"
 (location of scripts: "C:\Users\<USERNAME>\AppData\Roaming\Notepad++\plugins\Config\PythonScript\scripts")
-copy generated table into Microsoft Excel, select all cells with content, under "Daten" choose "Filtern" (German version),

Requirements:
*************
-Notepad++
-"Python Script for Notepad++" (install "FULL"-version from http://npppythonscript.sourceforge.net/download.shtml , installation via Notepad++ plugin manager doesn't work reliable)
  =>using an existing python release is untested
  =>the addon "Notepad++ Python script" has an embedded Python v2.7.x runtime environment (Notepad++ uses Scintilla engine, it's byte-based character manipulation doesn't seem to be Python 3 compatible...)


##############
Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
##############
"""

# Changelog:
# BrS, 04.04.2016 / v0.1.1:	Bugfix: now ignoring DMS-entries like "System:Text:GERMAN:ZW001:", they were handled as regular bmo instances because they have DMS node "NAME"...
# BrS, 14.03.2016 / v0.1: 	little refactoring: put application code into main function
#                         	added some usage hints, code released under GLP version 2
# BrS, 06.01.2016: Bugfix: 	"getListOfRows()" returned multiple PLC ressources in same row
#                         	(Python list datatype needs "deep copy" if you want a real copy of a list, otherwise it's a reference to the SAME list... Now template list is always a new generated list!)
# BrS, 11.12.2015
#
# FIXME: Umlaute-problem ->set LANG in buffer? Or work with Unicode strings and convert them back to UTF8?



# not used:
#import sys


DEBUGGING = False
dmsObjects = {}

class BMOobj:
	"""One Object in DMS"""
	nofObj = 0
	
	# preparation for __str__()
	# (class variables, identical in every instance)
	
	# using string constants for painless index access into list "emptyRowList" (robust and flexible when "titleList" is changed)
	SUBKEY = 'subkey'
	NAME = 'NAME'
	OBJECT = 'OBJECT'
	ESCHEMA = 'ESchema'
	FLAG = 'Flag'
	REGISTER = 'Register'
	DI = 'DI'
	DO = 'DO'
	AI = 'AI'
	AO = 'AO'
	titleList = [SUBKEY, NAME, OBJECT, ESCHEMA, FLAG, REGISTER, DI, DO, AI, AO]
	
	
	def __init__(self):
		self.ESchema = ''
		self.OBJECT = ''
		self.NAME = ''
		self.plcFlags = {}
		self.plcRegs = {}
		self.plcDI = {}
		self.plcDO = {}
		self.plcAI = {}
		self.plcAO = {}
		
		BMOobj.nofObj = BMOobj.nofObj + 1
		
	def setESchema(self, str):
		self.ESchema = str
	
	def setOBJECT(self, str):
		self.OBJECT = str

	def setNAME(self, str):
		self.NAME = str
		
	def insertplcFlag(self, subkey, flag):
		self.plcFlags[subkey] = flag
		
	def insertplcReg(self, subkey, register):
		self.plcRegs[subkey] = register
		
	def insertplcDI(self, subkey, plcDI):
		self.plcDI[subkey] = plcDI
		
	def insertplcDO(self, subkey, plcDO):
		self.plcDO[subkey] = plcDO

	def insertplcAI(self, subkey, plcAI):
		self.plcAI[subkey] = plcAI
		
	def insertplcAO(self, subkey, plcAO):
		self.plcAO[subkey] = plcAO
	
	def __getTemplateRow(self):
		# creating row template (it's values are identical in every row of this BMOobj instance)
		# used in "getListOfRows()"
		self.defaultRowList = len(BMOobj.titleList) * ['']
		self.defaultRowList[BMOobj.titleList.index(BMOobj.NAME)] = self.NAME
		self.defaultRowList[BMOobj.titleList.index(BMOobj.OBJECT)] = self.OBJECT
		self.defaultRowList[BMOobj.titleList.index(BMOobj.ESCHEMA)] = self.ESchema
		return self.defaultRowList
		
	def getListOfRows(self):
		# Return all values of this instance as list of strings
		
		# list of strings (all elements separated by \t)
		self.rows = []
		
		
		for self.flag in self.plcFlags.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.flag
			self.currRowList[BMOobj.titleList.index(BMOobj.FLAG)] = str(self.plcFlags[self.flag])
			self.rows.append('\t'.join(self.currRowList))
			#if DEBUGGING:
			#	console.write('DEBUGGING: plcFlags: self.currRowList is ' + '\t'.join(self.currRowList) + '\n')
		
		for self.reg in self.plcRegs.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.reg
			self.currRowList[BMOobj.titleList.index(BMOobj.REGISTER)] = str(self.plcRegs[self.reg])
			self.rows.append('\t'.join(self.currRowList))

		for self.currDI in self.plcDI.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.currDI
			self.currRowList[BMOobj.titleList.index(BMOobj.DI)] = str(self.plcDI[self.currDI])
			self.rows.append('\t'.join(self.currRowList))
			
		for self.currDO in self.plcDO.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.currDO
			self.currRowList[BMOobj.titleList.index(BMOobj.DO)] = str(self.plcDO[self.currDO])
			self.rows.append('\t'.join(self.currRowList))

		for self.currAI in self.plcAI.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.currAI
			self.currRowList[BMOobj.titleList.index(BMOobj.AI)] = str(self.plcAI[self.currAI])
			self.rows.append('\t'.join(self.currRowList))
			
		for self.currAO in self.plcAO.keys():
			self.currRowList = self.__getTemplateRow()
			self.currRowList[BMOobj.titleList.index(BMOobj.SUBKEY)] = self.currAO
			self.currRowList[BMOobj.titleList.index(BMOobj.AO)] = str(self.plcAO[self.currAO])
			self.rows.append('\t'.join(self.currRowList))

				
			
		# return all rows in one list
		return self.rows

def splitDMSkey(dmsKey):
	# Find the right BMO object and return it's DMS key and the subpart
	if dmsKey.startswith('System:Text:'):
		# ignoring this line...
		return [None, None]
	for bmo in dmsObjects.keys():
		if bmo == dmsKey:
			return [bmo, '']
		elif bmo + ':' in dmsKey:
			subkey = dmsKey[len(bmo)+1:] # "+1" because of ":" between BMO part and subpart
			return [bmo, subkey]
	
	console.write('ERROR: "splitDMSkey(' + dmsKey + ')" did not found the correct BMO object... Is your DMS-file corrupt?!?\n')
			
		

def handle_obj_match(match):
	# store OBJECT
	currObj = BMOobj()
	currObj.setOBJECT(match.group(2))
	dmsObjects[match.group(1)] = currObj

def handle_name_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" has NAME ' + str(match.group(2)) + '\n')
		dmsObjects[bmo].setNAME(str(match.group(2)))
	
def handle_eschema_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" has ESchema ' + str(match.group(2)) + '\n')
		dmsObjects[bmo].setESchema(str(match.group(2)))
	
def handle_flag_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC flag ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcFlag(subkey, str(match.group(2)))

def handle_register_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC register ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcReg(subkey, str(match.group(2)))
	
def handle_plcDI_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC DI ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcDI(subkey, int(match.group(2)))
	
def handle_plcDO_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC DO ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcDO(subkey, str(match.group(2)))
	
def handle_plcAI_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC AI ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcAI(subkey, int(match.group(2)))

def handle_plcAO_match(match):
	bmo, subkey = splitDMSkey(match.group(1))
	if bmo != None and subkey != None:
		if DEBUGGING:
			console.write('BMO "' + bmo + '" uses PLC AO ' + str(match.group(2)) + ' (DMS subkey is "' + subkey + '")\n')
		dmsObjects[bmo].insertplcAO(subkey, int(match.group(2)))
	

	
	
def main(argv=None):
	console.show()

	# get all OBJECTs in DMS
	obj_searchPattern = '(^\w.+):OBJECT;STR;(\w.+);\w+'
	editor.research(obj_searchPattern, handle_obj_match)

	# get all NAMEs in DMS
	name_searchPattern = '(^\w.+):NAME;STR;(\w.+);\w+'
	editor.research(name_searchPattern, handle_name_match)

	# get all ESchema in DMS
	eschema_searchPattern = '(^\w.+):ESchema;STR;(\w.+);\w+'
	editor.research(eschema_searchPattern, handle_eschema_match)

	# get all PLC flags
	flag_searchPattern = '(^\w.+);STR;F\.((\d+)|(\w+));'
	editor.research(flag_searchPattern, handle_flag_match)

	# get all PLC registers
	register_searchPattern = '(^\w.+);STR;R\.((\d+)|(\w+));'
	editor.research(register_searchPattern, handle_register_match)

	# get all PLC DIs
	plcDI_searchPattern = '(^\w.+);STR;I\.(\d+);'
	editor.research(plcDI_searchPattern, handle_plcDI_match)

	# get all PLC DOs
	plcDO_searchPattern = '(^\w.+);STR;O\.(\d+);'
	editor.research(plcDO_searchPattern, handle_plcDO_match)

	# get all PLC AIs
	plcAI_searchPattern = '(^\w.+:Eing);FLT;([0-9]+)\.000000;'
	editor.research(plcAI_searchPattern, handle_plcAI_match)

	# get all PLC AOs
	plcAO_searchPattern = '(^\w.+:StGr_Ausg);FLT;([0-9]+)\.000000;'
	editor.research(plcAO_searchPattern, handle_plcAO_match)

	console.write('\n->Found ' + str(BMOobj.nofObj) + ' BMOs in given DMS-file.\n')

	if BMOobj.titleList != []:
		# table export of all values
		# (first column "PLC" is unknown in BMOobj, that's why we have to add it now)
		exportTable = '\t'.join(['PLC', 'BMO-Key'] + BMOobj.titleList) + '\n'
		
		for bmo in dmsObjects.keys():
			currPlc = bmo.split(':')[0]
			for currRow in dmsObjects[bmo].getListOfRows():
				exportTable = exportTable + '\t'.join([currPlc, bmo, currRow]) + '\n'
		
		notepad.new()
		editor.write(exportTable)
		
		console.write('\nSuccessfully built IO table for ' + str(BMOobj.nofObj) + ' BMOs in given DMS-file. Enjoy! :-)\n')
	else:
		console.write('ERROR: no BMO object in given DMS-file found!\n')
		
	return 0        # success


if __name__ == '__main__':
	status = main()
	# the following line will close Notepad++
	#sys.exit(status)
