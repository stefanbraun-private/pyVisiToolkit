#!/usr/bin/env python
# encoding: utf-8
"""
misc.EventSystem.py

Copyright (C) 2018 Stefan Braun

registered handlers (a bag of handlers) getting called when event gets fired
using ideas from "axel events" https://github.com/axel-events/axel
and "event system" from http://www.valuedlessons.com/2008/04/events-in-python.html
(it seems that axel.Event leaks threads in my tries, it didn't kill old ones on synchronous execution, that's why I created my own event system)

=>differences to "axel events":
	-executes handlers synchronously in same thread
	-no timeouts for executing handler/callback functions,
	 (in Python it seems not possible to cleanly kill another thread,
	  and killing a subprocess would lead to problems for user with IPC and broken queues)

=>differences to "event system from valuedlessons.com":
	-using list of handlers instead of set (fixed execution order, allowing registration of callback multiple times)


	The execution result is returned as a list containing all results per handler having this structure:
            exec_result = [
                (True, result, handler),        # on success
                (False, error_info, handler),   # on error
                (None, None, handler), ...      # asynchronous execution
            ]


This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import threading
import queue
import time
import copy
import sys
import logging

# pause in busy-waiting-loop
SLEEP_TIMEBASE = 0.001

# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('misc.EventSystem')
logger.setLevel(logging.WARN)

# create console handler
# =>set level to DEBUG if you want to see everything on console!
ch = logging.StreamHandler()
ch.setLevel(logging.WARN)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)






class EventSystem(object):
	''' lightweight event system with many ideas from "axel event" '''

	# one background thread for all asynchronous event handler functions
	# (shared by EventSystem instances in asynchronous mode)
	_alock = threading.Lock()
	_async_thread = None
	_async_queue = None

	def __init__(self, sync_mode = True, exc_info=True, traceback=False):
		self._sync_mode = sync_mode
		self._exc_info = exc_info
		self._traceback = traceback
		self._handler_list = []
		self._hlock = threading.RLock()
		if not sync_mode:
			EventSystem._setup_async_thread()
		self._time_secs_old = 0.0
		self.duration_secs = 0.0

	@staticmethod
	def _setup_async_thread():
		with EventSystem._alock:
			if not EventSystem._async_queue:
				EventSystem._async_queue = queue.Queue()
			if EventSystem._async_thread:
				logger.info('EventSystem._setup_async_thread(): using existing background thread for asynchronous handler execution...')
				logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
				EventSystem._async_thread.inc_nof_eventsources()
				logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
			else:
				logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
				EventSystem._async_thread = _Async_Executor_thread(target_q=EventSystem._async_queue)
				EventSystem._async_thread.start()
				logger.info(
					'EventSystem._setup_async_thread(): started background thread for asynchronous handler execution...')
				logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')


	def handle(self, handler):
		""" register a handler (add a callback function) """
		with self._hlock:
			self._handler_list.append(handler)
		return self

	def unhandle(self, handler):
		""" unregister handler (removing callback function) """
		with self._hlock:
			try:
				self._handler_list.remove(handler)
			except:
				raise ValueError("Handler is not handling this event, so cannot unhandle it.")
		return self

	def fire(self, *args, **kargs):
		""" collects results of all executed handlers """

		self._time_secs_old = time.time()
		# allow register/unregister while execution
		# (a shallowcopy should be okay.. https://docs.python.org/2/library/copy.html )
		with self._hlock:
			handler_list = copy.copy(self._handler_list)
		result_list = []
		for handler in handler_list:
			one_res_tuple = (None, None, None)
			if self._sync_mode:
				# grab results of all handlers
				result = self._execute(handler, *args, **kargs)
				if isinstance(result, tuple) and len(result) == 3 and isinstance(result[1], Exception):
					# error occurred
					one_res_tuple = (False, self._error(result), handler)
				else:
					one_res_tuple = (True, result, handler)
			else:
				# execute handlers in background, ignoring result
				EventSystem._async_queue.put((handler, args, kargs))
				one_res_tuple = (None, None, handler)
			result_list.append(one_res_tuple)

		# update statistics
		time_secs_new = time.time()
		self.duration_secs = time_secs_new - self._time_secs_old
		self._time_secs_old = time_secs_new

		return result_list

	def _execute(self, handler, *args, **kwargs):
		""" executes one callback function """
		# difference to Axel Events: we don't use a timeout and execute all handlers in same thread
		# FIXME: =>possible problem: blocking of event firing when user gives a long- or infinitly-running callback function
		# (in Python it doesn't seem possible to forcefully kill a thread with clean ressource releasing,
		#  a thread has to cooperate und behave nice...
		#  execution and killing a process would be possible, but has data corruption problems with queues
		#  and possible interprocess communication problems with given handler/callback function)

		result = None
		exc_info = None

		try:
			result = handler(*args, **kwargs)
		except:
			exc_info = sys.exc_info()
		if exc_info:
			return exc_info
		return result


	def _error(self, exc_info):
		""" Retrieves the error info """
		if self._exc_info:
			if self._traceback:
				return exc_info
			return exc_info[:2]
		return exc_info[1]


	def getHandlerCount(self):
		with self._hlock:
			return len(self._handler_list)


	def clear(self):
		""" Discards all registered handlers """
		with self._hlock:
			self._handler_list = []


	def __del__(self):
		if not self._sync_mode:
			if hasattr(EventSystem, "_async_thread"):
				# only if thread-instance is still existing (on teardown Python interpreter removes symbols of objects):
				# update number of asynchronous instances
				EventSystem._async_thread.dec_nof_eventsources()

	__iadd__ = handle
	__isub__ = unhandle
	__call__ = fire
	__len__ = getHandlerCount

	def __repr__(self):
		""" developer representation of this object """
		return u'EventSystem(' + repr(self._handler_list) + u')'



class _Async_Executor_thread(threading.Thread):
	""" executing handler functions asynchronously in background """
	# =>attention: if EventSystem doesn't keep "self._nof_eventsources" up to date, then this thread will keep whole Python program running!

	def __init__(self, target_q):
		threading.Thread.__init__(self)
		# trying to cleanup thread, so no daemon...
		# https://stackoverflow.com/questions/20596918/python-exception-in-thread-thread-1-most-likely-raised-during-interpreter-shutd/20598791#20598791
		self.daemon = False
		self._target_q = target_q
		#self.keep_running = True
		self._nof_eventsources = 1
		self._lock = threading.Lock()

	def run(self):
		while self._nof_eventsources > 0:
			try:
				_target, _args, _kwargs = self._target_q.get(block=False)
			except queue.Empty:
				# give other threads some CPU time...
				time.sleep(SLEEP_TIMEBASE)
			else:
				# (this is an optional else clause when no exception occured)
				try:
					_res = _target(*_args, **_kwargs)
					logger.debug('_Async_Executor_thread.run(): handler function ' + repr(_target) + '(args=' + repr(_args) + ', kwargs=' + repr(_kwargs) + ') has result "' + repr(_res) + '"')
				except:
					logger.error('_Async_Executor_thread.run(): exception in handler function ' + repr(_target) + '(args=' + repr(_args) + ', kwargs=' + repr(_kwargs) + '):'+ repr(sys.exc_info()[:2]))
				finally:
					del _target, _args, _kwargs


	def inc_nof_eventsources(self):
		with self._lock:
			self._nof_eventsources += 1
			logger.debug('_Async_Executor_thread.inc_nof_eventsources(): self._nof_eventsources=' + str(self._nof_eventsources))

	def dec_nof_eventsources(self):
		with self._lock:
			self._nof_eventsources -= 1
			logger.debug('_Async_Executor_thread.dec_nof_eventsources(): self._nof_eventsources=' + str(self._nof_eventsources))



if __name__ == '__main__':


	test_set = set([1, 2])

	def cb1(event):
		logger.info('### cb1: enter callback: event=' + str(event))
		time.sleep(2)
		logger.info('*** cb1: exit callback: event=' + str(event))
		return True

	def cb2(event):
		# takes too long for execution
		logger.info('### cb2: enter callback: event=' + str(event))
		time.sleep(10)
		logger.info('*** cb2: exit callback: event=' + str(event))

	def cb3(event):
		# raises exception
		logger.info('### cb3: enter callback: event=' + str(event))
		print(str(1/0))
		logger.info('*** cb3: exit callback: event=' + str(event) + str(1 / 0))

	def cb4(event):
		# raises exception
		logger.info('### cb4: enter callback: event=' + str(event))
		raise Exception()
		logger.info('*** cb4: exit callback: event=' + str(event))

	sync_mode = True
	if 1 in test_set:
		sync_mode = False

	if 2 in test_set:
		if sync_mode:
			logger.error('testing synchronous events...')
		else:
			logger.error('testing asynchronous events...')
		event = EventSystem(sync_mode=sync_mode)
		event += cb1
		event += cb2
		event += cb3
		event += cb4

		CALLBACK_DURATION_WARNLEVEL = 10

		for x in range(2):
			result = event('TEST no.' + str(x))

			if result:
				for idx, res in enumerate(result):
					if res[0] == None:
						logger.debug('event-firing: asynchronously started callback no.' + str(idx) + ': handler=' + repr(res[2]))
					else:
						logger.debug('event-firing: synchronous callback no.' + str(idx) + ': success=' + str(res[0]) + ', result=' + str(res[1]) + ', handler=' + repr(res[2]))

					if res[0] == False:
						# example: res[1] without traceback: (<type 'exceptions.TypeError'>, TypeError("cannot concatenate 'str' and 'int' objects",))
						#          =>when traceback=True, then ID of traceback object is added to the part above.
						#            Assumption: traceback is not needed. It would be useful when debugging client code...
						logger.error('event-firing: synchronous callback no.' + str(idx) + ' failed: ' + str(res[1]) + ' [handler=' + repr(res[2]) + ']')
			else:
				logger.info('event-firing had no effect (no handler in EventSystem object')

			# diagnostic values
			logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
			if event.duration_secs > CALLBACK_DURATION_WARNLEVEL:
				logger.warn('event-firing took ' + str(event.duration_secs) + ' seconds... =>you should shorten your callback functions!')

			# give callbacks time for execution
			time.sleep(15)
		logger.info('test is done, trying to clean up...')
		logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
		logger.info('manually deleting reference to EventSystem instance...')
		event = None
		time.sleep(3)
		logger.debug('[number of active threads: ' + repr(threading.enumerate()) + ']')
		logger.info('main thread will exit...')
