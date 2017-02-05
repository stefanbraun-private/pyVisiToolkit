#!/usr/bin/env python
# encoding: utf-8
"""
tools.Runtime_BMO_Info.py

Copyright (C) 2016 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import visu.psc.Parser
import ctypes
import ctypes.wintypes
import time
import exceptions
import os

DEBUGGING = True


class Mouse(object):
	# example: get mouse cursor position in Windows
	# http://nullege.com/codes/show/src@u@i@UISoup-1.3.2@uisoup@win_soup@mouse.py/212/ctypes.windll.user32.GetCursorPos
	def get_position(self):
		obj_point = ctypes.wintypes.POINT()
		ctypes.windll.user32.GetCursorPos(ctypes.byref(obj_point))

		return obj_point.x, obj_point.y


def main(argv=None):

	curr_dms = dms.dmspipe.Dmspipe()

	prj = curr_dms.pyDMS_ReadSTREx('System:Project')
	computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
	if DEBUGGING:
		print('prj=' + prj)
		print('computer=' + computer)

	print('Runtime_BMO_Info.py')
	print('*******************')
	print('\tBMO-information is displayed when mouse position is over a BMO')
	print('\t(press <CTRL-C> for quit)')

	mouse = Mouse()
	psc_elem_set = set()
	doPrintElem = True

	# mainloop
	doRun = True
	try:
		while doRun:
			if curr_dms.pyDMS_ReadBITEx('System:Node:' + computer + ':Runtime'):
				curr_psc = curr_dms.pyDMS_ReadSTREx('System:Node:' + computer + ':Image')
				curr_ReInit = curr_dms.pyDMS_ReadSTREx('System:Node:' + computer + ':ImgReInit')
				curr_prj = curr_dms.pyDMS_ReadSTREx('System:Project')

				mousePos = mouse.get_position()

				filename = os.path.join(curr_prj, 'scr' , curr_psc)
				curr_visuparser = visu.psc.Parser.PscFile(filename)
				curr_visuparser.parse_file()

				psc_elem_set_old = psc_elem_set
				psc_elem_set = set()
				for elem in curr_visuparser.get_elem_list_at_coordinate(mousePos[0], mousePos[1]):
					psc_elem_set.add(elem._bmo_instance)

				if psc_elem_set == psc_elem_set_old:
					# last cycle mouse was over same BMO ->print it one time
					if doPrintElem:
						myStrList = []
						for myElem in psc_elem_set:
							if myElem != '':
								myStrList.append(myElem)
						if len(myStrList) > 0:
							print(','.join(myStrList))
							doPrintElem = False
				else:
					doPrintElem = True


			time.sleep(0.3)
	except exceptions.KeyboardInterrupt:
		# user pressed CTRL-C
		print('Quitting program...')




	return 0        # success


if __name__ == '__main__':
	status = main()
	# sys.exit(status)