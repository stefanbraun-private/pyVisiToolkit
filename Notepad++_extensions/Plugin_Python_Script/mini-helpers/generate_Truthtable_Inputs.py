# BrS, 20.3.2017

# based on example from http://www.python-course.eu/tkinter_entry_widgets.php
# and improvements from http://effbot.org/tkinterbook/entry.htm
# and idea from https://docs.python.org/2/library/itertools.html#itertools.product
# and http://stackoverflow.com/questions/6336424/python-build-a-dynamic-growing-truth-table

from Tkinter import *
import itertools

MAX_NOF_VARIABLES = 6

def evaluate(event):
	try:
		nof_inputs = int(entry1.get())
		
		if nof_inputs <= MAX_NOF_VARIABLES and nof_inputs > 0:
			entry1['bg'] = 'white'
			
			# when in state "readonly", then it's not possible to call delete() or insert()...
			res.config(state=NORMAL)
			res.delete(1.0, END)
			
			# fill result field
			for mytuple in itertools.product([0, 1], repeat=nof_inputs):
				myrow = '\t'.join(map(str, mytuple))
				res.insert(END, myrow + '\n')
		else:
			entry1['bg'] = 'red'
	except ValueError as ex:
		console.clear()
		console.show()
		console.show()
		console.write('Exception in "generate_Truthtable_Inputs.py": ' + repr(ex) + '\n')
		console.write('\t=>only positive integers are valid input!\n')
	res.config(state=DISABLED)
		

w = Tk()
Label(w, text="Truthtable input combinations generator").pack()

Label(w, text="number of binary input variables (up to " + str(MAX_NOF_VARIABLES) + ' are allowed)').pack()
entry1 = Entry(w, width=50)
entry1.bind("<KeyRelease>", evaluate)
entry1.pack(fill=BOTH)

Label(w, text="truthtable").pack()
res = Text(w, width=50, height=50)
res.config(state=DISABLED)
res.pack(fill=BOTH)
w.mainloop()