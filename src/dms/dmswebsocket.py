#!/usr/bin/env python
# encoding: utf-8
"""
dms.dmswebsocket.py

Copyright (C) 2017 Stefan Braun


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

DEBUGGING = True


import json
import time
import uuid
import websocket
import thread
import collections
import dateutil.parser, datetime

# events handling https://github.com/axel-events/axel
# =>installed with pip from https://anaconda.org/pypi/axel
import axel


TESTMSG = (u'{ "get": [ {"path":"System:Time"} ] }')

# duration of one time.sleep() in busy-waiting-loops
TIMEOUT_TIMEBASE = 0.001

# according "ProMoS DMS JSON Data Exchange":
DMS_PORT = 9020             # cleartext HTTP or WebSocket
DMS_HOST = "127.0.0.1"      # local connection: doesn't need authentification
DMS_BASEPATH = "/json_data" # default for HTTP and WebSocket







class _DMSFrame(object):
	def __init__(self):
		pass


class _DMSRequest(_DMSFrame):
	def __init__(self, whois, user):
		self.whois = u'' + whois
		self.user = u'' + user
		self.tag = None # we don't tag the whole request, since we tag all single commands inside request
		# dict of lists, containing all pending commands
		self._cmd_dict = {}
		self._cmd_tags_list = []
		_DMSFrame.__init__(self)

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
		return u'_DMSRequest(' + repr(self.as_dict()) + u')'

	def __str__(self):
		return u'' + str(self.as_dict())



class _DMSCmdGet(object):
	""" one unique "get" request, parsed from **kwargs """

	CMD_TYPE = u'get'

	def __init__(self, msghandler, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.query = {}
		self.histData = {}
		self.showExtInfos = None
		self.tag = msghandler.generate_tag()

		for key in kwargs:
			# parsing "query" object
			val = None
			if key == u'regExPath':
				val = u'' + kwargs[key]
			elif key == u'regExValue':
				val = u'' + kwargs[key]
			elif key == u'regExStamp':
				val = u'' + kwargs[key]
			elif key == u'isType':
				val = u'' + kwargs[key]
			elif key == u'hasHistData':
				val = bool(kwargs[key])
			elif key == u'hasAlarmData':
				val = bool(kwargs[key])
			elif key == u'hasProtocolData':
				val = bool(kwargs[key])
			elif key == u'maxDepth':
				val = int(kwargs[key])

			if val:
				self.query[key] = val

			# parsing "histData" object
			val = None
			if key == u'start' or key == u'end':
				# convert datetime.datetime object to ISO 8601 format
				try:
					val = u'' + kwargs[key].isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + kwargs[key]
			if key == u'interval':
				val = int(kwargs[key])
			if key == u'format':
				val = u'' + kwargs[key]

			if val:
				self.histData[key] = val

			# parsing properties
			if key == u'showExtInfos':
				self.showExtInfos = bool(kwargs[key])

		# checking mandatory fields
		#assert self.path != u'', u'"path" property is mandatory!'  # is null-path allowed?!?
		assert self.histData == {} or u'start' in self.histData, u'field "start" is mandatory when object "histData" is used!'


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.showExtInfos:
			curr_dict[u'showExtInfos'] = self.showExtInfos
		if self.query:
			curr_dict[u'query'] = self.query
		if self.histData:
			curr_dict[u'histData'] = self.histData
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdGet.CMD_TYPE


class _DMSCmdSet(object):
	""" one unique "Set" request, parsed from **kwargs """

	CMD_TYPE = u'set'

	def __init__(self, msghandler, path, value, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.value = value
		self.request = {}
		self.tag = msghandler.generate_tag()

		for key in kwargs:
			# parsing request options
			val = None
			if key == u'create':
				val = bool(kwargs[key])
			elif key == u'type':
				assert kwargs[key] in (u'int', u'double', u'string', u'bool'), u'unexpected type of value!'
				val = u'' + kwargs[key]
			elif key == u'stamp':
				# convert datetime.datetime object to ISO 8601 format
				try:
					val = u'' + kwargs[key].isoformat()
				except AttributeError:
					# now we assume it's already a string
					val = u'' + kwargs[key]

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
		return _DMSCmdSet.CMD_TYPE


class _DMSCmdRen(object):
	""" one unique "Rename" request, parsed from **kwargs """

	CMD_TYPE = u'rename'

	def __init__(self, msghandler, path, newPath, **kwargs):
		# kwargs are not used. we keep them for future extensions
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.newPath = u'' + newPath
		self.tag = msghandler.generate_tag()

	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		curr_dict[u'newPath'] = self.newPath
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdRen.CMD_TYPE


class _DMSCmdDel(object):
	""" one unique "Delete" request, parsed from **kwargs """

	CMD_TYPE = u'delete'

	def __init__(self, msghandler, path, recursive=None, **kwargs):
		# kwargs are not used. we keep them for future extensions
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path

		# flag "recursive" is optional, default in DMS is False.
		# Because this is a possible dangerous command we allow explicit sending of False over the wire!
		self.recursive = recursive
		self.tag = msghandler.generate_tag()

	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.recursive != None:
			curr_dict[u'recursive'] = bool(self.recursive)
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdDel.CMD_TYPE



class _DMSCmdSub(object):
	""" one unique "subscribe" request, parsed from **kwargs """

	CMD_TYPE = u'subscribe'

	def __init__(self, msghandler, path, **kwargs):
		# parsing of kwargs: help from https://stackoverflow.com/questions/5624912/kwargs-parsing-best-practice
		# =>since all fields in "get" object and all it's subobjects are unique, we could handle them in the same loop
		self.path = u'' + path
		self.query = {}
		if not u'tag' in kwargs:
			self.tag = msghandler.generate_tag()
		else:
			# caller wants to reuse existing tag =>DMS will update subscription when path and tag match a current subscription
			self.tag = kwargs[u'tag']


		for key in kwargs:
			# parsing "query" object
			val = None
			if key == u'regExPath':
				val = u'' + kwargs[key]
			elif key == u'regExValue':
				val = u'' + kwargs[key]
			elif key == u'regExStamp':
				val = u'' + kwargs[key]
			elif key == u'isType':
				val = u'' + kwargs[key]
			elif key == u'hasHistData':
				val = bool(kwargs[key])
			elif key == u'hasAlarmData':
				val = bool(kwargs[key])
			elif key == u'hasProtocolData':
				val = bool(kwargs[key])
			elif key == u'maxDepth':
				val = int(kwargs[key])

			if val:
				self.query[key] = val

			# parsing properties
			if key == u'event':
				# FIXME: we should implement something similar as in "sticky"-options of http://effbot.org/tkinterbook/grid.htm
				#        =>defining int-constants CHANGE=1, SET=2, CREATE=4, RENAME=8, DELETE=16, ALL=31,
				#          or handle these flags as string in a set()
				self.event = u'' + kwargs[key]


	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		if self.query:
			curr_dict[u'query'] = self.query
		if self.event:
			curr_dict[u'event'] = self.event
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdSub.CMD_TYPE



class _DMSCmdUnsub(object):
	""" one unique "unsubscribe" request, parsed from **kwargs """

	CMD_TYPE = u'unsubscribe'

	def __init__(self, path, tag):
		# =>because our implementation of subscriptions always use a tag, we have to make tags mandatory
		# (documentation for "unsubscribe" say "tag" is an optional field)
		self.path = u'' + path
		self.tag = tag

	def as_dict(self):
		curr_dict = {}
		curr_dict[u'path'] = self.path
		curr_dict[u'tag'] = self.tag
		return curr_dict

	def get_type(self):
		return _DMSCmdUnsub.CMD_TYPE



class ExtInfos(collections.Mapping):
	""" optional extended infos about datapoint """
	# inherit from abstract "Mapping" for getting dictionary-API

	_fields = (u'template',
	           u'name',
	           u'accType',
	           u'unit',
	           u'comment')
	def __init__(self, **kwargs):
		self._values_dict = {}

		for field in ExtInfos._fields:
			try:
				# all fields are strings.
				# default: no special treatment
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				self._values_dict[field] = None

		def __getitem__(self, key):
			return self._values_dict[key]

		def __iter__(self):
			return iter(self._values_dict)

		def __len__(self):
			return len(self._values_dict)

		def __repr__(self):
			""" developer representation of this object """
			return u'ExtInfos(' + repr(self._values_dict) + u')'

		def __str__(self):
			return u'' + str(self._values_dict)


class HistData_detail(collections.Sequence):
	""" optional history data in detailed format """
	# implementing abstract class "Sequence" for getting list-like object
	# https://docs.python.org/2/library/collections.html#collections.Sequence
	_fields = (u'stamp',
	           u'value',
	           u'state',
	           u'rec')

	def __init__(self, histobj_list):
		# internal storage: list of dictionaries with _fields as keys
		self._values_list = []

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
						print('constructor of HistData_detail(): ERROR: timestamp in current response could not get parsed as valid datetime.datetime() object!')
						curr_dict[field] = None
				else:
					# other fields are number or string, currently no special treatment
					try:
						curr_dict[field] = histobj[field]
					except KeyError:
						# something went wrong, a mandatory field is missing...
						print('constructor of HistData_detail(): ERROR: mandatory field "' + field + '" is missing in current response!')
						# argument was not in response =>setting default value
						curr_dict[field] = None
			# save current dict, begin a new one
			self._values_list.append(curr_dict)
			curr_dict = {}


	def __getitem__(self, idx):
		return self._values_list[idx]

	def __len__(self):
		return len(self._values_list)

	def __repr__(self):
		""" developer representation of this object """
		return u'HistData_detail(' + repr(self._values_list) + u')'

	def __str__(self):
		return u'' + str(self._values_list)


class HistData_compact(collections.Sequence):
	""" optional history data in compact format """
	# implementing abstract class "Sequence" for getting list-like object
	# https://docs.python.org/2/library/collections.html#collections.Sequence
	def __init__(self, histobj_list):
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
				print(
				'constructor of HistData_compact(): ERROR: timestamp in current response could not get parsed as valid datetime.datetime() object!')
				stamp = None

			curr_tuple = (stamp, value)
			self._values_list.append(curr_tuple)

	def __getitem__(self, idx):
		return self._values_list[idx]

	def __len__(self):
		return len(self._values_list)

	def __repr__(self):
		""" developer representation of this object """
		return u'HistData_compact(' + repr(self._values_list) + u')'

	def __str__(self):
		return u'' + str(self._values_list)



class CmdResponse(object):
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
		for field in CmdResponse._fields:
			try:
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# something went wrong, a mandatory field is missing... =>set error code
				print('constructor of CmdResponse(): ERROR: mandatory field "' + field + '" is missing in current response!')
				self._values_dict[u'code'] = CmdResponse.CODE_ERROR

		# some sanity checks
		if not self._values_dict[u'code'] in (CmdResponse.CODE_OK,
		                                      CmdResponse.CODE_NOPERM,
		                                      CmdResponse.CODE_NOTFOUND,
		                                      CmdResponse.CODE_ERROR):
			print('constructor of CmdResponse(): ERROR: field "code" in current response contains unknown value "' + repr(self._values_dict[u'code']) + '"!')
			# FIXME: what should we do if response code is unknown? Perhaps it's an unsupported JSON Data Exchange protocol?


class CmdGetResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'hasChild',
	           u'stamp',
	           u'extInfos',
	           u'message',
	           u'histData',
	           u'tag')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdGetResponse._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs[field])
					except:
						self._values_dict[field] = None
				elif field == u'extInfos':
					self._values_dict[field] = ExtInfos(kwargs[field])
				elif field == u'histData':
					if kwargs[field]:
						# parse response as "detail" or "compact" format
						# according to documentation: default is "compact"
						# =>checking first JSON-object if it contains "stamp" for choosing right parsing
						histData_list = kwargs[field]
						if not u'stamp' in histData_list[0]:
							# assuming "compact" format
							self._values_dict[field] = HistData_compact(kwargs[field])
						else:
							# assuming "detail" format
							self._values_dict[field] = HistData_detail(kwargs[field])
					else:
						# histData is an empty list, we have no trenddata...
						self._values_dict[field] = []
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				if DEBUGGING:
					print('\tDEBUG: CmdGetResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdGetResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdGetResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)


class CmdSetResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdSetResponse._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs[field])
					except:
						self._values_dict[field] = None
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdSetResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdSetResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdSetResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)


class CmdRenResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'newPath',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdRenResponse._fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdRenResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdRenResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdRenResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)


class CmdDelResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'message',
	           u'tag')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdDelResponse._fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdDelResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdDelResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdDelResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)



class CmdSubResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')
	# "query" object is optional
	_opt_fields = (u'regExPath',
	               u'regExValue',
	               u'regExStamp',
	               u'isType',
	               u'hasHistData',
	               u'hasAlarmData',
	               u'hasProtocolData',
	               u'maxDepth')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdSubResponse._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs[field])
					except:
						self._values_dict[field] = None
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdSubResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# handle optional "query" object
		# =>we insert an additional key "query" as flag if query was used.
		# =>the fields have unique names, so we store them flat in our dictionary.
		self._values_dict[u'query'] = u'query' in kwargs
		for field in CmdSubResponse._opt_fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs[u'query'][field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdSubResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdSubResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdSubResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)


class CmdUnsubResponse(CmdResponse, collections.Mapping):
	_fields = (u'path',
	           u'value',
	           u'type',
	           u'stamp',
	           u'message',
	           u'tag')
	# "query" object is optional
	_opt_fields = (u'regExPath',
	               u'regExValue',
	               u'regExStamp',
	               u'isType',
	               u'hasHistData',
	               u'hasAlarmData',
	               u'hasProtocolData',
	               u'maxDepth')

	def __init__(self, **kwargs):
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdUnsubResponse._fields:
			try:
				if field == u'stamp':
					# timestamps are ISO 8601 formatted (or "null" after DMS restart or on nodes with type "none")
					# https://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
					try:
						self._values_dict[field] = dateutil.parser.parse(kwargs[field])
					except:
						self._values_dict[field] = None
				else:
					# default: no special treatment
					self._values_dict[field] = kwargs[field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdUnsubResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# handle optional "query" object
		# =>we insert an additional key "query" as flag if query was used.
		# =>the fields have unique names, so we store them flat in our dictionary.
		self._values_dict[u'query'] = u'query' in kwargs
		for field in CmdUnsubResponse._opt_fields:
			try:
				# default: no special treatment
				self._values_dict[field] = kwargs[u'query'][field]
			except KeyError:
				# argument was not in response =>setting default value
				print('\tDEBUG: CmdUnsubResponse constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# init all common fields
		super(CmdUnsubResponse, self).__init__(**kwargs)


	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdUnsubResponse(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)


class Subscription(object):
	''' mapping python callbacks to DMS events '''
	# using "axel events" for events handling https://github.com/axel-events/axel

	# FIXME: how to "glue everything together"?
	# FIXME: which information does this class need for doing:
	#        -subscriptions
	#        -updates to those
	#        -re-subscriptions
	#        -unsubscriptions
	def __init__(self, msghandler, sub_response):
		self._msghandler = msghandler
		self.sub_response = sub_response
		# details about constructor of Event():
		# https://github.com/axel-events/axel/blob/master/axel/axel.py
		self.event = axel.Event(threads=1)

	def get_path_tag(self):
		return self.sub_response[u'path'], self.sub_response[u'tag']

	def update(self, **kwargs):
		# FIXME for performance: detect changes in "query" and "event",
		# if changed, then overwrite subscription in DMS,
		# else resubscribe (currently we send request in every case...)
		# FIXME: how to report errors to caller?

		# reuse "path" and "tag", then DMS will replace subscription
		if u'path' in kwargs:
			del(kwargs[u'path'])
		kwargs[u'tag'] = self.sub_response.tag
		resp = self._msghandler.dp_sub(path=self.sub_response.path, **kwargs)


	def unsubscribe(self):
		# FIXME: how to report errors to caller?
		resp = self._msghandler._dp_unsub(path=self.sub_response.path,
		                                  tag=self.sub_response.tag)
		self._msghandler.del_subscription(self)

	def __del__(self):
		# destructor: first unsubscribe from DMS,
		# we assume garbage collector will delete all internal references
		self.unsubscribe()


class CmdEvent(collections.Mapping):
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
		# better idea: do ducktyping without type checking,
		# inherit from abstract class "Mapping" for getting dictionary-interface
		# https://stackoverflow.com/questions/19775685/how-to-correctly-implement-the-mapping-protocol-in-python
		# https://docs.python.org/2.7/library/collections.html#collections.MutableMapping
		# (then the options are similar to Tkinter widgets: http://effbot.org/tkinterbook/tkinter-widget-configuration.htm )
		#
		#
		## set all keyword arguments as instance attribut
		## help from https://stackoverflow.com/questions/8187082/how-can-you-set-class-attributes-from-variable-arguments-kwargs-in-python
		#self.__dict__.update(kwargs)

		self._values_dict = {}

		for field in CmdEvent._fields:
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
				print('\tDEBUG: CmdEvent constructor: field "' + field + '" is not in response.')
				self._values_dict[field] = None

		# sanity check:
		if not self._values_dict[u'code'] in (CmdEvent.CODE_CHANGE,
		                                      CmdEvent.CODE_SET,
		                                      CmdEvent.CODE_CREATE,
		                                      CmdEvent.CODE_RENAME,
		                                      CmdEvent.CODE_DELETE):
					print(
						'constructor of CmdEvent(): ERROR: field "code" in current response contains unknown value "' + repr(
							self._values_dict[u'code']) + '"!')

	def __getitem__(self, key):
		return self._values_dict[key]

	def __iter__(self):
		return iter(self._values_dict)

	def __len__(self):
		return len(self._values_dict)

	def __repr__(self):
		""" developer representation of this object """
		return u'CmdEvent(' + repr(self._values_dict) + u')'

	def __str__(self):
		return u'' + str(self._values_dict)





class _MessageHandler(object):
	def __init__(self, dmsclient_obj, whois_str, user_str):
		# backreference for sending messages
		self._dmsclient = dmsclient_obj
		self._whois_str = whois_str
		self._user_str = user_str

		# dict for pending responses (key: cmd-tag, value: list of CmdResponse-objects)
		# =>None means request is sent, but answer is not yet here
		self._pending_response_dict = {}

		# dict for DMS-events (key: tuple path+tag, value: Subscription-objects)
		# =>DMS-event will fire our python event
		self._subscriptions_dict = {}


		# object for assembling response lists
		# (when one "get" command produces more than one response)
		class Current_response(object):
			def __init__(self):
				self.msg_tag = u''
				self.resp_list = []
			def clear(self):
				self.__init__()
		self._curr_response = Current_response()



	def dp_get(self, path, timeout=10000, **kwargs):
		""" read datapoint value(s) """

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(_DMSCmdGet(msghandler=self, path=path, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_get(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_set(self, path, value, timeout=10000, **kwargs):
		""" write datapoint value(s) """
		# Remarks: datatype in DMS is taken from datatype of "value" (field "type" is optional)
		# Remarks: datatype STR: 80 chars could be serialized by DMS into Promos.dms file for permament storage.
		#                        =>transmission of 64kByte text is possible (total size of JSON request),
		#                          this text is volatile in RAM of DMS.

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(
			_DMSCmdSet(msghandler=self, path=path, value=value, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_set(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_del(self, path, recursive, timeout=10000, **kwargs):
		""" delete datapoint(s) """

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(
			_DMSCmdDel(msghandler=self, path=path, recursive=recursive, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_del(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_ren(self, path, newPath, timeout=10000, **kwargs):
		""" rename datapoint(s) """

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(
			_DMSCmdRen(msghandler=self, path=path, newPath=newPath, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_ren(): len(req.get_tags())=' + str(len(req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def dp_sub(self, path, timeout=10000, **kwargs):
		""" subscribe monitoring of datapoints(s) """

		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(
			_DMSCmdSub(msghandler=self, path=path, **kwargs))
		self._send_frame(req)

		try:
			tag = req.get_tags()[0]
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_ren(): len(req.get_tags())=' + str(len(
					req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')



	def _dp_unsub(self, path, tag, timeout=10000, **kwargs):
		""" unsubscribe monitoring of datapoint(s) """
		# =>called by Subscription.unsubscribe()
		req = _DMSRequest(whois=self._whois_str, user=self._user_str).addCmd(
			_DMSCmdUnsub(path=path, tag=tag))
		self._send_frame(req)

		try:
			return self._busy_wait_for_response(tag, timeout)
		except IndexError:
			# something went wrong...
			if DEBUGGING:
				print('error in dp_ren(): len(req.get_tags())=' + str(len(
					req.get_tags())) + ', too much or too few responses? sending more than one command per request is not implemented!')
			raise Exception('Please report this bug of pyVisiToolkit!')


	def handle(self, msg):
		payload_dict = json.loads(msg.decode('utf8'))

		try:
			# message handler
			for resp_type, resp_cls in [(u'get',    CmdGetResponse),
			                            (u'set',    CmdSetResponse),
			                            (u'rename', CmdRenResponse),
			                            (u'delete', CmdDelResponse),
			                            (u'subscribe', CmdSubResponse),
			                            (u'unsubscribe', CmdUnsubResponse)]:
				if resp_type in payload_dict:
					# handling responses to command

					# preparation: reset response list
					self._curr_response.clear()

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
										if DEBUGGING:
											print('\tmessage handler: found different tags in response. Storing response for other thread...')
										self._pending_response_dict[curr_tag] = self._curr_response.resp_list
									else:
										if DEBUGGING:
											print('\tmessage handler: ignoring unexpected response "' + repr(self._curr_response.resp_list) + '"...')
								# begin of new response list
								self._curr_response.msg_tag = curr_tag
								self._curr_response.resp_list = [resp_cls(**response)]

						else:
							if DEBUGGING:
								print('\tmessage handler: ignoring untagged response "' + repr(response) + '"...')

					# storing collected list for other thread
					if DEBUGGING:
						print('\tmessage handler: storing of response for other thread...')
					self._pending_response_dict[curr_tag] = self._curr_response.resp_list
		except Exception as ex:
			print("exception in _MessageHandler.handle(): " + repr(ex))


		if u'event' in payload_dict:
			# handling DMS-events
			for event in payload_dict[u'event']:
				# trigger Python event
				try:
					event_obj = CmdEvent(**event)
					path, tag = event_obj[u'path'], event_obj[u'tag']
					sub = self._subscriptions_dict[(path, tag)]
					# print('DEBUGGING: _MsgHandler.handle(), sub=' + repr(sub) + ', sub.event=' + repr(sub.event))
					result = sub.event(event_obj)
					# FIXME: how to inform caller about exceptions while executing his callbacks?
					# FIXME: should we use Python logger framework?
					if DEBUGGING:
						print('DEBUGGING: _MsgHandler.handle(), result of event-firing: result=' + repr(result))
				except AttributeError as ex:
					print("exception in _MessageHandler.handle(): DMS-event seems corrupted: " + repr(ex))
				except KeyError as ex:
					print("exception in _MessageHandler.handle(): DMS-event is not registered: " + repr(ex))
				except Exception as ex:
					print("exception in _MessageHandler.handle(): DMS-event raises " + repr(ex))



	def _send_frame(self, frame_obj):
		# send whole request

		# create valid JSON
		# (according to https://docs.python.org/2/library/json.html : default encoding is UTF8)
		req_str = json.dumps(frame_obj.as_dict())
		self._dmsclient._send_message(req_str)

	def _busy_wait_for_response(self, tag, timeout):
		# FIXME: can we implement this in a better way?
		found = False
		loops = 0
		while not found and loops <= timeout:
			time.sleep(TIMEOUT_TIMEBASE)
			loops = loops + 1
			if self._pending_response_dict[tag]:
				found = True
		return self._pending_response_dict.pop(tag)

	def add_subscription(self, sub):
		path, tag = sub.get_path_tag()
		self._subscriptions_dict[(path, tag)] = sub

	def del_subscription(self, sub):
		path, tag = sub.get_path_tag()
		del(self._subscriptions_dict[(path, tag)])


	def generate_tag(self):
		# generating random and nearly unique message tags
		# (see https://docs.python.org/2/library/uuid.html )
		curr_tag = str(uuid.uuid4())

		self._pending_response_dict[curr_tag] = None
		return curr_tag


class DMSClient(object):
	def __init__(self, whois_str, user_str, dms_host_str=DMS_HOST, dms_port_int=DMS_PORT):
		self._dms_host_str = dms_host_str
		self._dms_port_int = dms_port_int
		self._msghandler = _MessageHandler(dmsclient_obj=self, whois_str=whois_str, user_str=user_str)
		self.ready_to_send = False

		# based on example on https://github.com/websocket-client/websocket-client
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
		if DEBUGGING:
			print("WebSocket connection will be established in background...")

	# API
	def dp_get(self, path, **kwargs):
		""" read datapoint value(s) """
		return self._msghandler.dp_get(path, **kwargs)

	def dp_set(self, path, **kwargs):
		""" write datapoint value(s) """
		return self._msghandler.dp_set(path, **kwargs)

	def dp_del(self, path, recursive, **kwargs):
		""" delete datapoint(s) """
		return self._msghandler.dp_del(path, recursive, **kwargs)

	def dp_ren(self, path, newPath, **kwargs):
		""" rename datapoint(s) """
		return self._msghandler.dp_ren(path, newPath, **kwargs)

	def get_dp_subscription(self, path, **kwargs):
		""" subscribe monitoring of datapoints(s) """
		# FIXME: now we care only the first response... is this ok in every case?
		response = self._msghandler.dp_sub(path, **kwargs)[0]
		print('DEBUGGING: type(response)=' + repr(type(response)) + ', repr(response)=' + repr(response))
		if response["code"] == u'ok':
			# DMS accepted subscription
			sub = Subscription(msghandler=self._msghandler, sub_response=response)
			self._msghandler.add_subscription(sub)
			return sub
		else:
			raise Exception(u'DMS ignored subscription of "' + path + '" with error "' + response.code + '"!')



	def _busy_wait_until_ready(self, timeout=10000):
		# FIXME: is there a better way to do this?
		# FIXME: how to inform caller about problems, should we raise a selfmade timeout excpetion?
		loops = 0
		while not self.ready_to_send and loops <= timeout:
			time.sleep(TIMEOUT_TIMEBASE)
			loops = loops + 1


	def _send_message(self, msg):
		self._busy_wait_until_ready()
		if self.ready_to_send:
			if DEBUGGING:
				print('DMSClient._send_message(): sending request "' + repr(msg) + '"')
			self._ws.send(msg)
		else:
			if DEBUGGING:
				print('DMSClient._send_message(): ERROR WebSocket not ready for sending request "' + repr(msg) + '"')
		# FIXME: how should we inform user about WebSocket problems?
		# e.g. giving back IOError exception?
		# or raw websocket-exceptions https://github.com/websocket-client/websocket-client/blob/master/websocket/_exceptions.py


	def _cb_on_message(self, ws, message):
		if DEBUGGING:
			print("_on_message(): " + message)
		self._msghandler.handle(message)

	def _cb_on_error(self, ws, error):
		if DEBUGGING:
			print("_on_error(): " + error)

	def _cb_on_open(self, ws):
		if DEBUGGING:
			print("_on_open(): WebSocket connection is established.")
		self.ready_to_send = True

	def _cb_on_close(self, ws):
		if DEBUGGING:
			print("_on_close(): server closed connection =>shutting down client thread")
		self.ready_to_send = False
		self._ws_thread.exit()

	def __del__(self):
		"""" closing websocket connection on object destruction """
		self._ws.close()
		time.sleep(1)
		self._ws_thread.exit()



