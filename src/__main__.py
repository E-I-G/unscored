import sys
import os
import time

import eventlet
eventlet.monkey_patch()

from utils import logger, helpers

import state as st
import database
import ingest
import webserver


def main():
	os.chdir(os.path.abspath(os.path.dirname(os.path.dirname(sys.argv[0]))))
	st.load_config()
	st.load_state()
	st.load_ipblocks()
	logger.start_logger(st.config['log_directory'], st.config['log_level'])
	logger.log('Starting Unscored server ver. %s' % st.VERSION)
	database.init_database()
	if st.config['ingest_enabled']:
		helpers.thread('Ingest', ingest.thread_ingest)
	try:
		webserver.start_webserver()
	except Exception:
		import traceback; traceback.print_exc()
		logger.logfatal('Unhandled exception on main thread')
		logger.log_traceback('FATAL')
	except KeyboardInterrupt:
		logger.logfatal('Closed by KeyboardInterrupt (Ctrl+C)')
	time.sleep(3)
	logger.log('Server closed')


if __name__ == '__main__':
	main()