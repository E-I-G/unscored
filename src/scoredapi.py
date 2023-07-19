import random
import time

import eventlet
import requests
import base62

from utils import helpers
from utils import logger

import state as st
import database
import archive


DEFAULT_MODERATION_INFO = {
	'approved_by': '',
	'approved_at': 0,
	'removed_by': '',
	'removed_at': 0
}

DEFAULT_ARCHIVE_INFO = {
	'is_archived': False,
	'archived_at': 0,
	'legal_removed': False,
	'legal_approved': False,
	'reportable': False,
	'recovered_from_log': False
}

DEFAULT_BAN_INFO = {
	'is_banned': False,
	'is_suspended': False,
	'is_nuked': False,
	'banned_by': None,
	'ban_reason': None,
}

ITEMS_PER_PAGE = 25


def api_cooldown():
	ms = random.randrange(st.config['request_cooldown_min_ms'], st.config['request_cooldown_max_ms'])
	logger.logtrace('API cooldown: %d ms' % ms)
	eventlet.sleep(ms / 1000)


def _api_request(method: str, endpoint: str, params: dict, attempt: int):
	logger.logdebug('[Scored API] request: %s %s (attempt %d/3)' % (method, endpoint, attempt))
	logger.logtrace('Params: %s' % params)
	url = 'https://scored.co/' + endpoint.lstrip('/')
	headers = {
		'User-Agent': st.config['scored_api_useragent']
	}
	if st.config['scored_api_key'] and st.config['scored_api_secret']:
		headers['X-Api-Key'] = st.config['scored_api_key']
		headers['X-Api-Secret'] = st.config['scored_api_secret']
	if method.lower() == 'get':
		resp = requests.get(url, headers=headers, params=params, timeout=3)
	elif method.lower() == 'post':
		resp = requests.post(url, headers=headers, data=params, timeout=3)
	else:
		raise ValueError('Invalid method')
	return resp


def apireq(method: str, endpoint: str, params: dict):
	attempt = 1
	while attempt <= 3:
		try:
			resp = _api_request(method, endpoint, params, attempt)
		except Exception as e:
			logger.logerr('[Scored API] exception - %s: %s' % (e.__class__.__name__, e))
		else:
			try:
				jsonResp = resp.json()
			except requests.JSONDecodeError:
				logger.logerr('[Scored API] returned code %d' % resp.status_code)
				return {
					'status': False,
					'error': 'Failed - status %d' % resp.status_code 
				}
			else:
				if not jsonResp['status']:
					logger.logerr('[Scored API] error response - %s' % jsonResp['error'])
				return jsonResp
		finally:
			attempt += 1
			api_cooldown()
	else:
		logger.logerr('[Scored API] all attempts failed')
		return {
			'status': False,
			'error': 'Failed'
		}
	


def scored_uuid_to_id(uuid):
	return int(base62.decodebytes(uuid).decode('ascii'))

def scored_id_to_uuid(id):
	return base62.encodebytes(str(id).encode('ascii'))