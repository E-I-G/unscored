import random
import time
import json

import eventlet
import requests
import base62
from bs4 import BeautifulSoup

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
	'recovery_method': None,
	'just_added': False
}

DEFAULT_BAN_INFO = {
	'is_banned': False,
	'is_suspended': False,
	'is_nuked': False,
	'banned_by': None,
	'ban_reason': None,
}

ITEMS_PER_PAGE = 25


def get_uagent():
	uagent = st.config['scored_api_useragent']
	if st.config['scored_api_useragent_appendver']:
		uagent += ' ' + st.VERSION



respCache = {}

def get_resp_from_cache(endpoint: str, params: dict):
	curTime = time.time()
	url = endpoint + '?' + '&'.join(str(k) + '=' + str(v) for k, v in params.items())
	for key in list(respCache.keys()):
		if curTime > respCache[key]['expires']:
			try:
				del respCache[key]
			except KeyError:
				pass
	if url in respCache:
		logger.logdebug('[Scored API] Got resp from cache (expires in %ss)' % int(respCache[url]['expires'] - curTime))
		return respCache[url]['resp']
	else:
		return None

def add_resp_to_cache(endpoint: str, params: dict, resp: dict, cache_ttl: int):
	url = endpoint + '?' + '&'.join(str(k) + '=' + str(v) for k, v in params.items())
	logger.logtrace('Added to cache (ttl=%d): %s' % (cache_ttl, url))
	respCache[url] = {
		'expires': time.time() + cache_ttl,
		'resp': resp
	}



def api_cooldown():
	ms = random.randrange(st.config['request_cooldown_min_ms'], st.config['request_cooldown_max_ms'])
	logger.logtrace('API cooldown: %d ms' % ms)
	eventlet.sleep(ms / 1000)


def _api_request(method: str, endpoint: str, params: dict, attempt: int):
	logger.logdebug('[Scored API] attempt %d/3' % attempt)
	url = 'https://scored.co/' + endpoint.lstrip('/')
	headers = {
		'User-Agent': get_uagent()
	}
	if st.config['scored_api_key'] and st.config['scored_api_secret']:
		headers['X-Api-Key'] = st.config['scored_api_key']
		headers['X-Api-Secret'] = st.config['scored_api_secret']
	if method.lower() == 'get':
		resp = requests.get(url, headers=headers, params=params, timeout=7)
	elif method.lower() == 'post':
		resp = requests.post(url, headers=headers, data=params, timeout=7)
	else:
		raise ValueError('Invalid method')
	return resp


def apireq(method: str, endpoint: str, params: dict, cache_ttl=0):
	logger.logdebug('[Scored API] request: %s %s (cache_ttl=%d)' % (method, endpoint, cache_ttl))
	logger.logtrace('Params: %s' % params)
	if cache_ttl and st.config['caching']:
		resp = get_resp_from_cache(endpoint, params)
		if resp is not None:
			return resp
	attempt = 1
	while attempt <= 3:
		t_ms_start = time.time_ns() // 10**6
		try:
			resp = _api_request(method, endpoint, params, attempt)
		except Exception as e:
			logger.logerr('[Scored API] exception - %s: %s' % (e.__class__.__name__, e))
		else:
			logger.logtrace('[Scored API] returned data')
			try:
				jsonResp = resp.json()
			except Exception:
				logger.logerr('[Scored API] returned code %d' % resp.status_code)
				return {
					'status': False,
					'error': 'Failed - status %d' % resp.status_code 
				}
			else:
				if not jsonResp['status']:
					logger.logerr('[Scored API] error response - %s' % jsonResp['error'])
				if cache_ttl and st.config['caching']:
					add_resp_to_cache(endpoint, params, jsonResp, cache_ttl)
				return jsonResp
		finally:
			attempt += 1
			t_ms_diff = time.time_ns() // 10**6 - t_ms_start
			logger.logtrace('[Scored API] request finished in %d ms' % t_ms_diff)
			api_cooldown()
	else:
		logger.logerr('[Scored API] all attempts failed')
		return {
			'status': False,
			'error': 'Failed'
		}
	

def scrape_page(url: str, params={}, selector='html'):
	logger.logdebug('[Scraping] request: GET %s -> %s' % (url, selector))
	t_ms_start = time.time_ns() // 10**6
	try:
		resp = requests.get(url, params=params, headers={
			'User-Agent': get_uagent()
		}, timeout=10)
	except Exception as e:
		logger.logerr('[Scraping] exception - %s: %s' % (e.__class__.__name__, e))
		return None
	finally:
		t_ms_diff = time.time_ns() // 10**6 - t_ms_start
		logger.logtrace('[Scraping] request finished in %d ms' % t_ms_diff)
	soup = BeautifulSoup(resp.content, 'html.parser')
	api_cooldown()
	return soup.select_one(selector)


def scored_uuid_to_id(uuid):
	return int(base62.decodebytes(uuid).decode('ascii'))

def scored_id_to_uuid(id):
	return base62.encodebytes(str(id).encode('ascii'))