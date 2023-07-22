import os
import json
import sys
import time

from utils import logger

VERSION = '1.1.2'

DATA_DIR = 'data'

CONFIGURATION_FILE = 'configuration/config.json'
COMMUNITIES_FILE = 'configuration/monitored_communities.json'
SESSION_SECRET_FILE = 'configuration/session_secret'
IPBLOCKS_FILE = 'configuration/blocked_addrs.txt'

INGEST_STATE_FILE = 'data/ingest_state.json'


config = {}
communities = []

def load_config():
	with open(CONFIGURATION_FILE, 'r') as f:
		cfg = json.load(f)
	config.clear()
	config.update(cfg)
	with open(COMMUNITIES_FILE, 'r') as f:
		cfg = json.load(f)
	communities.clear()
	communities.extend(cfg)


ingest = {}

def load_state():
	os.makedirs('data', exist_ok=True)
	if os.path.isfile(INGEST_STATE_FILE):
		with open(INGEST_STATE_FILE, 'r') as f:
			ingest.update(json.load(f))
	for community in communities:
		if community['name'] not in ingest:
			ingest[community['name']] = {
				'domain': community['standalone_domain'],
				'interval': community['interval'],
				'last_post_id': 0,
				'last_comment_id': 0,
				'last_modlog_timestamp': 0,
				'modlogs': None,
				'banlogs': None
			}
		else:
			ingest[community['name']].update({
				'domain': community['standalone_domain'],
				'interval': community['interval']
			})
	if 'global' not in ingest:
		ingest['global'] = {
			'last_post_id': max([community['last_post_id'] for community in ingest.values()]),
			'interval': config['global_interval'],
			'modlogs': False,
			'banlogs': False
		}
	ingest['global']['interval'] = config['global_interval']

def save_state():
	with open(INGEST_STATE_FILE, 'w') as f:
		json.dump(ingest, f, indent='\t')



def restart_application():
	path = ('"' + sys.argv[0] + '"') if os.name == 'nt' else sys.argv[0]
	if getattr(sys, 'frozen', False):
		os.execl(sys.executable, *sys.argv[1:])
	else:
		os.execl(sys.executable, os.path.basename(sys.executable), path, *sys.argv[1:])



#################################
### IP blocks and rate limits ###

class RequestBlocked(Exception): pass
class AddressBlocked(RequestBlocked): pass
class RateLimitExceeded(RequestBlocked): pass


blockedIPs = set()

def load_ipblocks():
	if not os.path.isfile(IPBLOCKS_FILE):
		with open(IPBLOCKS_FILE, 'w'):
			pass
	with open(IPBLOCKS_FILE, 'r') as f:
		for line in f:
			if line.strip():
				blockedIPs.add(line.strip())

def save_ipblocks():
	with open(IPBLOCKS_FILE, 'w') as f:
		for addr in blockedIPs:
			f.write(addr + '\n')
	logger.log('Saved IP blocks')

def block_ip(addr):
	blockedIPs.add(addr)
	logger.log('Blocked IP: %s' % addr)
	save_ipblocks()

def unblock_ip(addr):
	try:
		blockedIPs.remove(addr)
	except KeyError:
		logger.logerr('Blocked IP not found: %s' % addr)
	else:
		logger.log('Unblocked IP: %s' % addr)
		save_ipblocks()



rateLimit = {}
nextRateLimitReset = time.time() + 2 * 60

def enforce_api_ratelimit(addr):
	global nextRateLimitReset
	if time.time() > nextRateLimitReset:
		rateLimit.clear()
		nextRateLimitReset = time.time() + 2 * 60
	rateLimit.setdefault(addr, 0)
	rateLimit[addr] += 1
	if addr in blockedIPs:
		raise AddressBlocked
	if rateLimit[addr] > config['rate_limit']:
		raise RateLimitExceeded
	
