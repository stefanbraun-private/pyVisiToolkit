# BrS, 8.12.2016

# based on example from http://www.python-course.eu/tkinter_entry_widgets.php
# and improvements from http://effbot.org/tkinterbook/entry.htm
# and idea from https://docs.python.org/2/library/itertools.html#itertools.product

from Tkinter import *
import itertools
import functools


def evaluate(event):
	# example: iteration over text lines:
	# http://stackoverflow.com/questions/17485382/tkinter-text-widget-iterating-over-lines
	
	# turn text into sets (then we have unique elements!)
	set1 = set(entry1.get('1.0', 'end-1c').splitlines())
	set2 = set(entry2.get('1.0', 'end-1c').splitlines())
	#console.write('DEBUGGING: <char> = ' + repr(event.char) + '\n')
	
	# when in state "readonly", then it's not possible to call delete() or insert()...
	res.config(state=NORMAL)
	res.delete(1.0, END)
	
	# create third list
	for mytuple in itertools.product(sorted(set2), sorted(set1)):
		if mytuple[0] != '' and mytuple[1] != '':
			myrow = ''.join([mytuple[1], mytuple[0], '\n'])
			res.insert(END, myrow)
	res.config(state=DISABLED)
		

w = Tk()
Label(w, text="Cartesian Product (e.g. produce list of DMS keys from BMO-instances and BMO-subkeys)").pack()

Label(w, text="list no. 1 (e.g. BMO-instances)").pack()
entry1 = Text(w, width=150, height=20)
entry1.bind("<KeyRelease>", evaluate)
entry1.pack(fill=BOTH)

Label(w, text="list no. 2 (e.g. BMO-subkeys)").pack()
entry2 = Text(w, width=150, height=10)
entry2.bind("<KeyRelease>", evaluate)
entry2.pack(fill=BOTH)

Label(w, text="cartesian product, sorted by second list").pack()
res = Text(w, width=150, height=20)
res.config(state=DISABLED)
res.pack(fill=BOTH)
w.mainloop()