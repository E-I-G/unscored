import sys
import os
import time
import argparse

import eventlet
eventlet.monkey_patch()

from utils import logger, helpers

import state as st
import database
import ingest
import webserver


parser = argparse.ArgumentParser()
parser.add_argument('--discover', action='store_true', required=False)
parser.add_argument('--backingest', action='store_true', required=False)
parser.add_argument('--ingestlogs', action='store', required=False)
parser.add_argument('--discovermod', action='store', required=False)
parser.add_argument('-a', '--add', action='store', required=False)

known, unknown = parser.parse_known_args()


def mode_discover():
	with database.DBRequest() as db:
		ingest.discover_communities(db)
	logger.log('Job finished')
	sys.exit()

def mode_discovermod(moderators):
	for moderator in moderators:
		ingest.discover_communities_from_mod(moderator)
	logger.log('Job finished')
	sys.exit()

def mode_ingestlogs(communities):
	def thread_ingestlog(community):
		with database.DBRequest() as db:
			ingest.ingest_complete_modlog(db, community)
	for community in communities:
		helpers.thread('IngestLog-%s' % community, thread_ingestlog, community)

def mode_add(communities):
	for name in communities:
		ingest.discover_community(name)
	logger.log('Job finished')
	sys.exit()


def main():
	os.chdir(os.path.abspath(os.path.dirname(os.path.dirname(sys.argv[0]))))
	st.load_config()
	st.load_state()
	st.load_ipblocks()
	logger.start_logger(st.config['log_directory'], st.config['log_level'])
	logger.log('Starting Unscored server ver. %s' % st.VERSION)
	database.init_database()
		
	try:
		if known.discover:
			mode_discover()
		
		if known.discovermod:
			mode_discovermod(known.discovermod.split(','))

		if known.ingestlogs:
			mode_ingestlogs(known.ingestlogs.split(','))

		if known.add:
			mode_add(known.add.split(','))

		if known.backingest:
			helpers.thread('BackIngest', ingest.thread_backingest)

		if st.config['ingest_enabled']:
			freq = st.get_ingest_frequency_stat()
			logger.log('Average ingests per day: %d (every %s seconds)' % (int(freq), round(24*60*60/freq, 2)))
			helpers.thread('Ingest', ingest.thread_ingest)
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