#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017-2018 Stefan Braun

current state january 4th 2018:
=>whole functionality of cleartext WebSocket for DMS Data Exchange is implemented and should work
=>refactoring is needed (improving error handling, websocket handling, logging, ...)
=>possible ideas for further work:
  -learn Python3, make code compatible for Python 3
  -documentation and examples
  -create clean package for pip, Anaconda Cloud, ...
  -(caching?) proxy between client(s) and DMS
  -provide services via ZeroMQ or other IPC to other pyVisiToolkit programms
  -SSL-WebSocket connection to DMS
  -...

current state august 8th 2017:
=>test with WebSocket library https://github.com/websocket-client/websocket-client
(without using complicated huge frameworks)
==>this works well! :-)
currently only cleartext WebSocket (URL "ws" instead of "wss"/SSL) is implemented


Based on this documentation:
https://github.com/stefanbraun-private/stefanbraun-private.github.io/tree/master/ProMoS_dev_docs



This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

DEBUGGING = False


import json
import time
import uuid
import websocket
import thread
import threading
import collections
import dateutil.parser, datetime
import logging
import queue

# events handling https://github.com/axel-events/axel
# =>installed with pip from https://anaconda.org/pypi/axel
import axel


# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger
logger = logging.getLogger('dms.dmswebsocket')
logger.setLevel(logging.DEBUG)

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






TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')

# duration of one time.sleep() in busy-waiting-loops
SLEEP_TIMEBASE = 0.001

# according "ProMoS DMS JSON Data Exchange":
DMS_PORT = 9020             # cleartext HTTP or WebSocket
DMS_HOST = "127.0.0.1"      # local connection: doesn't need authentification
DMS_BASEPATH = "/json_data" # default for HTTP and WebSocket

# default timeout in seconds for DMS JSON Data Exchange requests
TIMEOUT = 300


# constants for retrieving extended infos ("extInfos")
# implementing something similar as in "sticky"-options of http://effbot.org/tkinterbook/grid.htm
# =>selection of more than one event is possible by addition or with OR: ON_CHANGE + ON_SET // ON_CHANGE | ON_SET
# (parsing is done in class _CmdGet())
INFO_STATE          = 1     # state of this value
INFO_ACCTYPE        = 2     # accurate type information
INFO_NAME           = 4     # topmost "NAME" datapoint of this tree
INFO_TEMPLATE       = 8     # topmost "OBJECT" datapoint of this tree
INFO_UNIT           = 16    # unit //FIXME: what's the name of a unit-datapoint?
INFO_COMMENT        = 32    # comment
INFO_CHANGELOGGROUP = 64    # group name of changelog protocol
INFO_ALL            = 127   # combination of all above


# constants for event subscriptions
# implementing something similar as in "sticky"-options of http://effbot.org/tkinterbook/grid.htm
# =>selection of more than one event is possible by addition or with OR: ON_CHANGE + ON_SET // ON_CHANGE | ON_SET
# FIXME: should we refactor this? we use integers and string values in class DMSEvent() and _CmdSub()
ON_CHANGE    = 1
ON_SET       = 2
ON_CREATE    = 4
ON_RENAME    = 8
ON_DELETE    = 16
ON_ALL       = 31





class _Mydict(collections.Mapping):
	""" dictionary-like superclass with attribute access """

	# inherit from abstract class "Mapping" for getting dictionary-interface
	# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
	# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
	# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )

	def __init__(self, **kwargs):
		self._values_dict = {}

	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __getattr__(self, name):
		# get's called when attribute isn't found
		# =>convenient way for retrieving element from dictionary!
		# https://stackoverflow.com/questions/2405590/how-do-i-override-getattr-in-python-without-breaking-the-default-behavior
		try:
			return self._values_dict[name]
		except KeyError:
			# Default behaviour
			raise AttributeError

	def __repr__(self):
		""" developer representation of this object """
		return u'_Mydict(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)

	def as_dict(self):
		return self._values_dict


class _Mylist(collections.Sequence):
	""" list-like superclass """
	# implementing abstract class "Sequence" for getting list-like object
	# https://docs.python.org/2/library/collections.html#collections.Sequence

	def __init__(self):
		# internal storage: list
		self._values_list = []

	def __getitem__(self, idx):
		return self._values_list[idx]

	def __len__(self):
		return len(self._values_list)

	def __repr__(self):
		""" developer representation of this object """
		return u'_Mylist(' + repr(self._values_list) + u')'

	def __str__(self):
		return u'' + str(self._values_list)

	def as_list(self):
		return self._values_list


class _Request(object):
	""" one JSON request containing DMS commands """
	def __init__(self, whois, user):
		self.whois = u'' + whois
		self.user = u'' + user
		self.tag = None # normally we don't tag the whole request, since we can tag most single commands inside request

		# dict of lists, containing all pending commands
		self._cmd_dict = {}
		self._cmd_tags_list = []

	def addCmd(self, *args):
		for cmd in args:
			curr_type = cmd.get_type()

			if not curr_type in self._cmd_dict:
				self._cmd_dict[curr_type] = []
			# include this command into request and update list with message tags
			self._cmd_dict[curr_type].append(cmd)
			self._cmd_tags_list.append(cmd.tag)
		return self

	def as_dict(self):
		# building complete request
		# (all request commands contain a list of commands,
		# usually we send only one command per request)
		curr_dict = {}
		curr_dict[u'whois'] = self.whois
		curr_dict[u'user'] = self.user

		if self.tag:
			# tagging whole frame
			curr_dict[u'tag'] = self.tag
		else:
			# special treatment of tagless commands: tagging whole frame with helper-dictionary for identification of response
			tag_dict = {}
			if _CmdChangelogGetGroups.CMD_TYPE in self._cmd_dict:
				groups_tag_list = []
				for groupCmd in self._cmd_dict[_CmdChangelogGetGroups.CMD_TYPE]:
					groups_tag_list.append(groupCmd.get_tag())
				tag_dict[_CmdChangelogGetGroups.CMD_TYPE] = groups_tag_list
			if tag_dict:
				curr_dict[u'tag'] = tag_dict

		for cmdtype in self._cmd_dict:
			curr_list = []
			for cmd in self._cmd_dict[cmdtype]:
				curr_list.append(cmd.as_dict())
			if curr_list:
				curr_dict[cmdtype] = curr_list
		return curr_dict

	def get_tags(self):
		""" returns all messagetags from included commands """
		return self._cmd_tags_list

	def __repr__(self):
		""" developer representation of this object """
		return u'_Request(' + repr(self.as_dict()) + u')'

	def __str__(self):
		return u'' + str(self.as_dict())



class Query(_Mydict):
	""" optional component in "get" request """

	def __init__(self, **kwargs):
		super(Query, self).__init__()

		for key in kwargs.keys():
			val = None
			if key in [u'regExPath',
			           u'regExValue',
			           u'regExStamp',
			           u'isType']:
				# handle as string
				val = u'' + kwargs.pop(key)
			elif key in [u'hasHistData',
			             u'hasChangelog',
			             u'hasAlarmData']:
				# handle as boolean
				val = bool(kwargs.pop(key))
			elif key == u'maxDepth':
				# handle as integer
				val = int(kwargs.pop(key))
			else:
				raise ValueError('parameter "' + repr(key) + '" is illegal in "Query" object')
			self._values_dict[key] = val

	def __repr__(self):
		""" developer representation of this object """
		return u'Query(' + repr(self._values_dict) + u')'


