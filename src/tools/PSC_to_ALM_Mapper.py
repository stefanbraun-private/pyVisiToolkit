#!/usr/bin/env python
# encoding: utf-8
"""
tools.PSC_to_ALM_Mapper.py      v0.0.1
Mapping tool for getting PSC reference in Alarmviewer to image with BMO-instance
Then user can directly go to PSC image where error is.


Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



import dms.dmswebsocket as dms
import logging
import argparse
import os
import re
import collections



# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('tools.PSC_to_ALM_Mapper')
logger.setLevel(logging.INFO)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class DMS_keystats(object):
	""" DMS key statistics """
	# somehow inspired by "ant colony optimization algorithm" https://en.wikipedia.org/wiki/Ant_colony_optimization_algorithms
	# count how many times parts of DMS keys appear in a PSC file
	# (used for classification which PSC file is better suited for a BMO instance,
	#  the higher the total path-score, the more similar BMO instances are in same PSC file)

	# idea/example:
	# MSR01:H01:Uwp
	# MSR01:H01:Fuehler
	# MSR01:H02:Uwp
	#
	# statistics stored in dictionary:
	# "MSR01"               2
	# "MSR01:H01"           2
	# "MSR01:H01:Uwp"       1
	# "MSR01:H01:Fuehler"   1
	# "MSR01:H02"           1
	# "MSR01:H02:Uwp"       1
	#
	# =>query examples (higher keyscore means more similarity)
	# "MSR02:H10:Uwp" = 0
	# "MSR01:H01:Waf" = "MSR01" + "MSR01:H01" + "MSR01:H01:Waf" = 2 + 2 + 0 = 4
	# "MSR01:H02:Waf" = "MSR01" + "MSR01:H02" + "MSR01:H02:Waf" = 2 + 1 + 0 = 3

	def __init__(self):
		# query keyscore of nonexistant DMS keys wont raise KeyError
		# help from https://www.accelebrate.com/blog/using-defaultdict-python/
		self._pathcounter_dict = collections.defaultdict(lambda: 0)

	def update_statistic(self, bmo_inst):
		if bmo_inst:
			all_parts = bmo_inst.split(':')
			for x in xrange(len(all_parts)):
				if x == 0:
					new_parts_str = all_parts[0]
				else:
					new_parts_str = ''.join(all_parts[0:x])
				self._pathcounter_dict[new_parts_str] += 1


	def get_keyscore(self, dmskey):
		if dmskey:
			all_parts = dmskey.split(':')
			keyscore = 0
			for x in xrange(len(all_parts)):
				if x == 0:
					new_parts_str = all_parts[0]
				else:
					new_parts_str = ''.join(all_parts[0:x])

				keyscore = keyscore + self._pathcounter_dict[new_parts_str]
			return keyscore



class PSC_Analyzer(object):
	""" searches in PSC files for all BMO instances """
	def __init__(self, project_path):
		self._psc_path = os.path.join(project_path, 'scr')

		# key: BMO instance // value: list of filenames
		self._bmo_instances_dict = {}

		# key: PSC-filename // value: DMS_pathstats object
		self._psc_dms_keystats = {}

	def analyze(self):
		logger.debug('PSC_Analyzer.analyze(): searching LIB attributes in all PSC files')
		nof_files = 0
		for fullpath in self._filelist_generator(self._psc_path):
			nof_files += 1
			logger.debug('PSC_Analyzer.analyze(): analyzing PSC file "' + fullpath + '"')
			with open(fullpath, mode='r') as f:
				psc_content = f.read()

				if not fullpath in self._psc_dms_keystats:
					self._psc_dms_keystats[fullpath] = DMS_keystats()

				# help with regex: https://stackoverflow.com/questions/6018340/capturing-group-with-findall
				# =>we search only for one group, so we get a list of strings and not a list of tuples containing matched groups
				patterns = [re.compile(r'LIB;[\w\s]+\.plb;\w+;([\w:]+);BMO:.+'),                    # BMO instances
				            re.compile(r'IBW;[\w\s]+\.*\w*;\d+;\d+;\d+;\d+;BMO[\w:]+;([\w:]+);')]   # button with reinit
				for pattern in patterns:
					for bmo_inst in pattern.findall(psc_content):
						#logger.debug('PSC_Analyzer.analyze(): found BMO instance "' + bmo_inst + '")')

						# add current PSC file as possible target for ALM "Screen" of this BMO instance
						if not bmo_inst in self._bmo_instances_dict:
							self._bmo_instances_dict[bmo_inst] = []
						if not fullpath in self._bmo_instances_dict[bmo_inst]:
							self._bmo_instances_dict[bmo_inst].append(fullpath)

						# update DMS path statistics of current PSC file
						self._psc_dms_keystats[fullpath].update_statistic(bmo_inst)

				logger.debug('PSC_Analyzer.analyze(): found ' + str(len(self._bmo_instances_dict[bmo_inst])) + ' BMO instances.')
		logger.info('PSC_Analyzer.analyze(): found total ' + str(len(self._bmo_instances_dict)) + ' BMO instances in ' + str(nof_files) + ' PSC files.')


	def _filelist_generator(self, path):
		for entry in os.listdir(path):
			fullpath = os.path.join(path, entry)
			if os.path.isfile(fullpath):
				# ignoring BMOs (assumption: PSC-files starting with "_" or a digit aren't BMOs)
				pattern = r'^[_\d].*\.PSC'
				m = re.search(pattern, entry, re.IGNORECASE)
				if m:
					yield fullpath
			# FIXME: should we recursively tracerse subdirectories? Perhaps this would work:
				# elif os.path.isdir(fullpath):
				#      for curr_entry in self._filelist_generator(fullpath):
				#           yield curr_entry


	def get_psc_filename(self, bmo_instance):
		try:
			psc_list = self._bmo_instances_dict[bmo_instance]
			if len(psc_list) == 1:
				# simple case: only one PSC file contains this BMO instance
				return psc_list[0]
			else:
				# (old idea: sorting by number of "0" in filename (lesser "0" means lesser specific PSC file in menu concept)
				# help from https://www.programiz.com/python-programming/methods/built-in/sorted
				# and https://stackoverflow.com/questions/8899905/count-number-of-occurrences-of-a-given-substring-in-a-string
				# psc_list = sorted(psc_list, key=lambda x: x.count("0"))
				#
				# (old idea: removing "Logik"-files. =>now we use them as last option
				# removing "Logik" files
				# with help from https://stackoverflow.com/questions/3013449/list-filtering-list-comprehension-vs-lambda-filter
				#psc_list = [filename for filename in psc_list if not filename.upper().endswith("_LG.PSC")]

				# sort priority:
				# 1) "Logik" files to the end
				# 2) keyscore algorithm in DMS_keystats for similarity
				#

				def _sorting_key_function(fullpath):
					# generates tuple (<is Logik-file as bool>, <keyscore as integer>) for sorting in "get_psc_filename()"
					# help from https://wiki.python.org/moin/HowTo/Sorting#Key_Functions
					# and idea from https://stackoverflow.com/questions/5212870/sorting-a-python-list-by-two-criteria

					# sort priority:
					# 1) use "Logik" files only if BMO instance has no other appearance
					# 2) keyscore algorithm in DMS_keystats for similarity

					isLogik = '_LG' in fullpath or '_LOGIK' in fullpath.upper()
					keyscore = self._psc_dms_keystats[fullpath].get_keyscore(dmskey=bmo_instance)
					return (not isLogik, keyscore)

				# choose PSC image with highest rating (at the end of sorted list)
				psc_list = sorted(psc_list, key=_sorting_key_function)
				return psc_list[-1]

		except KeyError as ex:
			logger.error('PSC_Analyzer.get_psc_filename(): ignoring BMO instance "' + bmo_instance + '", it was not found on any PSC file!')
			return ""

	def get_PSC_path(self):
		return self._psc_path


class ALM_datapoint(object):
	def __init__(self, dms_ws):
		self._dms_ws = dms_ws

		# key: ALM datapoint // value: BMO instance
		self._alm_dps_dict = {}

		# key: ALM datapoint // value: current DMS-value of "ALM:Screen"
		self._alm_screen_dict = {}


	def collect(self):
		self._collect_ALM()
		self._collect_Screen()

		# retrieve all OBJECT datapoints and match against ALM datapoints
		responses = self._dms_ws.dp_get(path='',
		                                query=dms.Query(regExPath="^(?!BMO).+:OBJECT$",
		                                                maxDepth=-1))
		# logger.debug('FOO: responses[0]=' + repr(responses[0]))
		for respget in responses:
			bmo_instance = respget.path.split(':OBJECT')[0]
			if bmo_instance:
				for alm in self._alm_dps_dict:
					# assumption: every ALM datapoint contains part of exactly one BMO instance
					# FIXME: "Meta-VLOs" as used in BACnet VLOs are currently not tested and could lead to unexpected results...
					if bmo_instance in alm:
						self._alm_dps_dict[alm] = bmo_instance



	def _collect_ALM(self):
		# retrieve all ALM datapoints
		responses = self._dms_ws.dp_get(path='',
		                           query=dms.Query(hasAlarmData=True,
		                                           regExPath="^(?!BMO).*",
		                                           maxDepth=-1))
		exclusion = ('System', 'GE')
		for respget in responses:
			#logger.debug('FOO: type(respget)=' + repr(type(respget)) + ', respget=' + repr(respget))
			if not respget.path.startswith(exclusion):
				self._alm_dps_dict[respget.path] = None
		logger.info('ALM_datapoint._collect_ALM(): found ' + str(len(self._alm_dps_dict)) + ' ALM datapoints.')


	def generator_ALM_BMO_instance(self):
		for alm in self._alm_dps_dict:
			bmo_instance = self._alm_dps_dict[alm]
			if bmo_instance:
				yield alm, bmo_instance
			else:
				logger.warn('ALM_datapoint.dp_generator(): ignoring ALM datapoint "' + alm + '", it does not belong to an OBJECT!')


	def write_ALM_screen(self, psc_analyzer, only_dryrun=False):
		# writes screen-mapping of ALM datapoints into DMS
		unwritten_screens_dict = {}
		total_alm = 0
		for alm_dp, bmo_instance in self.generator_ALM_BMO_instance():
			total_alm += 1
			# dictionary access with default value: http://www.tutorialspoint.com/python/dictionary_get.htm
			# empty string means no PSC file referenced...
			# =>assumption: every BMO instance needs a representation on a PSC file,
			#               user will fix errors,
			#               we insert "ALM:Screen" in every case.
			curr_screen = self._alm_screen_dict.get(alm_dp, "")

			# get PSC filename from PSC fullpath
			# FIXME: assumption: we don't use subdirectories... should we care? how does GE search for a PSC file?
			psc_fullpath = psc_analyzer.get_psc_filename(bmo_instance)
			new_screen = os.path.basename(psc_fullpath)
			if curr_screen != new_screen:
				unwritten_screens_dict[alm_dp] = new_screen

		logger.info('ALM_datapoint.write_ALM_screen(): number of ALM datapoints in BMO instances: ' + str(total_alm))
		logger.info('ALM_datapoint.write_ALM_screen(): number of current ALM screen mappings: ' + str(len(self._alm_screen_dict)))
		logger.info('ALM_datapoint.write_ALM_screen(): number of changed ALM screen mappings: ' + str(len(unwritten_screens_dict)))

		if only_dryrun:
			logger.info('ALM_datapoint.write_ALM_screen(): only dryrun. =>no change in DMS...')
		else:
			if len(unwritten_screens_dict):
				logger.info('ALM_datapoint.write_ALM_screen(): =>write screen-mappings into DMS...')
				# iteration over dictionary: https://stackoverflow.com/questions/26660654/how-do-i-print-the-key-value-pairs-of-a-dictionary-in-python
				for alm, screen in unwritten_screens_dict.iteritems():
					self._write_ALM_screen(alm_dp=alm, psc_filename=screen)
				logger.info('ALM_datapoint.write_ALM_screen(): done. :-)')
			else:
				logger.info('ALM_datapoint.write_ALM_screen(): =>nothing to do...')


	def _write_ALM_screen(self, alm_dp, psc_filename):
		# write ALM screen mapping
		dms_key = ":".join([alm_dp, "ALM:Screen"])
		response = self._dms_ws.dp_set(path=dms_key,
		                           value=psc_filename,
		                           create=True)
		if response[0].message:
			logger.error('ALM_datapoint._write_ALM_screen(): DMS returned error "' + response[0].message + '" for DMS key "' + dms_key + '"')
			raise Exception(response[0].message)


	def _collect_Screen(self):
		# retrieve all "ALM:Screen" datapoints
		# for storing current settings into a DMS importfile
		responses = self._dms_ws.dp_get(path='',
		                                query=dms.Query(regExPath="^(?!BMO).*:ALM:Screen",
		                                                isType="string",
		                                                maxDepth=-1))
		exclusion = ('System', 'GE')
		for respget in responses:
			# logger.debug('FOO: type(respget)=' + repr(type(respget)) + ', respget=' + repr(respget))
			if not respget.path.startswith(exclusion):
				alm_dp = respget.path.split(':ALM:Screen')[0]
				if alm_dp and respget.value:
					self._alm_screen_dict[alm_dp] = respget.value
		logger.info('ALM_datapoint._collect_Screen(): found ' + str(len(self._alm_screen_dict)) + ' ALM datapoints with "Screen" mapping.')





def main(dms_server, dms_port, only_dryrun):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.PSC_to_ALM_Mapper',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('main(): established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])

		project_str = dms_ws.dp_get(path='System:Project')[0]['value']
		logger.info('main(): working in project "' + project_str + '"...')

		psc_analyzer = PSC_Analyzer(project_path=project_str)
		psc_analyzer.analyze()

		alm_dp = ALM_datapoint(dms_ws)
		alm_dp.collect()

		alm_dp.write_ALM_screen(psc_analyzer, only_dryrun)

		logger.info('Quitting "PSC_to_ALM_Mapper"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Mapping most accurate PSC image to ALM datapoint (used in "Alarm-Viewer")')

	parser.add_argument('--dryrun', '-d', action='store_true', dest='only_dryrun', default=False, help='no writes into DMS, only print statistics (default: False)')
	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port,
	              only_dryrun = args.only_dryrun,
	              )
	#sys.exit(status)