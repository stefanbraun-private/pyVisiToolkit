#!/usr/bin/env python
# encoding: utf-8
"""
tools.Ping_Trend.py      v0.0.1
Runs "ping.exe" in background and continuously writes Round-Trip-Time to a DMS key (which should have a TRD object)

Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""



import dms.dmswebsocket as dms
import argparse
import logging
import subprocess
import threading
import Queue
import shlex
import re
import time


# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('tools.Ping_Trend')
logger.setLevel(logging.DEBUG)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class KilledProcessException(Exception):
	pass

class AsyncProcess(threading.Thread):
	# problem: when running a subprocess, then reading it's stdout will block until subprocess wrote data...
	# background information from http://eyalarubas.com/python-subproc-nonblock.html
	# and help from: https://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python/4896288#4896288
	def __init__(self, cmd, stdout_queue):
		self._cmd = str(cmd)
		self._stdout_queue = stdout_queue
		super(AsyncProcess, self).__init__()
		self.daemon = True  # thread dies with the program
		logger.debug('AsyncProcess.__init__(): starting background subprocess...')
		self._process = subprocess.Popen(shlex.split(self._cmd), bufsize=1, stdout=subprocess.PIPE)
		logger.info('AsyncProcess.__init__(): started background subprocess "' + self._cmd + '" with PID ' + str(self._process.pid))

	def run(self):
		# help from https://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python/4896288#4896288
		for line in iter(self._process.stdout.readline, b''):
			self._stdout_queue.put(line)
		self._process.stdout.close()
		logger.info('AsyncProcess.run(): background subprocess "' + self._cmd + '" with PID ' + str(self._process.pid) + ' was killed...')

	def stop(self):
		# with help from https://stackoverflow.com/questions/4084322/killing-a-process-created-with-pythons-subprocess-popen
		logger.debug('AsyncProcess.stop(): killing background subprocess...')
		self._process.kill()


class PingTarget(object):
	PING_CMD = 'ping -t '

	# examples of answers in German Windows Ping:
	# Antwort von 127.0.0.1: Bytes=32 Zeit<1ms TTL=128      // everything ok
	# Antwort von 130.59.31.80: Bytes=32 Zeit=10ms TTL=128  // everything ok
	# Zeitüberschreitung der Anforderung.                   // timeout (mostly offline)
	# Antwort von 192.168.107.2: Die Gültigkeitsdauer wurde bei der Übertragung überschritten.  // TTL too low
	# PING: Fehler bei der Übertragung. Allgemeiner Fehler. // no route to host

	# examples of answers in English Windows Ping:
	# Reply from 127.0.0.1: bytes=32 time<1ms TTL=128       // everything ok
	# Reply from 192.168.203.97: bytes=32 time=21ms TTL=249 // everything ok
	PATTERN_SUCCESS = r'((Zeit)|(time))[<=](?P<millisecs>\d+)ms'

	def __init__(self, host, dmskey):
		self.host = str(host)
		self.dmskey = str(dmskey)
		self._thread = None
		self._stdout_queue = Queue.Queue()


	def start_background_ping(self):
		# with help from https://www.endpoint.com/blog/2015/01/28/getting-realtime-output-using-python
		cmd = PingTarget.PING_CMD + self.host
		logger.debug('PingTarget.start_background_ping(): command for ping is ' + repr(cmd))
		self._thread = AsyncProcess(cmd=cmd, stdout_queue=self._stdout_queue)
		self._thread.start()


	def get_ping_rtt(self):
		# using nonblocking queue for getting stdout of subprocess: https://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python/4896288#4896288
		try:
			line = self._stdout_queue.get_nowait()
		except Queue.Empty:
			if self._thread.is_alive():
				# no output yet
				return None
			else:
				# no thread means no active process!
				raise KilledProcessException()
		else:
			logger.debug('PingTarget.get_ping_rtt(): one line of stdout is ' + repr(line) + '[' + self.host + ']')
			if line != '':
				match = re.search(PingTarget.PATTERN_SUCCESS, line)
				if match:
					return int(match.group('millisecs'))
				else:
					# assuming error => "-1" in trend should show an error
					return -1
			else:
				return None


	def stop_background_ping(self):
		self._thread.stop()


class Runner(object):
	def __init__(self, dms_ws, target_list, only_dryrun=None):
		self._dms_ws = dms_ws
		self._target_list = target_list
		self._only_dryrun = bool(only_dryrun)
		self._pingtargets = []



	def check_datapoints(self):
		logger.info('Runner.check_datapoints(): check availability of datapoints in DMS...')
		for host, dmskey in self._target_list:
			response = self._dms_ws.dp_get(path=dmskey)[0]
			if response.type:
				if not response.type in [u'int', u'double']:
					logger.warn('Runner.check_datapoints(): DMS key "' + dmskey + '" should have datatype FLT or integer!')
				if not self._only_dryrun:
					self._pingtargets.append(PingTarget(host=host, dmskey=dmskey))
					logger.info('Runner.check_datapoints(): added host "' + str(host) + '" to target list [DMS-key: ' + dmskey + ']')
			else:
				logger.error('Runner.check_datapoints(): DMS key "' + dmskey + '" for host "' + str(host) + '" does not exist!')
		logger.info('Runner.check_datapoints(): check availability of datapoints in DMS is done.')


	def start_pings(self):
		logger.info('Runner.start_pings(): starting background ping for every target...')
		for target in self._pingtargets:
			target.start_background_ping()


	def analyze_and_store(self):
		# manipulation of list while list iteration: =>we need a copy of our list!
		for idx, target in enumerate(self._pingtargets):
			try:
				rtt = target.get_ping_rtt()
				if rtt:
					logger.debug('Runner.analyze_and_store(): Round Trip Time is ' + repr(rtt) + ' [target: ' + target.host + ']')
					resp = self._dms_ws.dp_set(path=target.dmskey,
					                           value=rtt,
					                           create=False)
					if resp[0].code == 'ok':
						self._cached_val = resp[0].value
					else:
						logger.error('Runner.analyze_and_store(): DMS returned error "' + resp[
							0].message + '" for DMS key "' + target.dmskey + '"')
						# FIXME: should we throw exception? should we remove this target from list and keep going on?
						# =>currently we retry it next cycle.
			except KilledProcessException:
				# subprocess is no more working...
				self._pingtargets.remove(target)

	def get_nof_pingtargets(self):
		return len(self._pingtargets)


	def stop_pings(self):
		logger.info('Runner.stop_pings(): stopping background ping for every target...')
		for target in self._pingtargets:
			target.stop_background_ping()




def main(dms_server, dms_port, target_list, only_dryrun):
	with dms.DMSClient(whois_str=u'pyVisiToolkit',
	                                    user_str=u'tools.Ping_Trend',
	                                    dms_host_str=dms_server,
	                                    dms_port_int=dms_port) as dms_ws:
		logger.info('established WebSocket connection to DMS version ' + dms_ws.dp_get(path='System:Version:dms.exe')[0]['value'])
		runner = Runner(dms_ws=dms_ws,
		                target_list=target_list,
		                only_dryrun=only_dryrun)
		runner.check_datapoints()

		if not only_dryrun:
			runner.start_pings()

			# help from http://stackoverflow.com/questions/13180941/how-to-kill-a-while-loop-with-a-keystroke
			# and http://effbot.org/zone/stupid-exceptions-keyboardinterrupt.htm
			try:
				logger.info('"Ping_Trend" is starting work... Press <CTRL> + C for aborting.')

				keep_running = True
				while keep_running:
					# FIXME: we should implement a more efficient method...
					runner.analyze_and_store()
					keep_running = runner.get_nof_pingtargets() > 0
					time.sleep(0.001)
				logger.info('"Ping_Trend" has nothing to do...')
			except (KeyboardInterrupt, SystemExit):
			#except:
				runner.stop_pings()

	logger.info('Quitting "Ping_Trend"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Pinging target(s) in background and writing Round-Trip-Time to DMS.')

	# help for commandline switches: https://stackoverflow.com/questions/8259001/python-argparse-command-line-flags-without-arguments
	# help for appending list of targets: https://mkaz.tech/code/python-argparse-cookbook/

	parser.add_argument('--target', '-t', action='append', dest='target', nargs=2, help='pair of target and DMS key, one or more times (example: -t 192.168.1.1 System:Ping_Trend:DefaultGW)')
	parser.add_argument('--dryrun', '-d', action='store_true', dest='only_dryrun', default=False, help='no write into DMS, only print result (default: False)')
	parser.add_argument('--dms_servername', '-s', dest='dms_server', default='localhost', type=str, help='hostname or IP address for DMS JSON Data Exchange (default: localhost)')
	parser.add_argument('--dms_port', '-p', dest='dms_port', default=9020, type=int, help='TCP port for DMS JSON Data Exchange (default: 9020)')

	args = parser.parse_args()

	status = main(dms_server = args.dms_server,
	              dms_port = args.dms_port,
	              target_list = args.target,
	              only_dryrun = args.only_dryrun)
	#sys.exit(status)