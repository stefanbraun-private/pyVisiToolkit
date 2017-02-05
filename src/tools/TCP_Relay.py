#!/usr/bin/env python
# encoding: utf-8
"""
tools.TCP_Relay.py      v0.0.1
A quick-and-dirty TCP relaying (forwarding) tool for simple debugging of an unencrypted TCP network connection.
Opens a local TCP port and relay/forward data to an external Host.

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""


import socket
import select
import argparse


BUFFER_SIZE = 50  # Normally 1024, but we want fast response

# we work on a german Windows, we have no UTF-8 encoding...
ENCODING = 'windows-1252'


def main(local_ip, local_port, remote_host, remote_port):
	print('TCP_Relay v0.0.1')
	print('\tA quick-and-dirty TCP relaying (forwarding) tool for simple debugging of an unencrypted TCP network connection.')
	print('\tOpens a local TCP port and relay/forward data to a remote Host.')
	print('\nTrying to establish this TCP portforwarding:')
	print('[TCP-client] --> [' + str(local_ip) + ':' + str(local_port) + '] >>>> [TCP-Server ' + str(remote_host) + ':' + str(remote_port) + ']\n')

	sock_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	# host and port as a tuple: http://stackoverflow.com/questions/19143091/typeerror-connect-takes-exactly-one-argument
	sock_srv.bind((str(local_ip), local_port))
	sock_srv.listen(1)
	print('listening on local TCP port ' + str(local_port) + ' on interface ' + str(local_ip) + ' for incoming connections...')

	client_conn, client_addr = sock_srv.accept()
	print('got incoming client connection from ' + str(client_addr[0]) + ':' + str(client_addr[1]) + '...')


	sock_to_svr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock_to_svr.connect((str(remote_host), remote_port))
	print('established outgoing connection to server ' + remote_host.decode(ENCODING) + ':' + str(remote_port) + '...\n')

	try:
		while 1:
			# something to do in sockets?
			# from https://docs.python.org/2/howto/sockets.html
			ready_to_read, ready_to_write, in_error = \
		               select.select(
		                  [client_conn, sock_to_svr],
		                  [],
		                  [])

			# select returned a socket with available data ->forward on the other connection
			# (exception handling: http://stackoverflow.com/questions/25447803/python-socket-connection-exception )
			if client_conn in ready_to_read:
				data = client_conn.recv(BUFFER_SIZE)
				if not data: break
				print("from client:\t" + repr(data))
				sock_to_svr.send(data)

			if sock_to_svr in ready_to_read:
				data = sock_to_svr.recv(BUFFER_SIZE)
				if not data: break
				print("from server:\t" + repr(data))
				client_conn.send(data)

		# FIXME: do a proper cleanup when a TCP connection breaks or user interrupts this program...
		sock_to_svr.shutdown(socket.SHUT_RDWR)  # try to close the connection immediately
		sock_to_svr.close()
		client_conn.shutdown(socket.SHUT_RDWR)  # try to close the connection immediately
		client_conn.close()

	except socket.error as msg:
		print("Socket Error: %s" % msg)

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='TCP relay for debugging/forwarding an unencrypted TCP connection.')

	parser.add_argument('--lip', '-i', dest='local_ip', help='local ip address (default: binds to 127.0.0.1, use 0.0.0.0 for listening on all interfaces)')
	parser.add_argument('--lport', '-p', dest='local_port', default=0, type=int, help='local TCP port (default: same as on remote host)')
	parser.add_argument('REMOTE_HOST', help='remote host (e.g. 192.168.1.1, or www.example.ch)')
	parser.add_argument('REMOTE_PORT', type=int, help='remote TCP port')

	args = parser.parse_args()

	# setting default values
	if args.local_ip is None:
		# using loopback device
		args.local_ip = '127.0.0.1'
	if args.local_port == 0:
		# default: binding to same TCP port as remote host
		args.local_port = args.REMOTE_PORT

	status = main(local_ip=args.local_ip, local_port=args.local_port, remote_host=args.REMOTE_HOST, remote_port=args.REMOTE_PORT)
	#sys.exit(status)