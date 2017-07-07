#!/usr/bin/env python
# encoding: utf-8
"""
misc.BlinkenlightsRGB_Emulator.py

emulates color-display for Blinkenlights movies in Grafikeditor
(this script needs its counterparts in DMS and a special PSC file)

=>this program should play more movie types than "misc.Blinkenlights_Emulator.py"

ideas for improvements:
-Blinkenlights file selection via dropdown GUI element in PSC file
-implement all four specified Blinkenlights movie file formats
 [TBD]    blm - BlinkenLights Movie
 [TBD]   bmm - BlinkenMini Movie
 [TBD]   bml - Blinkenlights Markup Language
 [TBD]   bbm - Binary Blinken Movie


How does the RGB display work?
In "Grafikeditor" it's possible to change color by a binary DMS key. This way we got the monochrome display
for "misc.Blinkenlights_Emulator.py", where we used one BIT value in DMS for each pixel (transmitted as 32bit integer).
=>hmm, it's not possible to directly display a DMS value interpreted as RGB-value...
But there's a possibility for a color gradient depending on a reference DMS value. "Grafikeditor" simply
interpolates RGB values between two given points (think about a three dimensional cube,
the three axes represents red, green and blue, and with a color depth of 8bit the possible RGB colors have
values between 0 and 255 on each axe. The defined color gradient is a direct line between these two points).
When we define more than two points, then "Grafikeditor" follows this path through the RGB color "cube" (the
DMS reference value must descend with every given point). With one long path combined from many gradient-segments
we should get a low-resolution mapping for RGB colors. Our reference DMS value is simply the path length between
begin and end through the RGB color "cube".
For every RGB-pixel we have to find the nearest gradient-segment and the right reference value to display a similar
RGB color on the display (one reference DMS value per RGB-pixel).
The visibility of each pixel is controlled by enable bits in two 32bit integers,
this gives a maximal dimension of 32 rows and 32 columns.



=>URLs for more information:
general info:
https://de.wikipedia.org/wiki/Projekt_Blinkenlights
http://wiki.blinkenarea.org/index.php/Blinkenlights_Movie

technical specification:
http://blinkenlights.net/project/developer-tools
http://oldwiki.blinkenarea.org/bin/view/Blinkenarea/DateiFormate

examples:
http://www.apo33.org/pub/puredata/luc/degoyon/blinkenlights/blm/raumschiff_enterprise.blm
http://dpnc.unige.ch/users/meunier/DATA/src/iowarrior/SDK/MacOSX/Sources/BlinkenWarrior/BlinkenLights%20Movies/Scrolltext.blm
http://s23.org/wiki/Blinkenlights/Movies



Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import dms.dmspipe
import sys
import locale
import os
import time
import re
import argparse
import random

from operator import methodcaller

import sympy
from sympy import Point3D
from sympy.geometry import Line3D, Segment3D
from sympy.geometry import Line, Segment, Point, Circle

from visu.psc.ParserVars import PscVar_RGB


ENCODING_STDOUT1 = ''
ENCODING_STDOUT2 = ''
ENCODING_LOCALE = ''
ENCODING_FILENAMES = sys.getfilesystemencoding()

DEBUGGING = True

# floating point precision in ProMoS NT(c)
NOF_DECIMAL_DIGITS = 6

NOF_ROWS = 32
NOF_COLUMNS = 32

def get_encoding():
	global ENCODING_STDOUT1
	# following code seems only to work in IDE...
	ENCODING_STDOUT1= sys.stdout.encoding or sys.getfilesystemencoding()

	# hint from http://stackoverflow.com/questions/9226516/python-windows-console-and-encodings-cp-850-vs-cp1252
	# following code doesn't work in IDE because PyCharm uses UTF-8 and not encoding from Windows command prompt...
	global ENCODING_STDOUT2
	ENCODING_STDOUT2 = locale.getpreferredencoding()

	# another try: using encoding-guessing of IDE "IDLE"
	# hint from https://mail.python.org/pipermail/tkinter-discuss/2010-December/002602.html
	global ENCODING_LOCALE
	import idlelib.IOBinding
	ENCODING_LOCALE = idlelib.IOBinding.encoding
	print(u'Using encoding "' + ENCODING_LOCALE + u'" for input and trying "' + ENCODING_STDOUT1 + u'" or "' + ENCODING_STDOUT2 + u'" for STDOUT')

def my_print(line):
	"""
	wrapper for print()-function:
	-does explicit conversion from unicode to encoded byte-string
	-when parameter is already a encoded byte-string, then convert to unicode using "encoding cookie" and then to encoded byte-string
	"""
	unicode_line = u''
	if type(line) == str:
		# conversion byte-string -> unicode -> byte-string
		# (first encoding is source file encoding, second one is encoding of console)
		if not ENCODING_LOCALE:
			get_encoding()
		unicode_line = line.decode(ENCODING_LOCALE)
	else:
		# assuming unicode-string (we don't care about other situations, when called with wrong datatype then print() will throw exception)
		unicode_line = line

	if not (ENCODING_STDOUT1 and ENCODING_STDOUT2):
		get_encoding()
	# when a character isn't available in given ENCODING, then it gets replaced by "?". Other options:
	# http://stackoverflow.com/questions/3224268/python-unicode-encode-error
	try:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT1, errors='strict')
	except UnicodeEncodeError:
		bytestring_line = unicode_line.encode(ENCODING_STDOUT2, errors='strict')
	print(bytestring_line)



class _Gradient_Segment(object):

	# holding values from last gradient segment
	# =>start state: (0,0,0), thats RGB-value of Black
	last_rgb_coord = Point3D(0, 0, 0)
	curr_pathpos_sympyFloat = sympy.Float(0.0)
	counter = 0

	''' color gradient with begin and end as three dimensional coordinate point in 8bit RGB '''
	def __init__(self, next_rgb_coord_tup):
		# we expect a tuple of 8bit integers as RGB-tuple and calculate internally with sympy objects
		# =>begin of this segment is same as end of the last segment
		self._begin = _Gradient_Segment.last_rgb_coord

		end_tup = map(int, next_rgb_coord_tup)
		assert len(end_tup) == 3 and min(end_tup) >= 0 and max(end_tup) <= 255, u'RGB value as tuple of three 8bit integers expected!'
		self._end = Point3D(end_tup)

		# position on complete path where this gradient starts
		self._pathpos = _Gradient_Segment.curr_pathpos_sympyFloat

		self.counter = _Gradient_Segment.counter

		# update values for next segment
		_Gradient_Segment.last_rgb_coord = self._end
		_Gradient_Segment.curr_pathpos_sympyFloat = self._get_pathpos_end()
		_Gradient_Segment.counter += 1

	def _get_pathpos_end(self):
		return self._pathpos + self._begin.distance(self._end)

	def get_distance(self, rgb_parservar):
		seg = Segment3D(self._begin, self._end)
		requested_pnt = Point3D(rgb_parservar.get_tuple())
		return seg.distance(requested_pnt).evalf(NOF_DECIMAL_DIGITS)

	def get_pathpos(self, rgb_parservar):
		seg = Segment3D(self._begin, self._end)
		requested_pnt = Point3D(rgb_parservar.get_tuple())

		# analyze position of rectangular intersection between our gradient and searched RGB point
		# (following line doesn't always work... seems a bug in sympy...)
		#perpendicular_pnt = seg.projection(requested_pnt)

		# if seg.contains(perpendicular_pnt):
		# 	# need a value on our gradient segment
		# 	return float(self._pathpos + self._begin.distance(perpendicular_pnt))
		# else:
		# 	# RGB value is out of our gradient. =>return pathposition of the nearest endpoint.
		# 	if self._begin.distance(requested_pnt) < self._end.distance(requested_pnt):
		# 		return float(self._pathpos)
		# 	else:
		# 		return self._get_pathpos_end()


		# workaround: mapping it to 2D: first draw the triangle from distances between the three 3D coordinates
		a_point2D = Point(0,0)
		b_point2D = Point(0, self._begin.distance(self._end))
		seg2D = Segment(a_point2D, b_point2D)
		circle_a = Circle(a_point2D, self._begin.distance(requested_pnt))
		circle_b = Circle(b_point2D, self._end.distance(requested_pnt))
		requested_pnt2D = circle_a.intersection(circle_b)[0]
		perpendicular_pnt2D = seg2D.projection(requested_pnt2D)

		if seg2D.contains(perpendicular_pnt2D):
			# need a value on our gradient segment
		 	return (self._pathpos + seg2D.p1.distance(perpendicular_pnt2D)).evalf(NOF_DECIMAL_DIGITS)
		else:
			# RGB value is out of our gradient. =>return pathposition of the nearest endpoint.
		 	if seg2D.p1.distance(requested_pnt2D) < seg2D.p2.distance(requested_pnt2D):
				return self._pathpos.evalf(NOF_DECIMAL_DIGITS)
			else:
				return self._get_pathpos_end().evalf(NOF_DECIMAL_DIGITS)


	def get_serialized_tuple(self):
		''' returns endpoint as tuple(pathpos_str, RGB_value_int) in PSC format '''

		pathpos = self._get_pathpos_end().evalf(NOF_DECIMAL_DIGITS)
		# float serialization has always precision 10E-6
		pathpos_str = u'{:.6f}'.format(pathpos)

		# convert 3D-coordinate back to RGB
		color_tuple = self._end.x, self._end.y, self._end.z
		rgb_parservar = PscVar_RGB()
		rgb_parservar.set_value(color_tuple)

		return pathpos_str, rgb_parservar.get_serialized()



class Gradient_Path(object):
	''' holds whole gradient path assembled from all segments '''
	# by using PscVar_RGB objects we always get a valid 8bit RGB value

	def __init__(self):
		self._segments_list = []
		self._pathpos_caching_dict = {}


	def append_rgb_obj(self, rgb_parservar):
		'''  appending a new PscVar_RGB as new gradient endpoint '''
		curr_seg = _Gradient_Segment(next_rgb_coord_tup=rgb_parservar.get_tuple())
		if DEBUGGING:
			my_print(u'added gradient segment number ' + str(curr_seg.counter))
		self._segments_list.append(curr_seg)


	def get_pathpos(self, rgb_parservar):
		''' search closest path position for given PscVar_RGB '''

		if rgb_parservar in self._pathpos_caching_dict:
			# use our cache
			return self._pathpos_caching_dict[rgb_parservar]
		else:
			# search segment with closest match
			# (the following code part returns always segment number 0... =>now we do it more verbose...
			## with help from    https://wiki.python.org/moin/HowTo/Sorting#Operator_Module_Functions
			## and   https://docs.python.org/2/library/operator.html
			#closest_seg = sorted(self._segments_list, key=lambda rgb_parservar: methodcaller('get_distance', rgb_parservar))[0]

			closest_seg = self._segments_list[0]
			for segment in self._segments_list[1:]:
				if segment.get_distance(rgb_parservar) < closest_seg.get_distance(rgb_parservar):
					# choosing closer segment
					closest_seg = segment

			if DEBUGGING:
				my_print(u'"get_pathpos(' + repr(rgb_parservar) + u')": closest segment has number ' + str(closest_seg.counter))

			# update pathpos cache
			# FIXME: should we limit the size of our cache?
			pathpos = closest_seg.get_pathpos(rgb_parservar)
			self._pathpos_caching_dict[rgb_parservar] = pathpos
			return pathpos


	def print_serialisation(self):
		''' print whole gradient path in serialized form for PSC file '''

		# example appearance in PSC file for two points:
		# IBGN;2;Testval1;1;0.000000;0;255.000000;255
		#
		# explanation:
		# IBGN ; <nof_points> ; <DMS-key> ; <1==show_gradient> ; <float1> ; <RGB1> ; <float2> ; <RGB2>

		PSC_MARK = u'IBGN'
		nof_points = len(self._segments_list) + 1
		nof_points_str = str(nof_points)
		DMS_KEY = u'Testval1'
		SHOW_GRADIENT = u'1'

		# minimum is one black point.
		points_serialized_list = [u'0.000000', u'0']
		if nof_points > 1:
			for seg in self._segments_list:
				flt_str, rgb_str = seg.get_serialized_tuple()
				points_serialized_list.append(flt_str)
				points_serialized_list.append(rgb_str)

		# glue everything together
		my_print(u';'.join([PSC_MARK, nof_points_str, DMS_KEY, SHOW_GRADIENT] + points_serialized_list))


class BlinkenlightsRGB_Emulator(object):

	EMULATOR_DMS_KEY = "BlinkenlightsRGB_Emulator"

	@classmethod
	def generate_colormapping(cls, nof_points):
		# mapping in Grafikeditor and DMS for every pixel:
		# wanted RGB-value -> pathposition on closests gradient as DMS-value -> Grafikeditor shows interpolated RGB-value
		# =>we build random lines through threedimensional RGB colorspace for getting a good color mapping
		# =>lines are always between different sides of the cube

		my_print(u'************************************************************')
		my_print(u'Generating of new random colormapping with ' + str(nof_points) + u' points...')

		class _Cubeside(object):
			''' generating random coordinates on one cubeside '''

			def __init__(self, fixed_axe_str, fixed_value_int):
				if 0 < fixed_value_int < 255:
					raise ValueError(u'"fixed_value_int" must be exactly 0 or 255')

				if fixed_axe_str == 'R':
					self._red_values = [fixed_value_int]
					self._green_values = range(256)
					self._blue_values = range(256)
				elif fixed_axe_str == 'G':
					self._red_values = range(256)
					self._green_values = [fixed_value_int]
					self._blue_values = range(256)
				elif fixed_axe_str == 'B':
					self._red_values = range(256)
					self._green_values = range(256)
					self._blue_values = [fixed_value_int]
				else:
					raise ValueError(u'"fixed_axe_str" must be "R", "G" or "B"')

			def get_random_coordinate_tuple(self):
				r = random.choice(self._red_values)
				g = random.choice(self._green_values)
				b = random.choice(self._blue_values)
				return r, g, b


		curr_path = Gradient_Path()
		# first append all cube edges including direct connection between black and white (0,0,0) <-> (255,255,255)
		# since these color gradients could possibly occour oftener than others.
		# =>it's impossible to interconnect these in one turn:
		# https://math.stackexchange.com/questions/253253/tracing-the-edges-of-a-cube-with-the-minimum-pencil-lifts
		#
		#    h ******** g
		#     *      *
		#    *      *
		# e ******** f
		#
		#    d ******** c
		#     *      *
		#    *      *
		# a ******** b
		#
		# startpoint in Gradient_Path() is always (0,0,0)
		# =>adding a->b->c->d->a  ->g->h->e->f->g  ->c->e->a  ->f->b->d->h
		point_list = [(255, 0, 0), # b
		              (255, 255, 0), # c
		              (0, 255, 0),  # d
		              (0, 0, 0),  # a
		              (255, 255, 255),  # g
		              (0, 255, 255),  # h
		              (0, 0, 255),  # e
		              (255, 0, 255),  # f
		              (255, 255, 255),  # g
		              (255, 255, 0),  # c
		              (0, 0, 255),  # e
		              (0, 0, 0),  # a
		              (255, 0, 255),  # f
		              (255, 0, 0),  # b
		              (0, 255, 0),  # d
		              (0, 255, 255)]  # h
		rgb_var = PscVar_RGB()
		for point in point_list:
			rgb_var.set_value(point)
			curr_path.append_rgb_obj(rgb_var)

		# preparing random coordinates on six sides...
		cubesides_list = [_Cubeside('R', 0),
		                  _Cubeside('R', 255),
		                  _Cubeside('G', 0),
		                  _Cubeside('G', 255),
		                  _Cubeside('B', 0),
		                  _Cubeside('G', 255)]

		# generating gradient path over all randomly chosen coordinate/color points
		rgb_var = PscVar_RGB()
		for x in range(nof_points):
			coord_tuple = random.choice(cubesides_list).get_random_coordinate_tuple()
			rgb_var.set_value(coord_tuple)
			curr_path.append_rgb_obj(rgb_var)

		my_print('=>Serialisation of generated gradient path:')
		curr_path.print_serialisation()
		my_print(u'************************************************************')


	def __init__(self, filename_str, curr_dms, endless_movie=True):
		#self.blmovie = BlmFile(filename_str=filename_str)
		self.endless_movie = endless_movie
		self.curr_dms = curr_dms
		self.curr_width = 0
		self.curr_height = 0
		#self._check_consistence()
		#self._blank_display()





def main(filename, argv=None):
	get_encoding()

	my_print(u'misc.BlinkenlightsRGB_Emulator.py')
	my_print(u'*********************************')

	'''
	# some tests
	if False:
		grad1 = _Gradient_Segment((0xff, 0, 0))
		grad2 = _Gradient_Segment((0xff, 0xff, 0))
		grad3 = _Gradient_Segment((0xff, 0xff, 0xff))
		grad4 = _Gradient_Segment((0x00, 0x00, 0x00))

		test_points = [(0,0,0),
		               (0xff, 0, 0),
		               (0xff, 0xff, 0),
		               (0xff, 0xff, 0xff),
		               (0x7f, 0x7f, 0x7f),
		               ]

		for grad in [grad1, grad2, grad3, grad4]:
			my_print(u'*****************')
			for coord in test_points:
				rgb_var = PscVar_RGB()
				rgb_var.set_value(coord)
				my_print(u'Test-coordinate: ' + repr(rgb_var) + u' // grad.get_pathpos(rgb_var)=' + str(grad.get_pathpos(rgb_var)) + ' // grad.get_distance(rgb_var)=' + str(grad.get_distance(rgb_var)))

	if True:
		mypath = Gradient_Path()
		mypath.append_rgb_obj(PscVar_RGB('#FF0000'))
		mypath.append_rgb_obj(PscVar_RGB('#FFFF00'))
		mypath.append_rgb_obj(PscVar_RGB('#FFFFFF'))
		mypath.append_rgb_obj(PscVar_RGB('#000000'))

		my_print('Serialisation of current gradient path:')
		mypath.print_serialisation()

		test_points = [(0, 0, 0),
		               (0xff, 0, 0),
		               (0xff, 0xff, 0),
		               (0xff, 0xff, 0xff),
		               (0x7f, 0x7f, 0x7f),
		               ]

		for coord in test_points:
			rgb_var = PscVar_RGB()
			rgb_var.set_value(coord)
			my_print(u'Test-coordinate: ' + repr(rgb_var) + u' // mypath.get_pathpos(rgb_var)=' + str(mypath.get_pathpos(rgb_var)))
	'''

	curr_dms = dms.dmspipe.Dmspipe()
	if DEBUGGING:
		my_print(u'INFO: Currently this project is running:')
		prj = curr_dms.pyDMS_ReadSTREx('System:Project')
		computer = curr_dms.pyDMS_ReadSTREx('System:NT:Computername')
		my_print(u'\t"System:Project"=' + prj)
		my_print(u'\t"System:NT:Computername"=' + computer)

	curr_emulator = BlinkenlightsRGB_Emulator(filename, curr_dms)

	BlinkenlightsRGB_Emulator.generate_colormapping(20)

	'''
	if DEBUGGING:
		my_print('\nstarting Blinkenlights movie... :-)')
	try:
		curr_emulator.play_moviefile()
	except RuntimeError:
		return 1
	return 0        # success
	'''

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='BlinkenlightsRGB emulator for ProMoS NT(c).')

	parser.add_argument('FILENAME', help='filename of Blinkenlights movie (*.blm, *.bmm, *.bml, *.bbm)')

	args = parser.parse_args()
	status = main(filename=args.FILENAME)
	sys.exit(status)