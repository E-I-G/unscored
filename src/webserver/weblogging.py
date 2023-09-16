import time

import flask

from utils import logger
import state as st

def log_completed_request():
	data = flask.g.requestData
	ms = int((time.time() - flask.g.startTime) * 1000)
	level = st.config['log_weblevel']
	logger.log('[Web] %s: %s %s - %d %d ms' % (data['addr'], data['method'], data['url'], data['status'], ms), level)


def log_unhandled_error(error):
	logger.logerr('Unhandled web server error')
	logger.log_traceback('ERROR', error)


def log_request_error(error):
	lines = logger.format_traceback_for_log(error)
	for ln in lines:
		logger.logerr('[Web error] ' + ln)
	return lines



def is_json_request():
	return flask.request.path.startswith('/ajax/')