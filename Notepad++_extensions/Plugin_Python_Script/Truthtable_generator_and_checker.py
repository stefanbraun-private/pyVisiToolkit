#!/usr/bin/env python
# encoding: utf-8
"""
Truthtable_generator_and_checker.py

generates from a given list of binary variables a table with all input combinations
and evaluates two given expressions according to this combinations.
=>this helps developing boolean logics and allows efficient comparisons of different implementations.

Copyright (C) 2017 Stefan Braun

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

# based on example from http://www.python-course.eu/tkinter_entry_widgets.php
# and improvements from http://effbot.org/tkinterbook/entry.htm
# and idea from https://docs.python.org/2/library/itertools.html#itertools.product
# and http://stackoverflow.com/questions/6336424/python-build-a-dynamic-growing-truth-table


import itertools
from Tkinter import *

MAX_NOF_VARIABLES = 6

class myGui(Tk):
	def __init__(self):
		Tk.__init__(self)
	
		Label(self, text="Truthtable generator and checker").pack(pady=12)
		Label(self, text="Hint 1: insert max. " + str(MAX_NOF_VARIABLES) + " comma separated input variables").pack(anchor='w')
		Label(self, text="Hint 2: expression evaluation uses eval() and needs valid Python variable names").pack(anchor='w')
		Label(self, text="Hint 3: use bitwise operators | & ~ ^ to evaluate all variables (prevent short-circuit-evaluation of expressions)").pack(anchor='w')
		
		entry_frm = self._build_entry_frame()
		entry_frm.pack(pady=12)
		
		output_frm = self._build_output_frame()
		output_frm.pack()
	
	def _build_entry_frame(self):
		frm = Frame(self)
		
		Label(frm, text="list of binary inputs").grid(row=0, column=0)
		self._entry_vars = Entry(frm, width=80)
		self._entry_vars.grid(row=0, column=1)
		self._entry_vars.bind("<KeyRelease>", self._cb_evaluate)
		
		Label(frm, text="Python expression 1").grid(row=1, column=0)
		# list with both expression entry fields for improved handling
		self._entry_expr = []
		self._entry_expr.append(Entry(frm, width=80))
		self._entry_expr[0].grid(row=1, column=1)
		self._entry_expr[0]['bg'] = 'red'
		self._entry_expr[0].bind("<KeyRelease>", self._cb_evaluate)
		
		Label(frm, text="Python expression 2").grid(row=2, column=0)
		self._entry_expr.append(Entry(frm, width=80))
		self._entry_expr[1].grid(row=2, column=1)
		self._entry_expr[1]['bg'] = 'red'
		self._entry_expr[1].bind("<KeyRelease>", self._cb_evaluate)

		return frm

		
	def _build_output_frame(self):
		frm = Frame(self)
		
		# input combinations frame
		comb_frm = Frame(frm)
		Label(comb_frm, text="Input combinations").pack()
		self._comb_text = Text(comb_frm, width=50, height=50)
		self._comb_text.config(state=DISABLED)
		self._comb_text.pack()
		comb_frm.grid(row=0, column=0)
		
		# output functions frame
		outp_frm = Frame(frm)
		Label(outp_frm, text="Output for each input combination").pack()
		self._outp_text = Text(outp_frm, width=50, height=50)
		self._outp_text.config(state=DISABLED)
		self._outp_text.pack()
		outp_frm.grid(row=0, column=1)
		
		
		return frm
		

	def _cb_evaluate(self, event):
		try:
			my_vars = self._entry_vars.get().replace(',', ' ').split()
			nof_inputs = len(my_vars)
			
			if nof_inputs <= MAX_NOF_VARIABLES and nof_inputs > 0:
				self._entry_vars['bg'] = 'green'
				
				# first delete whole output fields before adding new content
				# when in state "readonly", then it's not possible to call delete() or insert()...
				self._comb_text.config(state=NORMAL)
				self._comb_text.delete(1.0, END)
				self._outp_text.config(state=NORMAL)
				self._outp_text.delete(1.0, END)
				
				
				curr_expr_list = []
				for idx in range(2):
					curr_expr_list.append(self._entry_expr[idx].get())
				
				# fill header rows, then output fields
				# (header row in "input combination field": our variable list)
				self._comb_text.insert(END, '\t'.join(my_vars) + '\n')
				self._outp_text.insert(END, '\t'.join(['Expr1', 'Expr2', 'Analysis']) + '\n')
				for mytuple in itertools.product([False, True], repeat=nof_inputs):
					# appending one row in each output field:
					
					# one input combination
					myrow = self._replace_bin_values('\t'.join(map(str, mytuple)))
					self._comb_text.insert(END, myrow + '\n')
					
					
					# output values for both expressions
					if curr_expr_list[0] or curr_expr_list[1]:
						# evaluate given expression with current input variable values
						# set test condition for eval(): building local variables dictionary
						mylocals = dict(zip(my_vars, mytuple))
					
						output_values = ['X', 'X']
						for idx in range(2):
							try:
								# calling eval() mostly safe (according to http://lybniz2.sourceforge.net/safeeval.html )
								output_values[idx] = eval(curr_expr_list[idx], {}, mylocals)
								self._entry_expr[idx]['bg'] = 'green'
							except Exception as ex:
								# current expression contains errors...
								self._entry_expr[idx]['bg'] = 'red'
						# fill output field
						myrow = self._replace_bin_values('\t'.join(map(str, output_values)))
						analysis_str = ''
						if not 'X' in output_values:
							# both values seem to be valid...
							# =>check for equality
							if output_values[0] == output_values[1]:
								analysis_str = 'EQUAL'
							else:
								analysis_str = 'NOT EQUAL'
						else:
							analysis_str = '---'
						self._outp_text.insert(END, myrow + '\t' + analysis_str + '\n')
						
			else:
				self._entry_vars['bg'] = 'red'
		except ValueError as ex:
			console.clear()
			console.show()
			console.write('Exception in "Truthtable.py": ' + repr(ex) + '\n')
		# protect output fields against corruption (e.g. user want's to select text but he does changes to output)
		self._comb_text.config(state=DISABLED)
		self._outp_text.config(state=DISABLED)

	def _replace_bin_values(self, curr_str):
		# for better readability:
		# "True" => "1"
		# "False" => "0"
		return curr_str.replace('True', '1').replace('False', '0')

		

def main(argv=None):
	root = myGui()
	root.mainloop()

	return 0        # success


if __name__ == '__main__':
	status = main()
	#sys.exit(status)