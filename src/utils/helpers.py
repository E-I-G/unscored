import time
import datetime
import threading
import inspect

from utils import logger

############
### Math ###

def avg(iterable):
	return sum(iterable) / len(iterable)

def clamp(curVal, minVal, maxVal):
	if curVal > maxVal:
		return maxVal
	elif curVal < minVal:
		return minVal
	return curVal

def isint(sourceString):
	try: int(sourceString)
	except ValueError: return False
	else: return True

def isnum(sourceString):
	try: float(sourceString)
	except ValueError: return False
	else: return True
	
def positive_int(value, allowZero=True):
	value = int(value)
	if value < 0:
		raise ValueError('Must be positive')
	elif value == 0 and not allowZero:
		raise ValueError('Must not be zero')
	return value

def positive_float(value, allowZero=True):
	value=float(value)
	if value < 0:
		raise ValueError('Must be positive')
	elif value == 0 and not allowZero:
		raise ValueError('Must not be zero')
	return value

def safeint(value, default=0):
	try:
		return int(value)
	except (ValueError, TypeError):
		return default

def safefloat(value, default=0.0):
	try:
		return float(value)
	except ValueError:
		return default

def safeint_from(value, minimum):
	try:
		return max(minimum, int(value))
	except ValueError:
		return minimum



############
### Time ###

GREGORIAN_YEAR = 31556952
def timeago(timestamp):
	difference = time.time() - timestamp
	if difference < 10:
		return 'just now'
	if difference < 60:
		return '%d seconds ago' % difference
	if difference < 60 * 60:
		minutes = difference // 60
		return '%d minute%s ago' % (minutes, '' if minutes == 1 else 's')
	if difference < 60 * 60 * 24:
		hours = difference // (60 * 60)
		return '%d hour%s ago' % (hours, '' if hours == 1 else 's')
	if difference < GREGORIAN_YEAR / 12:
		days = difference // (60 * 60 * 24)
		return '%d day%s ago' % (days, '' if days == 1 else 's')
	if difference < GREGORIAN_YEAR:
		months = difference // (GREGORIAN_YEAR / 12)
		return '%d month%s ago' % (months, '' if months == 1 else 's')
	years = difference // GREGORIAN_YEAR
	return '%d year%s ago' % (years, '' if years == 1 else 's')


def timestr(value=None, include_date=True, hide_todays_date=False, tz_offset=None):
	"""
	Returns a YYYY-mm-dd HH:MM:SS formatted string. Defaults to the current time.
	Uses local time unless tz_offset provided (in minutes)
	"""
	if value is None:
		value = time.time()
	try:
		if tz_offset is None:
			localTime = time.localtime(float(value))
		else:
			localTime = time.gmtime(float(value) - tz_offset * 60)
		timeString = time.strftime('%Y-%m-%d %H:%M:%S', localTime)
	except ValueError:
		return '<invalid time value>'
	except Exception:
		return '<failed to calculate>'
	else:
		if not include_date:
			timeString = timeString[11:]
		elif hide_todays_date:
			curDate = datetime.datetime.now()
			valDate = datetime.datetime.fromtimestamp(value)
			if curDate.day == valDate.day:
				timeString = timeString[11:]
	return timeString

def time_from_date(date, tz_offset):
	from calendar import timegm
	return timegm(time.strptime(date, '%Y-%m-%d')) + tz_offset * 60



####################################
### Fully qualified object names ###

def fullqualname(obj):
	if type(obj).__name__ == 'builtin_function_or_method':
		return _fullqualname_builtin_py3(obj)

	elif type(obj).__name__ == 'function':
		return _fullqualname_function_py3(obj)
	
	elif type(obj).__name__ in ('member_descriptor', 'method_descriptor', 'wrapper_descriptor'):
		return obj.__objclass__.__module__ + '.' + obj.__qualname__
	
	elif type(obj).__name__ == 'method':
		return _fullqualname_method_py3(obj)
	
	elif type(obj).__name__ == 'method-wrapper':
		return fullqualname(obj.__self__) + '.' + obj.__name__

	elif type(obj).__name__ == 'module':
		return obj.__name__

	elif type(obj).__name__ == 'property':
		return obj.fget.__module__ + '.' + obj.fget.__qualname__

	elif inspect.isclass(obj):
		return obj.__module__ + '.' + obj.__qualname__

	return obj.__class__.__module__ + '.' + obj.__class__.__qualname__


def _fullqualname_builtin_py3(obj):
	if obj.__module__ is not None:
		# built-in functions
		module = obj.__module__
	else:
		# built-in methods
		if inspect.isclass(obj.__self__):
			module = obj.__self__.__module__
		else:
			module = obj.__self__.__class__.__module__

	return module + '.' + obj.__qualname__


def _fullqualname_function_py3(obj):
	if hasattr(obj, "__wrapped__"):
		# Required for decorator.__version__ <= 4.0.0.
		qualname = obj.__wrapped__.__qualname__
	else:
		qualname = obj.__qualname__
	return obj.__module__ + '.' + qualname


def _fullqualname_method_py3(obj):
	if inspect.isclass(obj.__self__):
		cls = obj.__self__.__qualname__
	else:
		cls = obj.__self__.__class__.__qualname__
	return obj.__self__.__module__ + '.' + cls + '.' + obj.__name__



######################
### Multithreading ###

def threadname():
	return threading.current_thread().name

def thread(name, func, *args, logging=True, **kwargs):
	def exec_thread():
		if logging:
			level = 'INFO' if logging else 'TRACE'
			logger.log('Thread started (function %s)' % fullqualname(func), level)
		try:
			func(*args, **kwargs)
		except Exception as e:
			logger.logerr('Unhandled exception in thread - %s: %s' % (e.__class__.__name__, e))
			logger.log_traceback()
		except SystemExit as e:
			if logging:
				logger.log('Thread exited normally (SystemExit with code %s)' % e)
		else:
			if logging:
				logger.log('Thread exited normally (return)')
			
	threading.Thread(target=exec_thread, name=name, daemon=True).start()