class HistData(_Mydict):
	""" optional component in "get" request """

	def __init__(self, start, **kwargs):
		super(HistData, self).__init__()

		# convert datetime.datetime object to ISO 8601 format
		val = None
		try:
			val = u'' + start.isoformat()
		except AttributeError:
			# now we assume it's already a string
			val = u'' + start
		self._values_dict[u'start'] = val


		for key in kwargs.keys():
			val = None
			if key == u'end':
				# convert datetime.datetime object to ISO 8601 format
				end_tstamp = kwargs.pop(key)
				try:
					val = u'' + end_tstamp.isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + end_tstamp
			elif key == u'interval':
				# expecting number, conversion to int
				val = int(kwargs.pop(key))
			elif key == u'format':
				# expecting string
				# FIXME: should we check for correct parameter? Or should we send it anyway to DMS?
				val = u'' + kwargs.pop(key)
			else:
				raise ValueError('parameter "' + repr(key) + '" is illegal in "HistData" object')
			self._values_dict[key] = val

	def __repr__(self):
		""" developer representation of this object """
		return u'HistData(' + repr(self._values_dict) + u')'


class Changelog(_Mydict):
	""" optional component in "get" request """

	def __init__(self, start, end=None):
		super(Changelog, self).__init__()

		for key, tstamp in [(u'start', start),
		                    (u'end', end)]:
			if tstamp != None:
				# convert datetime.datetime object to ISO 8601 format
				val = None
				try:
					val = u'' + tstamp.isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + tstamp
				self._values_dict[key] = val

	def __repr__(self):
		""" developer representation of this object """
		return u'Changelog(' + repr(self._values_dict) + u')'



