import os
import json
import sys
import time

from utils import logger

VERSION = '1.5'

DATA_DIR = 'data'

CONFIGURATION_FILE = 'configuration/config.json'
DEFAULT_CONFIG_FILE = 'configuration/default_config.json'
COMMUNITIES_FILE = 'configuration/monitored_communities.json'
SESSION_SECRET_FILE = 'configuration/session_secret'
IPBLOCKS_FILE = 'configuration/blocked_addrs.txt'

INGEST_STATE_FILE = 'data/ingest_state.json'


config = {}

def load_config():
	with open(DEFAULT_CONFIG_FILE, 'r') as f:
		default = json.load(f)
	if not os.path.isfile(CONFIGURATION_FILE):
		cfg = {}
	else:
		with open(CONFIGURATION_FILE, 'r') as f:
			cfg = json.load(f)
	updated = False
	for key in default:
		if key not in cfg:
			updated = True
			cfg[key] = default[key]
	if updated:
		with open(CONFIGURATION_FILE, 'w') as f:
			json.dump(cfg, f, indent='\t')
	config.clear()
	config.update(cfg)


ingest = {}


def add_community_to_ingest(name, interval=None, domain=None, visibility=None, modlogs=None, banlogs=None, has_icon=None, app_safe=None):
	if name in ingest:
		if interval is not None:
			ingest[name]['interval'] = interval
		if visibility is not None:
			ingest[name]['visibility'] = visibility
		if domain and not ingest[name]['domain']:
			ingest[name]['domain'] = domain
		if modlogs is not None:
			ingest[name]['modlogs'] = modlogs
		if banlogs is not None:
			ingest[name]['banlogs'] = banlogs
		if has_icon is not None:
			ingest[name]['has_icon'] = has_icon
		if app_safe is not None:
			ingest[name]['app_safe'] = app_safe
	else:
		ingest[name] = {
			'domain': domain,
			'visibility': visibility,
			'interval': interval if interval is not None else 60,
			'last_post_id': 0,
			'last_comment_id': 0,
			'last_modlog_timestamp': 0,
			'last_ingested': 0,
			'modlogs': modlogs,
			'banlogs': banlogs,
			'has_icon': has_icon,
			'app_safe': app_safe
		}



def get_ingest_frequency_stat() -> float:
	"""Returns number of ingests per day"""
	ingests = 0
	for c in ingest.values():
		if c['interval'] > 0:
			ingests += 24*60*60 / c['interval']
	return ingests


def load_state():
	os.makedirs('data', exist_ok=True)
	if os.path.isfile(INGEST_STATE_FILE):
		with open(INGEST_STATE_FILE, 'r') as f:
			ingest.update(json.load(f))
	with open(COMMUNITIES_FILE, 'r') as f:
		defaultCommunities = json.load(f)
	for community in defaultCommunities:
		add_community_to_ingest(
			community['name'],
			domain = community['standalone_domain']
		)
	if 'global' not in ingest:
		ingest['global'] = {
			'last_post_id': max([community['last_post_id'] for community in ingest.values()]),
			'interval': config['global_interval'],
			'last_ingested': 0,
			'startup': True,
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
	
