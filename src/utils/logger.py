import os
import time
import threading
import queue
import traceback
import json

import utils
from utils import console
from utils.console import FT
from utils import helpers


LOG_LEVELS = {
	'TRACE': 0,
	'DEBUG': 1,
	'INPUT': 2,
	'INFO': 3,
	'WARNING': 4,
	'ERROR': 5,
	'FATAL': 6
}

TERMINAL_LOG_COLORS = {
	'ERROR': 'red',
	'FATAL': 'darkred',
	'WARNING': 'yellow', 
	'INPUT': 'white',
	'INFO': 'white',
	'TRACE': 'gray',
	'DEBUG': 'gray'
}


loggerQueue = queue.Queue(maxsize=-1)



def make_lines(logData):
	"""Supported: list of LogRecord, list of str, log file string."""
	if isinstance(logData, str):
		logData = [LogRecord(ln.strip()) for ln in logData.splitlines() if ln.strip()]
	if logData and isinstance(logData[0], str):
		logData = [LogRecord(ln.strip()) for ln in logData if ln.strip()]
	return logData


class LogRecord:
	def __init__(self, raw=None, timestamp=0, thread='', level='INFO', text=''):
		if raw:
			self.timestamp = time.mktime(time.strptime(raw[:19], '%Y-%m-%d %H:%M:%S'))
			th_and_level = raw[raw.find('[')+1:raw.find(']')]
			self.thread = th_and_level[:th_and_level.rfind('/')]
			self.level = th_and_level[th_and_level.rfind('/')+1:]
			self.text = raw[raw.find(']')+4:]
		else:
			self.timestamp = timestamp if timestamp else int(time.time())
			self.thread = thread if thread else helpers.threadname()
			self.level = level
			self.text = text

	def get_timestr(self, tz_offset=None):
		return helpers.timestr(self.timestamp, tz_offset=tz_offset)

	def get_levelnum(self):
		return LOG_LEVELS.get(self.level, 0)

	def export(self):
		return '%s [%s/%s] > %s' % (self.get_timestr(), self.thread, self.level, self.text)

	def __str__(self):
		return self.export()


class RCLogger:
	_isNewFile = False
	def __init__(self, path, level=0):
		self.wasOpened = False
		if os.path.isfile(path):
			self.path = path
		else:
			extension = 'log'
			self.path = os.path.join(path, '%d.%s' % (int(time.time()), extension))
			self._isNewFile = True
		self.running = False
		self.logFile = None
		self.count = 0
		self.set_level(level)

	def set_level(self, level):
		if isinstance(level, str):
			level = LOG_LEVELS.get(level, 0)
		self.level = level

	def open(self):
		if self.wasOpened:
			raise RuntimeError('Logger was already opened')
		if self._isNewFile:
			if os.path.isfile(self._isNewFile):
				raise FileExistsError
			os.makedirs(os.path.dirname(self.path), exist_ok=True)
		self.logFile = open(self.path, 'a', 1, encoding='utf-8')
		self.running = True
		self.wasOpened = True

	def _write_ln(self, record: LogRecord, flush=True):
		output = record.export()
		self.logFile.write(output + '\n')
		if flush:
			self.logFile.flush()

	def add(self, record: LogRecord):
		if not self.running:
			raise RuntimeError('Logger is not running')
		if LOG_LEVELS.get(record.level, 0) >= self.level:
			self.count += 1
			self._write_ln(record, flush=False)

	def get_data(self):
		with open(self.path, 'r') as f:
			return make_lines(f.read())

	def flush(self):
		if self.running:
			self.logFile.flush()

	def close(self):
		self.logFile.flush()
		self.logFile.close()
		self.running = False


curLogger: RCLogger = None


def _logger_thread(loggerObj):
	while True:
		try:
			entry = loggerQueue.get(timeout=5)
		except queue.Empty:
			if not loggerObj.running:
				return
		else:
			if not loggerObj.running:
				return
			try:
				_write_log_record(entry)
			except Exception:
				import traceback; traceback.print_exc()


def start_logger(path, level=0):
	global curLogger
	if curLogger and curLogger.running:
		raise RuntimeError('A logger is already running')
	curLogger = RCLogger(path, level)
	curLogger.open()
	if utils.THREADED_LOG:
		helpers.thread('Logger', _logger_thread, curLogger)


def stop_logger(stopped_ok=True):
	global curLogger
	if not curLogger or not curLogger.running:
		if stopped_ok: return
		raise RuntimeError('Logger is not running')
	curLogger.close()
	curLogger = None


def reload_with_new_file():
	global curLogger
	if curLogger and curLogger.running:
		old = curLogger
		log('Reloading logger in new file')
		stop_logger(stopped_ok=True)
		start_logger(os.path.dirname(old.path), old.level)
		log('Continued from log %s' % old.path)


def logger_is_running():
	return curLogger is not None and curLogger.running


def get_cur_filename():
	if not logger_is_running():
		return None
	return curLogger.path



def _write_log_record(record: LogRecord):
	if utils.PRINT_LOG:
		if utils.COLORPRINT:
			console.println(
				FT(record.get_timestr() + ' ', 'lightgray'),
				FT('[', 'lightgray'),
				FT(record.thread, 'lightgray'),
				FT('/', 'lightgray'),
				FT(record.level, TERMINAL_LOG_COLORS.get(record.level)),
				FT('] > ', 'lightgray'),
				FT(record.text, TERMINAL_LOG_COLORS.get(record.level))
			)
		else:
			print(record)
	if not logger_is_running():
		raise SystemExit(0)
	curLogger.add(record)

def _log(record: LogRecord):
	if curLogger is not None and curLogger.running and record.get_levelnum() >= curLogger.level:
		if utils.THREADED_LOG:
			loggerQueue.put(record)
		else:
			_write_log_record(record)

def log(text, level='INFO', thread=None, timestamp=None):
	text = str(text).replace('\n', ' ').replace('\r', ' ').replace('\t', '    ')
	record = LogRecord(None, timestamp, thread, level, text)
	_log(record)

def logtrace(text): log(text, 'TRACE')
def logdebug(text): log(text, 'DEBUG')
def loginput(text): log(text, 'INPUT')
def loginfo(text): log(text, 'INFO')
def logwrn(text): log(text, 'WARNING')
def logerr(text): log(text, 'ERROR')
def logfatal(text): log(text, 'FATAL')


def format_traceback_for_log(exc=None):
	if exc is None:
		tbFormat = traceback.format_exc()
	else:
		tbFormat = '\n'.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
	return [ln.rstrip().replace('\t', '    ') for ln in tbFormat.splitlines() if ln.strip()]

def log_traceback(level='ERROR', exc=None):
	for ln in format_traceback_for_log(exc):
		log(ln, level)