if __name__ == '__main__':

	myClient = DMSClient(u'test', u'user') #,  dms_host_str='192.168.10.173')
	print('\n=>WebSocket connection runs now in background...')

	# while True:
	# 	time.sleep(1)
	# 	print('sending TESTMSG...')
	# 	myClient._send_message(TESTMSG)

	test_set = set([11])

	if 1 in test_set:
		print('\nTesting creation of Request command:')
		print('"get":')
		for x in range(3):
			response = myClient.dp_get(path="System:Time")
			print('response to our request: ' + repr(response))
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
		print('\twith query: ' + repr(myClient.dp_get(path="", regExPath=".*", maxDepth=1)))

	if 4 in test_set:
		print('\nTesting retrieving HistData:')
		response = myClient.dp_get(path="MSR01:Ala101:Output_Lampe",
		                           start="2017-08-22T12:38:50.486000+02:00",
		                           end="2017-08-23T12:38:50.486000+02:00",
		                           format="compact",
		                           #format="detail",
		                           interval=0,
		                           showExtInfos=True,
		                           maxDepth=0)
		print('response: ' + repr(response))

	if 5 in test_set:
		print('\nTesting writing of DMS datapoint:')
		response = myClient.dp_set(path="MSR01:Test_str",
		                           value=80*"x",
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
			                           showExtInfos=True,
			                           maxDepth=-1,
			                           )
			print('response to our request: ' + repr(response))
			print('*' * 20)

	if 11 in test_set:
		print('\nTesting monitoring of DMS datapoint:')
		sub = myClient.get_dp_subscription(path="System:Blinker:Blink1.0",
		                                        event="onChange",
		                                        maxDepth=-1)
		print('got Subscription object: ' + repr(sub))
		print('\tadding callback function:')
		def myfunc(event):
			print('\t\tGOT EVENT: ' + repr(event))
		sub.event += myfunc
		print('\twaiting some seconds...')
		for x in range(100):
			time.sleep(0.1)