class _CmdGet(object):
	""" one unique "get" request, parsed from **kwargs """

	CMD_TYPE = u'get'

	def __init__(self, msghandler, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# deleting keys from kwargs while iteration over it
		# https://stackoverflow.com/questions/5384914/how-to-delete-items-from-a-dictionary-while-iterating-over-it
		self.path = u'' + path
		self.query = None
		self.histData = None
		self.changelog = None
		self.showExtInfos = None
		self.tag = msghandler.prepare_tag()

		for key in kwargs.keys():
			if key == u'showExtInfos':
				showExtInfos = kwargs.pop(key)
				try:
					showExtInfos_int = int(showExtInfos)
					assert showExtInfos_int > 0 and showExtInfos_int <= INFO_ALL, u'field "showExtInfos" excepts integer constant, got illegal value "' + str(showExtInfos_int) + u'"'
					self.showExtInfos = self.showExtInfos_as_strlist(showExtInfos_int)
				except ValueError:
					# assumption: it's already a list of strings
					self.showExtInfos = [].extend(showExtInfos)
			elif key == u'query':
				self.query = kwargs.pop(key)
				assert type(self.query) is Query, u'field "query" expects "Query" object, got "' + str(type(self.query)) + u'" instead'
			elif key == u'histData':
				self.histData = kwargs.pop(key)
				assert type(self.histData) is HistData, u'field "histData" expects "HistData" object, got "' + str(type(self.histData)) + u'" instead'
			elif key == u'changelog':
				self.changelog = kwargs.pop(key)
				assert type(self.changelog) is Changelog, u'field "changelog" expects "Changelog" object, got "' + str(type(self.changelog)) + u'" instead'
			else:
				raise ValueError('field "' + repr(key) + '" is illegal in "get" request')


	def showExtInfos_as_strlist(self, showExtInfos_int):
		# build a list of strings for DMS request
		# it uses same eventcodes as in class DMSEvent()
		strings_list = []
		for val_int, val_str in [(INFO_STATE,           u'state'),
		                         (INFO_ACCTYPE,         u'accType'),
		                         (INFO_NAME,            u'name'),
		                         (INFO_TEMPLATE,        u'template'),
		                         (INFO_UNIT,            u'unit'),
		                         (INFO_COMMENT,         u'comment'),
		                         (INFO_CHANGELOGGROUP,  u'changelogGroup')]:
			if showExtInfos_int == INFO_ALL or showExtInfos_int & val_int:
				# flag is set
				strings_list.append(val_str)

		return strings_list



	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.showExtInfos:
			curr_dict[u'showExtInfos'] = self.showExtInfos
		if self.query:
			curr_dict[u'query'] = self.query.as_dict()
		if self.histData:
			curr_dict[u'histData'] = self.histData.as_dict()
		if self.changelog:
			curr_dict[u'changelog'] = self.changelog.as_dict()
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdGet.CMD_TYPE


class _CmdSet(object):
	""" one unique "Set" request, parsed from **kwargs """

	CMD_TYPE = u'set'

	def __init__(self, msghandler, path, value, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "set" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.value = value
		self.request = {}
		self.tag = msghandler.prepare_tag()

		for key in kwargs.keys():
			# parsing request options
			val = None
			if key == u'create':
				val = bool(kwargs.pop(key))
			elif key == u'type':
				assert kwargs[key] in (u'int', u'double', u'string', u'bool'), u'unexpected type of value!'
				val = u'' + kwargs.pop(key)
			elif key == u'stamp':
				# convert datetime.datetime object to ISO 8601 format
				val_raw = kwargs.pop(key)
				try:
					val = u'' + val_raw.isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + val_raw
			else:
				raise ValueError('field "' + repr(kwargs) + '" is illegal in "set" request')

			if val:
				self.request[key] = val


	def as_dict(self):
		# no need to create deep-copy, changes are on same dict
		curr_dict = self.request
		curr_dict[u'path'] = self.path
		curr_dict[u'value'] = self.value
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdSet.CMD_TYPE


class _CmdRen(object):
	""" one unique "Rename" request, parsed from **kwargs """

	CMD_TYPE = u'rename'

	def __init__(self, msghandler, path, newPath, **kwargs):
		# kwargs are not used. we keep them for future extensions
		self.path = u'' + path
		self.newPath = u'' + newPath
		self.tag = msghandler.prepare_tag()

		if kwargs:
			raise ValueError('field "' + repr(kwargs) + '" is illegal in "rename" request')


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		curr_dict[u'newPath'] = self.newPath
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdRen.CMD_TYPE


class _CmdDel(object):
	""" one unique "Delete" request, parsed from **kwargs """

	CMD_TYPE = u'delete'

	def __init__(self, msghandler, path, recursive=None, **kwargs):
		# kwargs are not used. we keep them for future extensions
		self.path = u'' + path

		# flag "recursive" is optional, default in DMS is False.
		# Because this is a possible dangerous command we allow explicit sending of False over the wire!
		self.recursive = recursive
		self.tag = msghandler.prepare_tag()

		if kwargs:
			raise ValueError('field "' + repr(kwargs) + '" is illegal in "delete" request')


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.recursive != None:
			curr_dict[u'recursive'] = bool(self.recursive)
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdDel.CMD_TYPE



class _CmdSub(object):
	""" one unique "subscribe" request, parsed from **kwargs """

	CMD_TYPE = u'subscribe'

	def __init__(self, msghandler, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "sub" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.query = None
		curr_tag = None
		if u'tag' in kwargs.keys():
			# caller wants to reuse existing tag =>DMS will update subscription when path and tag match a current subscription
			curr_tag = kwargs.pop(u'tag')
		self.tag = msghandler.prepare_tag(curr_tag=curr_tag)


		for key in kwargs.keys():
			# parsing "query" object
			if key == u'query':
				self.query = kwargs.pop(key)
				assert type(self.query) is Query, u'field "query" expects "Query" object, got "' + str(type(self.query)) + u'" instead'

			# parsing properties
			if key == u'event':
				# event codes similar as in "sticky"-options of http://effbot.org/tkinterbook/grid.htm
				# =>we expect an integer value, build as addition e.g. ON_CHANGE + ON_SET
				val = kwargs.pop(key)
				try:
					self.event = self.eventcode_as_str(val)
				except TypeError:
					# assumption: it's already a string
					self.event = u'' + val

		if kwargs:
			raise ValueError('field "' + repr(kwargs) + '" is illegal in "subscribe" request')


	def eventcode_as_str(self, code_int):
		# build a string for DMS request
		# it uses same eventcodes as in class DMSEvent()
		strings_list = []
		if code_int == ON_ALL:
			strings_list = u'*'
		else:
			for val_int, val_str in [(ON_CHANGE, DMSEvent.CODE_CHANGE),
			                         (ON_SET, DMSEvent.CODE_SET),
			                         (ON_CREATE, DMSEvent.CODE_CREATE),
			                         (ON_RENAME, DMSEvent.CODE_RENAME),
			                         (ON_DELETE, DMSEvent.CODE_RENAME)]:
				if code_int & val_int:
					# flag is set
					strings_list.append(val_str)

		return u','.join(strings_list)



	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.query:
			curr_dict[u'query'] = self.query.as_dict()
		if self.event:
			curr_dict[u'event'] = self.event
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdSub.CMD_TYPE



class _CmdUnsub(object):
	""" one unique "unsubscribe" request, parsed from **kwargs """

	CMD_TYPE = u'unsubscribe'

	def __init__(self, msghandler, path, tag):
		# =>because our implementation of subscriptions always use a tag, we have to make tags mandatory
		# (documentation for "unsubscribe" say "tag" is an optional field)
		self.path = u'' + path
		self.tag = msghandler.prepare_tag(curr_tag=tag)

	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdUnsub.CMD_TYPE



class _CmdChangelogGetGroups(object):
	""" one unique "changelogGetGroups" request, parsed from **kwargs """
	# ATTENTION: this command doesn't use an own tag, we must tag the whole frame!

	CMD_TYPE = u'changelogGetGroups'

	def __init__(self, msghandler, **kwargs):
		# kwargs are not used. we keep them for future extensions

		# tag is handled in class _Request()
		self.tag = msghandler.prepare_tag()

		if kwargs:
			raise ValueError('field "' + repr(kwargs) + '" is illegal in "changelogGetGroups" request')


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'changelogGetGroups'] = []
		return curr_dict

	def get_tag(self):
		return self.tag

	def get_type(self):
		return _CmdChangelogGetGroups.CMD_TYPE



class _CmdChangelogRead(object):
	""" one unique "changelogRead" request, parsed from **kwargs """

	CMD_TYPE = u'changelogRead'

	def __init__(self, msghandler, group, start, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "changelogRead" object and all it's subobjects are unique, we could handle them in the same loop
		self.group = u'' + group

		# convert datetime.datetime object to ISO 8601 format
		try:
			self.start = u'' + start.isoformat()
		except AttributeError:
			# now we assume it's already a string
			self.start = u'' + start

		self.request = {}
		self.tag = msghandler.prepare_tag()

		for key in kwargs.keys():
			# parsing request options
			val = None
			if key == u'end':
				# convert datetime.datetime object to ISO 8601 format
				val_raw = kwargs.pop(key)
				try:
					val = u'' + val_raw.isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + val_raw
			else:
				raise ValueError('field "' + repr(kwargs) + '" is illegal in "changelogRead" request')

			if val:
				self.request[key] = val


	def as_dict(self):
		# no need to create deep-copy, changes are on same dict
		curr_dict = self.request
		curr_dict[u'group'] = self.group
		curr_dict[u'start'] = self.start
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _CmdChangelogRead.CMD_TYPE




class ExtInfos(_Mydict):
	""" from DMS: optional extended infos about datapoint """

	_fields = (u'state',
	           u'accType',
	           u'name',
	           u'template',
	           u'unit',
	           u'comment',
	           u'changelogGroup')
	def __init__(self, **kwargs):
		super(ExtInfos, self).__init__()

		for field in ExtInfos._fields:
			try:
				# all fields are strings.
				# default: no special treatment
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				self._values_dict[field] = None

	def __repr__(self):
		""" developer representation of this object """
		return u'ExtInfos(' + repr(self._values_dict) + u')'


class HistData_detail(_Mylist):
	""" from DMS: optional history data in detailed format """

	_fields = (u'stamp',
	           u'value',
	           u'state',
	           u'rec')

	def __init__(self, histobj_list):
		super(HistData_detail, self).__init__()
		# internal storage: list of dictionarys

		for histobj in histobj_list:
			curr_dict = {}
			for field in HistData_detail._fields:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						curr_dict[field] = dateutil.parser.parse(histobj[field])
					except ValueError:
						# something went wrong, conversion into a datetime.datetime() object isn't possible
						logger.exception('constructor of HistData_detail(): ERROR: timestamp in current response could not get parsed as valid datetime.datetime() object!')
						curr_dict[field] = None
				else:
					# other fields are number or string, currently no special treatment
					try:
						curr_dict[field] = histobj[field]
					except KeyError:
						# something went wrong, a mandatory field is missing...
						logger.exception('constructor of HistData_detail(): ERROR: mandatory field "' + field + '" is missing in current response!')
						# argument was not in response =>setting default value
						curr_dict[field] = None
			# save current dict, begin a new one
			self._values_list.append(curr_dict)
			curr_dict = {}

	def __repr__(self):
		""" developer representation of this object """
		return u'HistData_detail(' + repr(self._values_list) + u')'


class HistData_compact(_Mylist):
	""" from DMS: optional history data in compact format """

	def __init__(self, histobj_list):
		super(HistData_compact, self).__init__()
		# internal storage: list of tuples (timestamp, value)
		self._values_list = []

		for histobj in histobj_list:
			# info: dictionary items() method returns a list of (key, value) tuples...
			stamp_str, value = histobj.items()[0]

			# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
			# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
			try:
				stamp = dateutil.parser.parse(stamp_str)
			except ValueError:
				# something went wrong, conversion into a datetime.datetime() object isn't possible
				logger.exception('constructor of HistData_compact(): ERROR: timestamp in current response could not get parsed as valid datetime.datetime() object!')
				stamp = None

			curr_tuple = (stamp, value)
			self._values_list.append(curr_tuple)

	def __repr__(self):
		""" developer representation of this object """
		return u'HistData_compact(' + repr(self._values_list) + u')'


class Changelog_Protocol(_Mylist):
	""" from DMS: optional protocol data about datapoint """

	_fields = (u'path',
	           u'stamp',
	           u'text')
	def __init__(self, obj_list):
		super(Changelog_Protocol, self).__init__()
		# internal storage: list of dictionarys

		for obj in obj_list:
			curr_dict = {}
			for field in Changelog_Protocol._fields:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						curr_dict[field] = dateutil.parser.parse(obj[field])
					except ValueError:
						# something went wrong, conversion into a datetime.datetime() object isn't possible
						logger.exception('constructor of Changelog_Protocol(): ERROR: timestamp in current response could not get parsed as valid datetime.datetime() object!')
						curr_dict[field] = None
				elif field == u'path':
					# path is optional when only one datapoint was requested
					if u'path' in obj:
						curr_dict[field] = obj[field]
					else:
						curr_dict[field] = None
				else:
					# other fields are string, currently no special treatment
					try:
						curr_dict[field] = obj[field]
					except KeyError:
						# something went wrong, a mandatory field is missing...
						logger.exception('constructor of Changelog_Protocol(): ERROR: mandatory field "' + field + '" is missing in current response!')
						# argument was not in response =>setting default value
						curr_dict[field] = None
			# save current dict, begin a new one
			self._values_list.append(curr_dict)
			curr_dict = {}

	def __repr__(self):
		""" developer representation of this object """
		return u'Changelog_Protocol(' + repr(self._values_list) + u')'


class Changelog_Alarm(Changelog_Protocol):
	""" from DMS: optional changelog & alarm data about datapoint """

	_fields = (u'state',
	           u'priority',
	           u'priorityBACnet',
	           u'alarmGroup',
	           u'alarmCollectGroup',
	           u'siteGroup',
	           u'screen')

	def __init__(self, obj_list):
		super(Changelog_Alarm, self).__init__(obj_list)
		# internal storage: list of dictionarys

		# looping again through list of objects for alarm data,
		# appending additional key/value pairs into internal list of dictionarys
		for idx, obj in enumerate(obj_list):
			curr_dict = {}
			for field in Changelog_Alarm._fields:
				if field in [u'priority', u'priorityBACnet', u'alarmGroup', u'alarmCollectGroup', u'siteGroup']:
					# values as numbers
					curr_dict[field] = int(obj[field])
				elif field == u'screen':
					# scada screen name is optional
					if u'screen' in obj:
						curr_dict[field] = obj[field]
					else:
						curr_dict[field] = None
				else:
					# other fields are string, currently no special treatment
					try:
						curr_dict[field] = obj[field]
					except KeyError:
						# something went wrong, a mandatory field is missing...
						logger.exception('constructor of Changelog_Alarm(): ERROR: mandatory field "' + field + '" is missing in current response!')
						# argument was not in response =>setting default value
						curr_dict[field] = None
			# save current dict (combine it into existing one already filled by superclass)
			self._values_list[idx].update(curr_dict)
			# begin a new one
			curr_dict = {}

	def __repr__(self):
		""" developer representation of this object """
		return u'Changelog_Alarm(' + repr(self._values_list) + u')'




class _Response(object):
	""" all common response fields """

	# inherit from abstract class "Mapping" for getting dictionary-interface
	# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
	# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
	# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )

	# string constants
	CODE_OK = u'ok'
	CODE_NOPERM = u'no perm'
	CODE_NOTFOUND = u'not found'
	CODE_ERROR = u'error'

	# these fields are common for all responses
	_fields = (u'code', )

	def __init__(self, **kwargs):
		# this variable has to be declared in child class...
		for field in _Response._fields:
			try:
				self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# something went wrong, a mandatory field is missing... =>set error code
				logger.exception('constructor of CmdResponse(): ERROR: mandatory field "' + field + '" is missing in current response!')
				self._values_dict[u'code'] = _Response.CODE_ERROR

		# some sanity checks
		if not self._values_dict[u'code'] in (_Response.CODE_OK,
		                                      _Response.CODE_NOPERM,
		                                      _Response.CODE_NOTFOUND,
		                                      _Response.CODE_ERROR):
			logger.error('constructor of CmdResponse(): ERROR: field "code" in current response contains unknown value "' + repr(self._values_dict[u'code']) + '"!')
			# FIXME: what should we do if response code is unknown? Perhaps it's an unsupported JSON Data Exchange protocol?

		if kwargs:
			logger.warn('constructor of CmdResponse(): WARNING: these fields in current response are unknown, perhaps unsupported JSON Data Exchange protocol: "' + repr(kwargs) + '"!')


class RespGet(_Mydict, _Response):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'hasChild',
	           u'stamp',
	           u'extInfos',
	           u'message',
	           u'histData',
	           u'changelog',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespGet._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs.pop(field))
					except:
						self._values_dict[field] = None
				elif field == u'extInfos':
					extInfos_dict = kwargs.pop(field)
					self._values_dict[field] = ExtInfos(**extInfos_dict)
				elif field == u'histData':
					histData_list = kwargs.pop(field)
					if histData_list:
						# parse response as "detail" or "compact" format
						# according to documentation: default is "compact"
						# =>checking first JSON-object if it contains "stamp" for choosing right parsing
						if not u'stamp' in histData_list[0]:
							# assuming "compact" format
							self._values_dict[field] = HistData_compact(histData_list)
						else:
							# assuming "detail" format
							self._values_dict[field] = HistData_detail(histData_list)
					else:
						# histData is an empty list, we have no trenddata...
						self._values_dict[field] = []
				elif field == u'changelog':
					obj_list = kwargs.pop(field)
					if obj_list:
						# parse response as "protocol" or "alarm" format
						# =>checking first JSON-object if it contains "state" for choosing right parsing
						if u'state' in obj_list[0]:
							# datapoint has protocol + alarm
							self._values_dict[field] = Changelog_Alarm(obj_list)
						else:
							# datapoint has only protocol
							self._values_dict[field] = Changelog_Protocol(obj_list)
					else:
						# changelog is an empty list, we have no changelogs...
						self._values_dict[field] = []
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespGet() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespGet(' + repr(self._values_dict) + u')'


class RespSet(_Mydict, _Response):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespSet._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs.pop(field))
					except:
						self._values_dict[field] = None
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespSet() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespSet(' + repr(self._values_dict) + u')'


class RespRen(_Mydict, _Response):
	_fields = (u'path',
	           u'newPath',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespRen._fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespRen() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespRen(' + repr(self._values_dict) + u')'


class RespDel(_Mydict, _Response):
	_fields = (u'path',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespDel._fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespDel() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespDel(' + repr(self._values_dict) + u')'



class RespSub(_Mydict, _Response):
	_fields = (u'path',
	           u'query',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespSub._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs.pop(field))
					except:
						self._values_dict[field] = None
				elif field == u'query':
					# handle optional "query" object
					query_dict = kwargs.pop(field)
					try:
						self._values_dict[field] = Query(**query_dict)
					except ValueError as ex:
						logger.warn('RespSub(): constructor of Query() found unknown fields in current response, perhaps unsupported JSON Data Exchange protocol!')
						raise ex
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespSub() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespSub(' + repr(self._values_dict) + u')'


class RespUnsub(_Mydict, _Response):
	_fields = (u'path',
	           u'query',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespUnsub._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs.pop(field))
					except:
						self._values_dict[field] = None
				elif field == u'query':
					# handle optional "query" object
					query_dict = kwargs.pop(field)
					try:
						self._values_dict[field] = Query(**query_dict)
					except ValueError as ex:
						logger.warn('RespUnsub(): constructor of Query() found unknown fields in current response, perhaps unsupported JSON Data Exchange protocol!')
						raise ex
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespUnsub() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespUnsub(' + repr(self._values_dict) + u')'


class RespChangelogGetGroups(_Mydict, _Response):
	_fields = (u'groups',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespChangelogGetGroups._fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespChangelogGetGroups() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespChangelogGetGroups(' + repr(self._values_dict) + u')'


class RespChangelogRead(_Mydict, _Response):
	_fields = (u'group',
	           u'changelog',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		_Mydict.__init__(self, **kwargs)

		for field in RespChangelogRead._fields:
			try:
				if field == u'changelog':
					obj_list = kwargs.pop(field)
					if obj_list:
						# parse response as "protocol" format (we don't have to care for "alarm" format)
						# datapoint has only protocol
						self._values_dict[field] = Changelog_Protocol(obj_list)
					else:
						# changelog is an empty list, we have no changelogs...
						self._values_dict[field] = []
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs.pop(field)
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('RespChangelogRead() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		# (explicit calling _Response's constructor, because "super" would call "_Mydict"...)
		_Response.__init__(self, **kwargs)

	def __repr__(self):
		""" developer representation of this object """
		return u'RespChangelogRead(' + repr(self._values_dict) + u')'





class SubscriptionAE(axel.Event):
	''' mapping python callbacks to DMS events '''
	# extending "axel events" for events handling https://github.com/axel-events/axel
	# =>caller has to attach his callback functions to this object.
	# (Factory for this object is in DMSClient.get_dp_subscription())

	def __init__(self, msghandler, sub_response):
		self._msghandler = msghandler
		self.sub_response = sub_response    # original DMS response (instance of RespSub())

		# details about constructor of Event():
		# https://github.com/axel-events/axel/blob/master/axel/axel.py
		# (setting threads>0 means synchronous execution of eventhandler,
		#  this way we get success or failure data in _MessageHandler.handle()
		# details about traceback:
		#  https://pythonhosted.org/axel/
		#  https://docs.python.org/2/library/sys.html
		super(SubscriptionAE, self).__init__(threads=1,
		                                     exc_info=True,
		                                     traceback=False)

	def get_tag(self):
		return self.sub_response[u'tag']

	def update(self, **kwargs):
		# FIXME for performance: detect changes in "query" and "event",
		# if changed, then overwrite subscription in DMS,
		# else resubscribe (currently we send request in every case...)
		# FIXME: how to report errors to caller?

		# reuse "path" and "tag", then DMS will replace subscription
		assert not u'path' in kwargs, u'DMS uses path and tag for identifying subscription. Changing is not allowed!'
		assert not u'tag' in kwargs, u'DMS uses path and tag for identifying subscription. Changing is not allowed!'
		if u'path' in kwargs:
			del(kwargs[u'path'])
		kwargs[u'tag'] = self.sub_response[u'tag']
		resp = self._msghandler.dp_sub(path=self.sub_response[u'path'], **kwargs)


	def unsubscribe(self):
		# FIXME: how to report errors to caller?
		resp = self._msghandler._dp_unsub(path=self.sub_response[u'path'],
		                                  tag=self.sub_response[u'tag'])
		self._msghandler.del_subscription(self)


	def __del__(self):
		# destructor: being friendly: unsubscribe from DMS for stopping events
		try:
			# on shutting down Python program this could raise an TypeError
			self.unsubscribe()
		except TypeError:
			pass

	def __repr__(self):
		""" developer representation of this object """
		return u'SubscriptionAE(self.sub_response=' + repr(self.sub_response) + u')'



class DMSEvent(_Mydict):
	# string constants
	CODE_CHANGE = u'onChange'
	CODE_SET = u'onSet'
	CODE_CREATE = u'onCreate'
	CODE_RENAME = u'onRename'
	CODE_DELETE = u'onDelete'

	_fields = (u'code',
	           u'path',
	           u'newPath',
	           u'trigger',
	           u'value',
	           u'type',
	           u'stamp',
	           u'tag')

	def __init__(self, **kwargs):
		super(DMSEvent, self).__init__()

		for field in DMSEvent._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs[field])
					except:
						self._values_dict[field] = None
				elif field == u'code':
					# attention: difference to other commands: "code" in DMS-events means trigger of this event
					self._values_dict[field] = u'' + kwargs[field]
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				logger.debug('DMSEvent() constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# sanity check:
		if not self._values_dict[u'code'] in (DMSEvent.CODE_CHANGE,
		                                      DMSEvent.CODE_SET,
		                                      DMSEvent.CODE_CREATE,
		                                      DMSEvent.CODE_RENAME,
		                                      DMSEvent.CODE_DELETE):
			logger.error('constructor of DMSEvent(): ERROR: field "code" in current response contains unknown value "' + repr(self._values_dict[u'code']) + '"!')

	def __repr__(self):
		""" developer representation of this object """
		return u'DMSEvent(' + repr(self._values_dict) + u')'



class _MessageHandler(object):
	def __init__(self, dmsclient_obj, whois_str, user_str, subAE_queue):
		# backreference for sending messages
		self._dmsclient = dmsclient_obj
		self._whois_str = whois_str
		self._user_str = user_str

		# Queue for firing Subscription-axel.Events
		self._subAE_queue = subAE_queue

		# thread safety for shared dictionaries =>we want to be on the safe side!
		# (documentation: https://docs.python.org/2/library/threading.html#lock-objects )
		# http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm
		# https://stackoverflow.com/questions/8487673/how-would-you-make-this-python-dictionary-thread-safe

		# dict for pending responses (key: cmd-tag, value: list of CmdResponse-objects)
		# =>None means request is sent, but answer is not yet here
		self._pending_response_dict = {}
		self._pending_response_lock = threading.Lock()


		# dict for DMS-events (key: tag, value: SubscriptionAE-objects)
		# =>DMS-event will fire our python event
		# (our chosen tag for DMS subscription command is unique across all events related to this subscription)
		self._subscriptionAE_objs_dict = {}
		self._subscriptionAE_objs_lock = threading.Lock()


		# object for assembling response lists
		# (when one "get" command produces more than one response)
		class Current_response(object):
			def __init__(self):
				self.msg_tag = u''
				self.resp_list = []
			def clear(self):
				self.__init__()
		self._curr_response = Current_response()

	# object for "busy-waiting" mechanism in responses
	class _Response_container(object):
		def __init__(self):
			self.isAvailable = threading.Event()
			self.response_list = []


	def dp_get(self, path, timeout=TIMEOUT, **kwargs):
		""" read datapoint value(s) """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(_CmdGet(msghandler=self, path=path, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_get(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_set(self, path, value, timeout=TIMEOUT, **kwargs):
		""" write datapoint value(s) """
		# Remarks: datatype in DMS is taken from datatype of "value" (field "type" is optional)
		# Remarks: datatype STR: 80 chars could be serialized by DMS into Promos.dms file for permament storage.
		#                        =>transmission of 64kByte text is possible (total size of JSON request),
		#                          this text is volatile in RAM of DMS.

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdSet(msghandler=self, path=path, value=value, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_set(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_del(self, path, recursive, timeout=TIMEOUT, **kwargs):
		""" delete datapoint(s) """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdDel(msghandler=self, path=path, recursive=recursive, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_del(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_ren(self, path, newPath, timeout=TIMEOUT, **kwargs):
		""" rename datapoint(s) """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdRen(msghandler=self, path=path, newPath=newPath, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_ren(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_sub(self, path, timeout=TIMEOUT, **kwargs):
		""" subscribe monitoring of datapoints(s) """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdSub(msghandler=self, path=path, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_ren(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')



	def _dp_unsub(self, path, tag, timeout=TIMEOUT, **kwargs):
		""" unsubscribe monitoring of datapoint(s) """
		# =>called by Subscription.unsubscribe()
		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdUnsub(msghandler=self, path=path, tag=tag))
		self._send_frame(req)

		try:
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in dp_ren(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def changelog_GetGroups(self, timeout=TIMEOUT, **kwargs):
		""" get list of available changelog groups """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdChangelogGetGroups(msghandler=self, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in changelog_GetGroups(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def changelog_Read(self, group, start, timeout=TIMEOUT, **kwargs):
		""" get protocol entries in given changelog group """

		req = _Request(whois=self._whois_str, user=self._user_str).addCmd(
			_CmdChangelogRead(msghandler=self, group=group, start=start, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			logger.error('error in changelog_Read(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')





	def handle(self, msg):
		payload_dict = json.loads(msg.decode('utf8'))

		try:
			# message handler
			for resp_type, resp_cls in [(u'get', RespGet),
			                            (u'set', RespSet),
			                            (u'rename', RespRen),
			                            (u'delete', RespDel),
			                            (u'subscribe', RespSub),
			                            (u'unsubscribe', RespUnsub),
			                            (u'changelogGetGroups', RespChangelogGetGroups),
			                            (u'changelogRead', RespChangelogRead)]:
				if resp_type in payload_dict:
					# handling responses to command

					# preparation: reset response list
					self._curr_response.clear()

					# special treatment: when whole frame is tagged with helper-dictionary,
					# then we need to copy it back to all tagless commands
					# (I don't know why not all commands have an own tag...?!?)
					# =>DMS must return us same helper-dictionary as built in _Request.as_dict(),
					#   and all tagless commands in same order (array in JSON must keep ordering)
					if resp_type == _CmdChangelogGetGroups.CMD_TYPE:
						for idx, resp_obj in enumerate(payload_dict[resp_type]):
							resp_obj[u'tag'] = payload_dict[u'tag'][_CmdChangelogGetGroups.CMD_TYPE][idx]

					for response in payload_dict[resp_type]:
						if u'tag' in response:
							curr_tag = response[u'tag']

							if curr_tag == self._curr_response.msg_tag:
								# appending to current list
								self._curr_response.resp_list.append(resp_cls(**response))
							else:
								# found a new tag =>save old list and create a new one
								if self._curr_response.msg_tag and self._curr_response.resp_list:
									# need to save last responses
									if curr_tag in self._pending_response_dict:
										logger.debug('message handler: found different tags in response. Storing response for other thread...')
										with self._pending_response_lock:
											self._pending_response_dict[curr_tag].response_list = self._curr_response.resp_list
											# inform other thread
											self._pending_response_dict[curr_tag].isAvailable.set()
									else:
										logger.warn('message handler: ignoring unexpected response "' + repr(self._curr_response.resp_list) + '"...')
								# begin of new response list
								self._curr_response.msg_tag = curr_tag
								self._curr_response.resp_list = [resp_cls(**response)]

						else:
							logger.warn('message handler: ignoring untagged response "' + repr(response) + '"...')


					# storing collected list for other thread
					logger.debug('message handler: storing of response for other thread...')
					with self._pending_response_lock:
						self._pending_response_dict[curr_tag].response_list = self._curr_response.resp_list
						# inform other thread
						self._pending_response_dict[curr_tag].isAvailable.set()
		except Exception as ex:
			# help from https://stackoverflow.com/questions/5191830/best-way-to-log-a-python-exception
			logger.exception("exception occurred in _MessageHandler.handle()")


		if u'event' in payload_dict:
			# handling DMS-events
			for event in payload_dict[u'event']:
				# trigger Python event
				try:
					event_obj = DMSEvent(**event)
					with self._subscriptionAE_objs_lock:
						subAE = self._subscriptionAE_objs_dict[event_obj.tag]

					# via background thread: firing Python callback functions registered in axel.Event()
					# (result is tuple of tuples: https://github.com/axel-events/axel/blob/master/axel/axel.py#L122 )
					if len(subAE) > 0:
						logger.debug('_MsgHandler.handle(): event-firing on SubscriptionAE object [DMS-key="' + event_obj.path + '" / tag=' + event_obj.tag + ']')
						self._subAE_queue.put((subAE, event_obj))
					else:
						logger.info('_MsgHandler.handle(): SubscriptionsAE object is empty, suppressing firing of axel.Event...')
				except AttributeError:
					logger.exception("exception in _MessageHandler.handle(): DMS-event seems corrupted")
				except KeyError:
					logger.exception("exception in _MessageHandler.handle(): DMS-event is not registered")
				except Exception:
					logger.exception("exception in _MessageHandler.handle() during handling of DMS-event")



	def _send_frame(self, frame_obj):
		# send whole request

		# create valid JSON
		# (according to https://docs.python.org/2/library/json.html : default encoding is UTF8)
		req_str = json.dumps(frame_obj.as_dict())
		self._dmsclient._send_message(req_str)

	def _busy_wait_for_response(self, tag, timeout):
		while not tag in self._pending_response_dict:
			# FIXME: hmm, sometimes we have a race condition... Now we do this ugly busy wait loop...
			# this tag HAS to be in dictionary, or we have a problem...
			time.sleep(SLEEP_TIMEBASE)
		with self._pending_response_lock:
			isAvailable = self._pending_response_dict[tag].isAvailable
		if isAvailable.wait(timeout=timeout):
			with self._pending_response_lock:
				curr_container = self._pending_response_dict.pop(tag)
			return curr_container.response_list
		else:
			# no response in given timeframe... Should we return an exception?
			raise Exception('_MessageHandler.DMS_busy_wait_for_response(): got no response within ' + str(timeout) + ' seconds...')

	def add_subscription(self, subAE):
		with self._subscriptionAE_objs_lock:
			self._subscriptionAE_objs_dict[subAE.get_tag()] = subAE

	def del_subscription(self, subAE):
		with self._subscriptionAE_objs_lock:
			del(self._subscriptionAE_objs_dict[subAE.get_tag()])


	def prepare_tag(self, curr_tag=None):
		# register message tag for identification of responses
		# =>attention: commands "subscribe" and "unsubscribe" need to reuse tag of their subscription!

		if not curr_tag:
			# generating random and nearly unique message tags
			# (see https://docs.python.org/2/library/uuid.html )
			curr_tag = str(uuid.uuid4())

		with self._pending_response_lock:
			self._pending_response_dict[curr_tag] = _MessageHandler._Response_container()
		return curr_tag



class _SubscriptionAE_Dispatcher(threading.Thread):
	""" firing Subscription-Axel.Events in a separated thread """
	# =>if user adds an infinitly running function, then only the event-monitoring is blocked,
	#   instead of blocking whole _MessageHandler.handle() function
	# =>this way a users callback function should be able to send WebSocket messages
	#   (ealier we had a deadlock sending a message while processing _cb_on_message() function)
	# FIXME: we should implement a hard timeout when synchronous execution of a fired SubscriptionAE() uses too much time
	# FIXME: we use a "polling queue", it's a waste of CPU time when no datapoint subscription is active...

	def __init__(self, event_q):
		self._event_q = event_q
		self.keep_running = True
		super(_SubscriptionAE_Dispatcher, self).__init__()

	def run(self):
		# "polling queue" based on code from http://stupidpythonideas.blogspot.ch/2013/10/why-your-gui-app-freezes.html
		logger.debug('_SubscriptionAE_Dispatcher.run(): background thread for firing axel.Events() is running...')
		while self.keep_running:
			try:
				subAE, event_obj = self._event_q.get(block=False)
			except queue.Empty:
				# give other threads some CPU time...
				time.sleep(SLEEP_TIMEBASE)
			except Exception as ex:
				logger.error('_SubscriptionAE_Dispatcher.run(): got exception ' + repr(ex))
			else:
				# (this is an optional else clause when no exception occured)
				logger.debug('_SubscriptionAE_Dispatcher.run(): event-firing on SubscriptionAE object [DMS-key="' + event_obj.path + '" / tag=' + event_obj.tag + ']')
				result = subAE(event_obj)
				# FIXME: how to inform caller about exceptions while executing his callbacks?
				for idx, res in enumerate(result):
					if res[0] == None:
						logger.debug('_SubscriptionAE_Dispatcher.run(): event-firing on SubscriptionAE object: asynchronously started callback' + str(idx) + ': handler=' + repr(res[2]))
					else:
						logger.debug('_SubscriptionAE_Dispatcher.run(): event-firing on SubscriptionAE object: synchronous callback' + str(idx) + ': success=' + str(res[0]) + ', result=' + str(res[1]) + ', handler=' + repr(res[2]))

					# since we process axel.Events synchronously (this could be a bottleneck or risk of blocking!!!) we get success or failure data
					# =>look in constructor of SubscriptionAE() for details
					if res[0] == False:
						# example: res[1] without traceback: (<type 'exceptions.TypeError'>, TypeError("cannot concatenate 'str' and 'int' objects",))
						#          =>when traceback=True, then ID of traceback object is added to the part above.
						#            Assumption: traceback is not needed. It would be useful when debugging client code...
						logger.error('_SubscriptionAE_Dispatcher.run(): event-firing on SubscriptionAE object: synchronous callback' + str(idx) + ' failed: ' + str(res[1]) + ' [handler=' + repr(res[2]) + ']')



class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int
		self._subAE_queue = queue.Queue()
		self._msghandler = _MessageHandler(dmsclient_obj=self, whois_str=whois_str, user_str=user_str, subAE_queue=self._subAE_queue)

		# thread synchronisation flag for Websocket connection state
		# (documentation: https://docs.python.org/2/library/threading.html#event-objects )
		self.ready_to_send = threading.Event()

		# based on example on https://github.com/websocket-client/websocket-client
		# and comments in sourcecode:
		#   https://github.com/websocket-client/websocket-client/blob/master/websocket/_app.py
		#   https://github.com/websocket-client/websocket-client/blob/master/websocket/_core.py
		#websocket.enableTrace(True)
		ws_URI = u"ws://" + self._dms_host_str + u':' + str(self._dms_port_int) + DMS_BASEPATH
		self._ws = websocket.WebSocketApp(ws_URI,
		                            on_message = self._cb_on_message,
		                            on_error = self._cb_on_error,
		                            on_open = self._cb_on_open,
		                            on_close = self._cb_on_close)
		# executing WebSocket eventloop in background
		self._ws_thread = thread.start_new_thread(self._ws.run_forever, ())
		# FIXME: how to return caller a non-reachable WebSocket server?
		logger.info("WebSocket connection will be established in background...")

		# background thread for firing Subscription-axel.Events
		self._subAE_disp_thread = _SubscriptionAE_Dispatcher(event_q=self._subAE_queue)


	# API
	def dp_get(self, path, timeout=TIMEOUT, **kwargs):
		""" read datapoint value(s) """
		return self._msghandler.dp_get(path, timeout=timeout, **kwargs)

	def dp_set(self, path, timeout=TIMEOUT, **kwargs):
		""" write datapoint value(s) """
		return self._msghandler.dp_set(path, timeout=timeout, **kwargs)

	def dp_del(self, path, recursive, timeout=TIMEOUT, **kwargs):
		""" delete datapoint(s) """
		return self._msghandler.dp_del(path, recursive, timeout=timeout, **kwargs)

	def dp_ren(self, path, newPath, timeout=TIMEOUT, **kwargs):
		""" rename datapoint(s) """
		return self._msghandler.dp_ren(path, newPath, timeout=timeout, **kwargs)

	def get_dp_subscription(self, path, timeout=TIMEOUT, **kwargs):
		""" subscribe monitoring of datapoints(s) """
		# FIXME: now we care only the first response... is this ok in every case?
		response = self._msghandler.dp_sub(path, timeout=timeout, **kwargs)[0]
		if DEBUGGING:
			print('DEBUGGING: get_dp_subscription(): type(response)=' + repr(type(response)) + ', repr(response)=' + repr(response))
		if response["code"] == u'ok':
			# DMS accepted subscription
			subAE = SubscriptionAE(msghandler=self._msghandler, sub_response=response)
			self._msghandler.add_subscription(subAE=subAE)
			return subAE
		else:
			raise Exception(u'DMS ignored subscription of "' + path + '" with error "' + response.code + '"!')

	def changelog_GetGroups(self, timeout=TIMEOUT, **kwargs):
		""" get list of available changelog groups """
		return self._msghandler.changelog_GetGroups(timeout=timeout, **kwargs)

	def changelog_Read(self, group, start, timeout=TIMEOUT, **kwargs):
		""" get protocol entries in given changelog group """
		return self._msghandler.changelog_Read(group, start, timeout=timeout, **kwargs)

	def _send_message(self, msg):
		if not self.ready_to_send.is_set():
			logger.warn('DMSClient._send_message(): WebSocket not ready for sending, giving it more time for connection establishment...')
		if self.ready_to_send.wait(timeout=60):     # timeout in seconds
			logger.debug('DMSClient._send_message(): sending request "' + repr(msg) + '"')
			self._ws.send(msg)
		else:
			logger.error('DMSClient._send_message(): ERROR WebSocket not ready for sending request "' + repr(msg) + '"')
			raise IOError('DMSClient._send_message(): ERROR WebSocket not ready for sending request')
		# FIXME: how should we inform user about WebSocket problems?
		# FIXME: when DMS is not reachable then user gets an IOError after the self.ready_to_send.wait()-timeout,
		#        but during this wait state the websocket client thread has died much earlier with callback "on_close"...
		#        =>we should interrupt this waiting earlier... we should do a better thread synchronization....
		# what about raw websocket-exceptions https://github.com/websocket-client/websocket-client/blob/master/websocket/_exceptions.py


	def _cb_on_message(self, ws, message):
		logger.debug("DMSClient: websocket callback _on_message(): " + message)
		self._msghandler.handle(message)

	def _cb_on_error(self, ws, error):
		logger.error("DMSClient: websocket callback _on_error(): " + error)

	def _cb_on_open(self, ws):
		logger.info("DMSClient: websocket callback _on_open(): WebSocket connection is established.")
		self._subAE_disp_thread.start()
		self.ready_to_send.set()

	def _cb_on_close(self, ws):
		logger.info("DMSClient: websocket callback _on_close(): server closed connection =>shutting down own client thread")
		self._subAE_disp_thread.keep_running = False
		self.ready_to_send.clear()
		self._exit_ws_thread()

	def __del__(self):
		"""" closing websocket connection on object destruction """
		self._ws.close()
		time.sleep(1)
		self._exit_ws_thread()

	def _exit_ws_thread(self):
		# FIXME: this function is never called from callbacks... But why?
		logger.debug("DMSClient._exit_ws_thread(): exiting websocket thread...")
		self._ws.keep_running = False

	def _exit_subAE_thread(self):
		logger.debug("DMSClient._exit_subAE_thread(): exiting subscriptionAE-dispatcher thread...")
		self._subAE_disp_thread.keep_running = False

	# trying to implement Context Manager.
	# help from https://jeffknupp.com/blog/2016/03/07/python-with-context-managers/
	#           https://gist.github.com/bradmontgomery/4f4934893388f971c6c5
	#           https://docs.python.org/2/reference/datamodel.html#object.__exit__
	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self._exit_ws_thread()
		self._exit_subAE_thread()
		if traceback:
			logger.error("DMSClient.__exit__(): type: {}".format(exc_type))
			logger.error("DMSClient.__exit__(): value: {}".format(exc_value))
			logger.error("DMSClient.__exit__(): traceback: {}".format(traceback))



if __name__ == '__main__':


	#test_set = set(['ws'] + range(18))
	#test_set = set(['ws', 11])
	test_set = set(['contextmanager'])

	if 'contextmanager' in test_set:
		with DMSClient(u'test', u'user') as myClient:
			print('\nTesting creation of Request command:')
			print('"get":')
			response = myClient.dp_get(path="System:Time")
			print('response to our request: ' + repr(response))
			print('\tresponse[0].value=' + repr(response[0].value))


	if 'ws' in test_set:
		myClient = DMSClient(u'test', u'user')
		#myClient = DMSClient(u'test', u'user', dms_host_str="127.0.0.1", dms_port_int=1234)
		print('\n=>WebSocket connection runs now in background...')

		# while True:
		# 	time.sleep(1)
		# 	print('sending TESTMSG...')
		# 	myClient._send_message(TESTMSG)

	if 0 in test_set:
		print('\nTesting single classes....')
		myobj = Query(regExPath=u'.*')
		print('myobj: ' + repr(myobj) + ', as string: ' + str(myobj) + ', has type ' + str(type(myobj)))
		print('myobj["regExPath"]= ' + repr(myobj["regExPath"]))


	if 1 in test_set:
		print('\nTesting creation of Request command:')
		print('"get":')
		attribute_list = list(_Response._fields) + list(RespGet._fields)
		for x in range(3):
			response = myClient.dp_get(path="System:Time")
			print('response to our request: ' + repr(response))
			# test of magic method "__getattr__()" implemented in class _Mydict()
			# =>user simply can write "response[0].code" or the ususal "response[0].['code']"
			for name in attribute_list:
				print('\tresponse[0].' + name + ' =\t' + repr(getattr(response[0], name)))
			print('*' * 20)

	if 2 in test_set:
		print('\n\nNow doing loadtest:')
		DEBUGGING = False
		nof_tests = 1000
		for x in xrange(nof_tests):
			response = myClient.dp_get(path="System:Time")
		print('We have done ' + str(nof_tests) + ' requests. :-) Does it still work?')
		DEBUGGING = True
		print('*' * 20)
		response = myClient.dp_get(path="System:Time")
		print('response to our request: ' + repr(response))
		print('*' * 20)

	if 3 in test_set:
		print('\nNow testing query function:')
		print('\twithout query: ' + repr(myClient.dp_get(path="")))
		print('\twith query: ' + repr(myClient.dp_get(path="",
		                                              query=Query(regExPath=".*", maxDepth=1)
		                                              )
		                              )
		      )


	if 4 in test_set:
		print('\nTesting retrieving HistData:')
		DEBUGGING = True
		response = myClient.dp_get(path="MSR01:Ala101:Output_Lampe",
		                           histData=HistData(start="2017-12-05T19:00:00,000+02:00",
		                                             #end="2017-12-05T19:35:00,000+02:00",
		                                             #format="compact",
		                                             format="detail",
		                                             interval=0
		                                             ),
		                           showExtInfos=INFO_ALL
		                           )
		print('response: ' + repr(response))

	if 5 in test_set:
		print('\nTesting writing of DMS datapoint:')
		response = myClient.dp_set(path="MSR01:Test_str",
		                           #value=80*"x",
		                           value="abc",
		                           create=True)
		print('response: ' + repr(response))

	if 6 in test_set:
		print('\nTesting retrieving of value from test no.5:')
		print('"get":')
		response = myClient.dp_get(path="MSR01:Test_str")
		print('response to our request: \n' + repr(response))

	if 7 in test_set:
		print('\nTesting writing of DMS datapoint:')
		response = myClient.dp_set(path="MSR01:Test_int",
		                           value=123,
		                           create=True)
		print('response: ' + repr(response))

	if 8 in test_set:
		print('\nTesting renaming of DMS datapoint:')
		response = myClient.dp_ren(path="MSR01:Test_int",
		                           newPath="MSR01:Test_int2")
		print('response: ' + repr(response))

	if 9 in test_set:
		print('\nTesting deletion of DMS datapoint:')
		response = myClient.dp_del(path="MSR01:Test_int2",
		                           recursive=False)
		print('response: ' + repr(response))

	if 10 in test_set:
		print('\nTesting retrieving of whole BMO:')
		print('"get":')
		for x in range(3):
			response = myClient.dp_get(path="MSR01:And102",
			                           showExtInfos=INFO_ALL,
			                           query=Query(maxDepth=-1),
			                           )
			print('response to our request: ' + repr(response))
			print('*' * 20)

	if 11 in test_set:
		DEBUGGING = False
		dms_blinker_str = "System:Blinker:Blink1.0"
		print('Testing monitoring of DMS datapoint "' + dms_blinker_str + '"')
		sub = myClient.get_dp_subscription(path=dms_blinker_str,
		                                   event=ON_ALL,
		                                   query=Query(maxDepth=-1))
		print('got Subscription object: ' + repr(sub))
		print('adding callback function:')
		def myfunc(event):
			print('\t\tmyfunc(): GOT EVENT: ' + repr(event))
		sub += myfunc

		def myfunc2(event):
			# testing logging of exception in callback function: TypeError("cannot concatenate 'str' and 'int' objects",)
			print('\t\tmyfunc2(): GOT EVENT: ' + repr(event) + 1)
		sub += myfunc2

		print('waiting some seconds while callback should getting fired in background...')
		for x in range(30):
			time.sleep(0.1)

		print('changing eventfilter in DMS subscription...')
		sub.update(event='*')
		for x in range(30):
			time.sleep(0.1)

		print('waiting some seconds with active DMS subscription but without Python callbackfunction...')
		sub -= myfunc
		sub -= myfunc2
		for x in range(30):
			time.sleep(0.1)

		print('unsubscription test...')
		sub.unsubscribe()

		print('waiting some seconds while no new event should fire...')
		for x in range(30):
			time.sleep(0.1)

		print('Done.')



	if 12 in test_set:
		DEBUGGING = False
		dms_path_str = ""
		print('Testing monitoring of DMS datapoint "' + dms_path_str + '"')
		sub = myClient.get_dp_subscription(path=dms_path_str,
		                                        event=ON_CREATE + ON_DELETE,
		                                        query=Query(maxDepth=-1))
		print('got Subscription object: ' + repr(sub))
		print('adding callback function:')
		def myfunc(event):
			print('\t\tGOT EVENT: ' + repr(event))
		sub += myfunc

		print('waiting some seconds while callback should getting fired in background...')
		for x in range(100):
			time.sleep(0.1)

		print('unsubscription test...')
		sub.unsubscribe()
		time.sleep(2)

		print('Done.')


	if 13 in test_set:
		print('\nTesting retrieving Changelog:')
		DEBUGGING = True
		response = myClient.dp_get(path="MSR01:Ala101:Hand",
		                           changelog=Changelog(start="2017-12-05T19:00:00,000+02:00",
		                                               #end="2017-12-05T20:30:00,000+02:00"
		                                               )
		                           )
		print('response: ' + repr(response))


	if 14 in test_set:
		print('\nTesting retrieving Changelog of alarm datapoint:')
		DEBUGGING = True
		response = myClient.dp_get(path="MSR01:Bat101:SM_Err",
		                           changelog=Changelog(start="2017-12-05T19:00:00,000+02:00",
		                                               #end="2017-12-05T20:30:00,000+02:00"
		                                               )
		                           )
		print('response: ' + repr(response))


	if 15 in test_set:
		print('\nTesting retrieving ExtInfos:')
		DEBUGGING = True
		response = myClient.dp_get(path="MSR01:Ala101:Hand",
		                           showExtInfos=INFO_ALL
		                           )
		print('response: ' + repr(response))


	if 16 in test_set:
		print('\nTesting retrieving available changelog groups:')
		DEBUGGING = True
		response = myClient.changelog_GetGroups()
		print('response: ' + repr(response))



	if 17 in test_set:
		print('\nTesting retrieving available protocol entries in changelog group:')
		DEBUGGING = True
		response = myClient.changelog_Read(group=u'Hand',
		                                   start="2017-12-05T19:00:00,000+02:00",
		                                   #end="2017-12-10T20:30:00,000+02:00"
		                                   )
		print('response: ' + repr(response))