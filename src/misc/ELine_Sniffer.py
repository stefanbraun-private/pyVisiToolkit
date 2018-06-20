#!/usr/bin/env python
# encoding: utf-8
"""
misc.ELine_Sniffer.py      v0.0.1
Passively monitoring of SBC(R) E-Line RS-485 S-Bus datacommunication.

[works with USB-RS485-converter https://www.cti-shop.com/rs485-konverter/usb-485-mini-op ]


based on information found in

-opensource "SBPoll" (c) by Michael Griffin <m.os.griffin@gmail.com>
..\mbtools_2011-01-07.zip\mbtools_2011-01-07\sbpoll\mbprotocols\SBusMsg.py
http://mblogic.sourceforge.net/mbtools/sbpoll.html

-Saia/SBC(R) chm-helpfile in PG5(tm) Instruction-List library for E-Line

-Saia/SBC(R) S-Bus PDF handbook 26-739 and other public PDFs published on the internet

-opensource Wireshark Ether-S-Bus packet dissector (c) by Christian Durrer <christian.durrer@sensemail.ch>

-RS485-ELine-SBus monitoring by relaying it over Ether-SBus-gateway -> Ethernet-hub (Wireshark) -> serial-SBus-gateway

and a lot of trial and error...


Some remarks:
-pyserial uses packed strings like '\x45\xAB\xC3\x16'
https://eli.thegreenplace.net/2009/08/20/frames-and-protocols-for-the-serial-port-in-python

-handling frames out of a serial bytestream:

information about E-Line serial S-Bus on RS485 (it uses reduced S-Bus protocol, means only reading/writing PLC medias, no PGU)
-datagrams from master to E-Line module look like "S-Bus master data-mode (SM2)"
-datagrams from E-Line module to master look like "S-Bus slave data-mode (SS2)"
-E-Line modules can operate with regular reduced S-Bus datagrams and with a new compact E-line protocol embedded into S-Bus frames
-serial RS485 communication with E-Line modules seems "autobauding" (only master has configuration for baudrate)
-serial mode for "S-Bus data-mode" is 1x startbit, 8x databit, no parity, 1x stopbit.
=>FS (frame synchronisation) character == 0xB5
=>AT-char 1 byte (S-Bus command?):
  0x00 request from master to E-Line-module
       (followed by 1 byte S-Bus slave address)
  0x01 response from E-line-module to master
=>UNKNOWN E-LINE DATA EMBEDDED INTO USUAL S-BUS-DATAGRAM
=>16bit CRC (CCIT V.41 CRC) with seed 0x0000 at end of frame
-hmm, how to detect end of frame?
  -using timeouts and split by FS-char?
  -using "inter_byte_timeout" of http://pyserial.readthedocs.io/en/latest/pyserial_api.html ?
  -continously calculate CRC after every byte?
  =>need to reversing every bit of this new protocol... :-/
  (according to chm-helpfile: "S.SF.ELINE.ELMInit" says that every E-Line-module has unique amount of registers and flags,
   they store internally a configuration read/written by master, and wrong datagrams were rejected by NAK)

ideas:
https://eli.thegreenplace.net/2009/08/12/framing-in-serial-communications
https://github.com/GraemeWilson/Arduino-Python-Framing-CRC16/tree/master/Python



Copyright (C) 2018 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import logging
import pyparsing
import argparse
import threading
import serial
import Queue
import datetime

# setup of logging
# (based on tutorial https://docs.python.org/2/howto/logging.html )
# create logger =>set level to DEBUG if you want to catch all log messages!
logger = logging.getLogger('misc.ELine_Sniffer')
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



class SerialByteReader(threading.Thread):
	""" reads single bytes from serialport as background thread and puts them with timestamp into nonblocking queue """
	def __init__(self, ser, bytes_queue):
		self._ser = ser
		self._bytes_queue = bytes_queue
		threading.Thread.__init__(self)

		self._keep_running = False
		self.daemon = True

	def run(self):
		while self._keep_running:
			x = self._ser.read()  # read one byte
			if x:
				now = datetime.datetime.now()
				self._bytes_queue.put(now, x)

	def stop(self):
		self._keep_running = False




def main():
	# based on examples from http://pyserial.readthedocs.io/en/latest/shortintro.html
	with serial.Serial('COM3', 9600, timeout=1) as ser:
		q = Queue.Queue()
		reader = SerialByteReader(ser=ser, bytes_queue=q)
		reader.start()


	logger.info('Quitting "ELine_Sniffer"...')

	return 0        # success


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Passively monitoring of SBC(R) E-Line RS-485 S-Bus datacommunication.')

	args = parser.parse_args()

	status = main()
	#sys.exit(status)