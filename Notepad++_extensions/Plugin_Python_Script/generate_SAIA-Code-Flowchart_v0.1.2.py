#!/usr/bin/env python
# encoding: utf-8
"""
generate_SAIA-Code-Flowchart_v0.1.0.py
Uses Notepad++ and Graphviz for generating flowchart of SAIA Instruction List file (*.src)
-generated Dot-file contains node definitions in HTML (for some syntax-highlighting in generated graphic)
-needs installation of Graphviz (adjust absolute path in PATH_GRAPHVIZ_BINARY to the EXE file)

FIXME: Labels and symbols are case-insensitive... We should implement a workaround for differently written labels
 from Sasm52.chm helpfile: "Symbols can be up to 80 characters long, and are not case-sensitive unless they contain accented characters. MotorOn is the same as MOTORON, but FÜHRER is not the same as führer."


Changelog:
v0.1.2 / 20.03.2017	Bugfix Regex-pattern "RE_LABELS"
v0.1.1 / 11.11.2016	Bugfix Regex-pattern "RE_JUMPS"
v0.1.0 / 29.3.2016	public release


Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import os
import re
from sets import Set

DEBUGGING = True

PATH_GRAPHVIZ_BINARY = r"C:\Program Files (x86)\Graphviz2.38\bin\dot.exe"
PATH_GRAPHVIZ_GV_FILE = r"D:\SAIA-Code-Flowchart.gv"
PATH_GRAPHVIZ_PICTURE_FILE = r"D:\SAIA-Code-Flowchart.png"
#PATH_GRAPHVIZ_PICTURE_FILE = r"D:\SAIA-Code-Flowchart.svg"

class srcFile(object):
	# example block begin:
	#	FB	MOT10	; Motor mit FU (do not change)
	RE_BLOCK_BEGIN = r'^\s*(COB|PB|FB|ST|TR|SB)\s'
	
	# example end block:
	#                  EFB
	RE_BLOCK_END = r'^\s*(ECOB|EPB|EFB|EST|ETR|ESB)\s'
	
	# example jump (could begin with a label!)
	# W12:               JR     END
	#                   JR     L W20
	RE_JUMPS = r'^\s*(([A-Z]|[a-z])([A-Z]|[a-z]|[0-9]|_)+:)*\s*(JR|JPD|JPI)\s+(H|L|P|N|Z|E)*\s*(([A-Z]|[a-z])([A-Z]|[a-z]|[0-9]|_)+)'
	
	# example label (second one is also valid!):
	# NO_BP_EIN:         COPY   RMBP_Verz
	# Cmp14_noHand:
	RE_LABELS = r'^\s*(([A-Z]|[a-z])([A-Z]|[a-z]|[0-9]|_)+):([\s$])'
	
	def __init__(self):
		self._labels = {}
		self._currCodeBlock = self.createBlockObj(0)
		self._codeBlocks = [self._currCodeBlock]
		self._isSkippedLine = False
		self._BlockBeginRegex = re.compile(srcFile.RE_BLOCK_BEGIN)
		self._BlockEndRegex = re.compile(srcFile.RE_BLOCK_END)
		self._JumpsRegex = re.compile(srcFile.RE_JUMPS)
		self._LabelsRegex = re.compile(srcFile.RE_LABELS)
		self._CommentRegex = re.compile(r'^\s*;')
		self._SkipRegex = re.compile(r'^\s*\$SKIP', re.IGNORECASE)
		self._EndSkipRegex = re.compile(r'^\s*\$ENDSKIP', re.IGNORECASE)
		
		self.handleSrcFile()
	
	def handleSrcFile(self):
		# first run: fill dictionary with all labels
		self._isSkippedLine = False
		editor.forEachLine(self._collectLabel)
		
		# second run: put each line into the right codeBlock
		self._isSkippedLine = False
		editor.forEachLine(self._processLine)

	def _checkSkippedLine(self, contents):
		matchSkip = self._SkipRegex.match(contents)
		matchEndSkip = self._EndSkipRegex.match(contents)
		if matchSkip != None:
			self._isSkippedLine = True
		elif matchEndSkip != None:
			self._isSkippedLine = False

	def _collectLabel(self, contents, lineNumber, totalLines):
		self._checkSkippedLine(contents)
		if not self._isSkippedLine:
			# fill dictionary for relation "label -> lineNumber" (used as jump targets and Scintilla "Hotspot" in console window)
			match = self._LabelsRegex.match(contents)
			if match != None:
				myLabel = match.group(1)
				self._labels[myLabel] = lineNumber
	
	
	def _processLine(self, contents, lineNumber, totalLines):
		# process the given line		
		

		self._checkSkippedLine(contents)
		if self._isSkippedLine:
			self._getBlock().addLine(lineNumber, contents, isSkippedLine = True)
		else:
			# do we need further processing?
			matchBegin = self._BlockBeginRegex.match(contents)
			matchLabel = self._LabelsRegex.match(contents)
			matchEnd = self._BlockEndRegex.match(contents)
			matchJump = self._JumpsRegex.match(contents)
			if matchBegin != None or matchLabel != None:
				# begin of new code block => generate new block object, append reference to previous code block
				# (current line will be part of the new block)
				if self._getBlock(lineNumber) == None:
					self._addNewBlock(lineNumber)
				newBlock = self._getBlock(lineNumber)
				self._setCurrentBlock(newBlock)
				self._getBlock(lineNumber - 1).addReference(newBlock)
				self._getBlock().addLine(lineNumber, contents)
			elif matchEnd != None:
				# current line is last line in current block
				# => add line before creating new block
				self._getBlock().addLine(lineNumber, contents)
				if self._getBlock(lineNumber + 1) == None:
					self._addNewBlock(lineNumber + 1)
				newBlock = self._getBlock(lineNumber + 1)
				self._setCurrentBlock(newBlock)
				
				# include reference to next block
				self._getBlock(lineNumber).addReference(newBlock)
			elif matchJump != None:
				#if DEBUGGING:
				#	console.write('found JUMP: source: ' + str(lineNumber) + ', target: ' + matchJump.group(6) + '\n')
				# current line is last line in current block
				# => add line before creating new block
				self._getBlock().addLine(lineNumber, contents)
				if self._getBlock(lineNumber + 1) == None:
					self._addNewBlock(lineNumber + 1)
				newBlock = self._getBlock(lineNumber + 1)
				self._setCurrentBlock(newBlock)
				
				if matchJump.group(5) != None:
					# conditional jump: create reference to target codeBlock AND to the next codeBlock
					# include reference to next block
					self._getBlock(lineNumber).addReference(newBlock)
					#if DEBUGGING:
					#	console.write('matchJump.group(5) = ' + repr(matchJump.group(5)) + '\n')
				
				# include reference to jump target
				try:
					lineNrTarget = self._labels[matchJump.group(6)]
					if self._getBlock(lineNrTarget) == None:
						self._addNewBlock(lineNrTarget)
					self._getBlock(lineNumber).addReference(self._getBlock(lineNrTarget))
				except KeyError:
					console.write('ERROR: found jump-definition, but label "' + matchJump.group(6) + '" is not found!!! Ignoring this reference...\n')
			else:
				# we got a line without any specials
				self._getBlock().addLine(lineNumber, contents)


					
	def _addNewBlock(self, lineNumber):
		newBlock = self.createBlockObj(lineNumber)
		self._codeBlocks.append(newBlock)

	def _setCurrentBlock(self, block):
		self._currCodeBlock = block
		
	def _getBlock(self, lineNumber=-1):
		"""
		return current codeBlock object for appending line,
		or return codeBlock by lineNumber (any lineNumber of this codeBlock will match)
		"""
		if lineNumber < 0:
			return self._currCodeBlock
		else:
			# search for existing block
			for block in self._codeBlocks:
				if block.containsLine(lineNumber):
					return block
			return None

		
	def createBlockObj(self, lineNumber):
		"""
		get a new code block instance
		(override this method when you handle block objects inheritated from codeBlock())
		"""
		return codeBlock(lineNumber)

	def printLabels(self):
		console.write('The following labels were found:\n')
		currFileName = notepad.getCurrentFilename()
		for key in sorted(self._labels):
			# enable clickable result (Scintilla "Hotspot")
			console.editor.setReadOnly(False)
			# Notepad++ starts counting with 0 on Line 1hmm, strange... when clicking on result, then Notepad++ jumps to one line BEFORE right position... =>offset 1
			console.write(currFileName + ':' + str(self._labels[key] + 1) + ':\tLabel "' + key + '"\n')
			

			
			
class codeBlock(object):
	def __init__(self, lineNumber):
		#if DEBUGGING:
		#	console.write('new codeBlock: lineNumber=' + str(lineNumber) + '\n')
		# lines are stored as dictionary with lineNumber as key
		self._lines = {}
		self._lines[lineNumber] = ''
		self._skippedLines = Set()
		self._references = []
		
	def addLine(self, lineNumber, lineStr, isSkippedLine = False):
		if isSkippedLine:
			self._skippedLines.add(lineNumber)
		#if DEBUGGING:
		#	console.write('addLine: (lineNumber, lineStr)==' + repr((lineNumber, lineStr)) + '\n')
		self._lines[int(lineNumber)] = str(lineStr)

	def addReference(self, nextBlock):
		"""
		adds a link to another codeBlock object
		"""
		# append this reference to this block
		#if DEBUGGING:
		#	console.write('addReference(): nextBlock.getFirstline()=' + str(nextBlock.getFirstline()) + '\n')
		if not nextBlock in self._references:
			if nextBlock == self:
				console.write('WARNING: codeBlock starting at line ' + str(self.getFirstline() +1 ) + ' has reference to itself, there seems to be an endless loop in your code!\n')
			self._references.append(nextBlock)
	
	def getFirstline(self):
		"""
		returns the line number where this codeblock starts
		"""
		#if DEBUGGING:
		#	console.write('getFirstline(): self._lines.keys()=' + repr(self._lines.keys()) + '\n')
		return int(min(self._lines.keys()))
		
	def getLastline(self):
		"""
		returns the line number where this codeblock ends
		"""
		return	int(max(self._lines.keys()))
		
	def containsLine(self, lineNumber):
		"""
		check if given line number is in this codeblock
		(we allow "holes" in codeBlock, means not every lineNumber is a key in this dictionary)
		"""
		#if DEBUGGING:
		#	console.write('containsLine(): lineNumber=' + str(lineNumber) + ', self.getFirstline()=' + str(self.getFirstline()) + ', self.getLastline()=' + str(self.getLastline()) + '\n')
		return lineNumber >= self.getFirstline() and lineNumber <= self.getLastline()
		
	def getRefsList(self):
		"""
		returns a list of linked codeBlock objects
		"""
		return self._references

	def getLinesList(self):
		"""
		returns a list of tuples (lineNumber, lineStr)
		"""
		myList = []
		for lineNumber in sorted(self._lines.keys()):
			myList.append((lineNumber, self._lines[lineNumber]))
		return myList
		
	def isSkippedLine(self, lineNumber):
		return lineNumber in self._skippedLines

		
		
class graphCodeTable(codeBlock):
	def __init__(self, lineNumber):
		codeBlock.__init__(self, lineNumber)
		self.structName = 'struct' + str(self.getFirstline())
		
		
	def getGraphvizStruct(self, indent=4):
		myRowList = []
		numOfRows = len(self.getLinesList())
		if numOfRows > 0:
			myRowList.append('\t' + self.structName + ' [label=<')
			myRowList.append('\t' * indent + '<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0">')
			localLineNr = 0
			for lineNumber, currLine in self.getLinesList():
				localLineNr = localLineNr + 1
				#if DEBUGGING:
				#	console.write('numOfRows = ' + str(numOfRows) + ', localLineNr = ' + str(localLineNr) + '\n')
				#	console.write('getGraphvizStruct() raw data: lineNumber, currLine == ' + repr(lineNumber) + ', ' + repr(currLine) + '\n')
				myRowList.append('\t' * (indent + 1) + '<TR>')
				
				## Test: is it necessary to declare a Graphviz port for edge-target? How does a graph look like without it?
				#if localLineNr == 1:
				#	# first row in Graphviz table contains Graphviz connection point
				#	gvPortIn = r' PORT="in"'
				#else:
				#	gvPortIn = ''
				#
				#if localLineNr == numOfRows:
				#	# last row in Graphviz table contains Graphviz connection point
				#	gvportOut = r' PORT="out"'
				#else:
				#	gvportOut = ''
				
				# add offset to lineNumber, because "editor.forEachLine()" counts from 0 and in Notepad++ lineNumber starts with 1
				lineNumberText = getLineNumberStyled('Line ' + str(lineNumber + 1) + ':  ')
				currCellStr = '\t' * (indent + 2) + '<TD>' + lineNumberText + '</TD>'
				#currCellStr = '\t' * (indent + 2) + '<TD' + gvPortIn + '>' + lineNumberText + '</TD>'
				myRowList.append(currCellStr)
					
				
				# treatment of the sourcecode line:
				# 1) remove all trailing whitespace
				# 2) do necessary HTML escaping
				# 3) insert FONT HTML-tag for syntax highlighting
				cellTextStr = getSyntaxHighlighting(html_escape(currLine.rstrip()), self.isSkippedLine(lineNumber))
				currCellStr = '\t' * (indent + 2) + '<TD ALIGN="LEFT">' + cellTextStr + '</TD>'
				#currCellStr = '\t' * (indent + 2) + '<TD' + gvportOut + ' ALIGN="LEFT">' + cellTextStr + '</TD>'
				myRowList.append(currCellStr)
				myRowList.append('\t' * (indent + 1) + '</TR>')
			myRowList.append('\t' * indent + '</TABLE>>];')
		return '\n'.join(myRowList)
		
		
	def getLinks(self, indent=1):
		myLinkList = []
		for item in self.getRefsList():
			if item != None:
				# example of link specification in dot-file:
				# struct1:f1 -> struct2:f8;
				#myStr = '\t' * indent + self.structName + ':out -> ' + item.structName + ':in;'
				
				# new idea: struct1 -> struct2;
				# (this allows oneline-codeBlocks and should have a more linear node placement in graph
				myStr = '\t' * indent + self.structName + ' -> ' + item.structName + ';'
				myLinkList.append(myStr)
			else:
				console.write('BUG: None-Block as reference?!?\n')
		return '\n'.join(myLinkList)
		
		
class graphFile(srcFile):
	def __init__(self, gvFile):
		self._gvFile = gvFile
		srcFile.__init__(self)
	
	def createBlockObj(self, lineNumber):
		"""
		get a new code block instance
		"""
		return graphCodeTable(lineNumber)
	
	def _getNodeRankString(self, block, rankStr):
		return '{rank=' + str(rankStr) + block.structName + '}'
		
	
	def generateGraphvizFile(self):
		self._gvFile.write('digraph structs {\n')
		# using Windows font ""Courier New" (it's a monospace font, then generated image is similar to sourcecode in Notepad++ =>we need to simulate tabulator in Graphviz HTML-labels with spaces...)
		self._gvFile.write('	node [shape=plaintext fontname="Courier New"]\n')
		structStringList = []
		linkStringList = []
		for item in self._codeBlocks:
			structStringList.append(item.getGraphvizStruct())
			linkStringList.append(item.getLinks())
		self._gvFile.write('\n'.join(structStringList) + '\n')
		self._gvFile.write('\n'.join(linkStringList) + '\n')
		
		# setting "rank" attribute for start and end codeBlock
		# example: 	{rank=source struct0}
		#			{rank=sink struct88}
		self._gvFile.write(self._getNodeRankString(self._codeBlocks[0], 'source') + '\n')
		self._gvFile.write(self._getNodeRankString(self._codeBlocks[-1], 'sink') + '\n')
		
		self._gvFile.write('}\n')

		
# HTML escaping:
# example from https://wiki.python.org/moin/EscapingHtml
# (added work-around for '\t', because Graphviz ignores tabulator in HTML labels)
html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
    "\t": " " * 4
    }

def html_escape(text):
    """Produce entities within text."""
    return "".join(html_escape_table.get(c,c) for c in text)

def getLineNumberStyled(lineNumberText):
	# reduce fontsize, set italic style (improve readability)
	return '<FONT POINT-SIZE="9"><I>' + lineNumberText + '</I></FONT>'
	
def getSyntaxHighlighting(cellTextStr, isSkippedLine):
	# do syntax highlighting (improve readability)
	# (color names: http://www.graphviz.org/doc/info/colors.html )
	if cellTextStr == '':
		return ''
	elif isSkippedLine:
		# $SKIP: whole text is green
		return '<FONT COLOR="darkgreen">' + cellTextStr + '</FONT>'
	elif ';' in cellTextStr:
		# comment is green
		pos = cellTextStr.index(';')
		commented = cellTextStr[pos:]
		uncommented = _getReservedWordsStyled(cellTextStr[:pos])
		return uncommented + '<FONT COLOR="darkgreen">' + commented + '</FONT>'
	else:
		# styling of reserved words if there are some
		return _getReservedWordsStyled(cellTextStr)

def _getReservedWordsStyled(codeLineStr):
	# searches for many SAIA reserved words (improving readability)
	# returns text with HTML tag around reserved word
	#
	# FIXME: it's oversimplified and a dirty hack, it would be cool to copy the syntax highlighting of the opened src file...
	#	( e.g. function "Editor.getStyleAt(pos)" in Notepad++ Python Script, http://npppythonscript.sourceforge.net/docs/latest/scintilla.html )
	
	# match assembler directives (e.g. $IFNDEF, $PCDVER, ...)
	# =>color red, style italic
	# assumption: there's no other reserved word in this line
	myRegex = re.compile(r'(.*)(\$[A-Z]+)(\s.*)')
	dirMatch = myRegex.match(codeLineStr)
	if dirMatch != None:
		return dirMatch.group(1) + '<FONT COLOR="red"><I>' + dirMatch.group(2) + '</I></FONT>' + dirMatch.group(3)
	
	# match keywords (e.g. SETH, ANL, ....)
	# =>color blue, style bold
	# assumption: there's no other reserved word in this line
	myRegex = re.compile(r'(.*)(STH|STHX|STL|ANH|ANL|ORH|ORL|XOR|ACC|DYN|OUT|OUTX|SET|RES|COM|SETD|RESD|LD|LDL|LDH|INC|DEC|MOV|COPY|GET|PUT|TFR|TFRI|BITI|BITIR|BITO|BITOR|DIGI|DIGIR|DIGO|DIGOR|AND|OR|EXOR|NOT|SHIU|SHID|ROTU|ROTD|SHIL|SHIR|ROTL|ROTR|SEI|INI|DEI|STI|RSI|ADD|SUB|MUL|DIV|SQR|CMP|IFP|FPI|FADD|FSUB|FMUL|FDIV|FSQR|FCMP|FSIN|FCOS|FATAN|FEXP|FLN|FABS)(\s.*)')
	keywMatch = myRegex.match(codeLineStr)
	if keywMatch != None:
		return keywMatch.group(1) + '<FONT COLOR="blue"><B>' + keywMatch.group(2) + '</B></FONT>' + keywMatch.group(3)

	# no reserved word found
	return codeLineStr
	
	
	
	
def main(argv=None):
	
	console.show()
	console.write('generate_SAIA-Code-Flowchart.py\n')
	
	with open(PATH_GRAPHVIZ_GV_FILE, 'w') as f:
		currFile = graphFile(f)
		currFile.printLabels()
		console.write('generate Graphviz File "' + PATH_GRAPHVIZ_GV_FILE + '"...\n')
		currFile.generateGraphvizFile()
		console.write('Done. Generate Windows batch file...\n')
		gvFileType = PATH_GRAPHVIZ_PICTURE_FILE.split('.')[-1]
		#execCommand = '"' + PATH_GRAPHVIZ_BINARY + '" -x -Goverlap=prism -T' + gvFileType + ' ' + PATH_GRAPHVIZ_GV_FILE + ' -Gcharset=latin1 -v -o ' + PATH_GRAPHVIZ_PICTURE_FILE
		#execCommand = '"' + PATH_GRAPHVIZ_BINARY + '" -T' + gvFileType + ' ' + PATH_GRAPHVIZ_GV_FILE + ' -Gcharset=latin1 -v -o ' + PATH_GRAPHVIZ_PICTURE_FILE
		execCommand = '"' + PATH_GRAPHVIZ_BINARY + '" -T' + gvFileType + ' ' + PATH_GRAPHVIZ_GV_FILE + ' -Gcharset=latin1 -v -o ' + PATH_GRAPHVIZ_PICTURE_FILE
	
	with open(PATH_GRAPHVIZ_GV_FILE + '.bat', 'w') as f:
		f.write('@echo off\n')
		f.write('echo *** Generate Graphviz graph as PNG image ***\n')
		f.write('echo (this Windows batch file is generated by "generate_SAIA-Code-Flowchart.py"\n')
		f.write('echo ********************************************\n')
		f.write('echo .\n')
		f.write('@echo on\n')
		f.write(execCommand + '\n')
		f.write('@echo off\n')
		f.write('echo .\n')
		f.write('echo .\n')
		f.write('echo Your SAIA-Code-Flowchart should be in file "' + PATH_GRAPHVIZ_PICTURE_FILE + '"\n')
		f.write('echo .\n')
		f.write('pause')
	console.write('Please execute Windows batch file "' + PATH_GRAPHVIZ_GV_FILE + '.bat' + '" for Image generation!\n')
	console.write('End of "generate_SAIA-Code-Flowchart.py".\n\n')
	
	
	return 0        # success


if __name__ == '__main__':
	status = main()
	# don't close Notepad++ after program execution...
	#sys.exit(status)