# BrS, 15.4.2016

# example from http://www.python-course.eu/tkinter_entry_widgets.php
# and improvements from http://effbot.org/tkinterbook/entry.htm

from Tkinter import *
from math import *

def evaluate(event):
    # when "res" is a Label:
	#res.configure(text = "Ergebnis: " + str(eval(entry.get())))
	
	# now we use another Entry for showing a selectable result:
	# (when in state "readonly", then it's not possible to call delete() or insert()...
	res.delete(0, END)
	res.insert(0, 'Ergebnis: ' + str(eval(entry.get())))

w = Tk()
Label(w, text="Your Python Expression: ").pack()
entry = Entry(w, width=150)
entry.bind("<Return>", evaluate)
entry.pack()
res = Entry(w, text='Ergebnis: ', state='normal', width=150)
res.pack()
w.mainloop()