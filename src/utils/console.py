import os
import sys
import queue

try:
	import colorconsole.terminal
except ImportError:
	SUPPORTED = False
else:
	SUPPORTED = True
	term = colorconsole.terminal.get_terminal()

import utils

lnQueue = queue.SimpleQueue()

COLORS = {
	'black': 0,
	'gray': 8 if os.name == 'nt' else 7,
	'lightgray': 7,
	'blue': 9 if os.name == 'nt' else 4,
	'darkblue': 1 if os.name == 'nt' else 4,
	'red': 12 if os.name == 'nt' else 1,
	'darkred': 4 if os.name == 'nt' else 1,
	'green': 2 if os.name == 'nt' else 2,
	'lightgreen': 10 if os.name == 'nt' else 2,
	'cyan': 3 if os.name == 'nt' else 6,
	'lightcyan': 11 if os.name == 'nt' else 6,
	'purple': 5,
	'magenta': 13 if os.name == 'nt' else 5,
	'yellow': 14 if os.name == 'nt' else 3,
	'white': 15 if os.name == 'nt' else 7,
}

class FT:
	def __init__(self, text, fg='', bg=''):
		self.text = text
		self.fg = COLORS.get(fg)
		self.bg = COLORS.get(bg)

	def display(self):
		if SUPPORTED:
			term.set_color(self.fg, self.bg)
			sys.stdout.write(self.text)
			term.reset()
		else:
			sys.stdout.write(self.text)



def _println(textObjs):
	i = 0
	for t in textObjs:
		i+=1
		if isinstance(t, str):
			t = FT(t)
		t.display()
	sys.stdout.write('\n')

def println(*textObjs):
	if utils.CONSOLE_THREADING:
		lnQueue.put(textObjs)
	else:
		_println(textObjs)



stopConsole = False
def queue_thread():
	while not stopConsole:
		textObjs = lnQueue.get()
		_println(textObjs)

def process_queue():
	try:
		while True:
			textObjs = lnQueue.get_nowait()
			_println(textObjs)
	except queue.Empty:
		pass