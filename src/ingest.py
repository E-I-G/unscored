import time
import math
import random

import markdownify
from bs4 import BeautifulSoup

from utils import logger

import database
import state as st
import archive
import scoredapi



MAX_INGEST_INTERVAL = 5*24*60*60

def calculate_new_interval(comments) -> int:
	t = int(time.time() - comments[-1]['created'] / 1000)
	interval = int(25 * math.sqrt(t))
	if len(comments) < 5:
		interval *= 10
	elif len(comments) < 12 or time.time() - comments[0]['created'] / 1000 > 120*24*60*60:
		interval *= 5
	elif len(comments) < 25 or time.time() - comments[0]['created'] / 1000 > 20*24*60*60:
		interval *= 2
	interval = min(random.randint(int(0.8 * interval), int(1.2 * interval)), MAX_INGEST_INTERVAL)
	if interval == MAX_INGEST_INTERVAL:
		interval = random.randint(int(0.9 * MAX_INGEST_INTERVAL), MAX_INGEST_INTERVAL)
	return interval



###########################
### Community discovery ###

def add_discovered_community(community: dict):
	logger.log('Adding community to ingest: %s (visibility=%s)' % (community['name'], community['visibility']))
	st.add_community_to_ingest(
		community['name'],
		visibility = community['visibility'],
		modlogs = community['is_public_logs'],
		banlogs = community['is_public_ban_logs'],
		has_icon = community['icon'],
		app_safe = community['is_app_safe']
	)
	if community['description']:
		st.ingest[community['name']]['description'] = community['description']


def discover_community(name):
	resp = scoredapi.apireq('GET', '/api/v2/community/community.json', {
		'communities': name
	})
	if resp['status'] and resp['communities']:
		add_discovered_community(resp['communities'][0])
	st.save_state()


def discover_communities(db: database.DBRequest):
	logger.log('Discovering communities on Scored')
	page = 1
	while True:
		resp = scoredapi.apireq('GET', '/api/v2/community/communities.json', {
			'sort': 'activity',
			'topic': 'all',
			'page': page,
			'showPolitics': 'true'
		})
		page += 1
		if resp['status'] and resp['communities']:
			for community in resp['communities']:
				add_discovered_community(community)
		else:	
			break
	st.save_state()
	logger.log('Looking for hidden communites')
	for row in db.query("SELECT name FROM boards"):
		if row.name not in st.ingest:
			discover_community(row.name)
	

def discover_communities_from_mod(moderator):
	logger.log('Discovering communities moderated by %s' % moderator)
	resp = scoredapi.apireq('GET', '/api/v2/user/about.json', {
		'user': moderator
	})
	if resp['status']:
		communities = resp['users'][0]['moderates']
		for name in communities:
			discover_community(name)



###################
### Post ingest ###

def scrape_from_page(post: dict):
	successful = False
	logger.logdebug('Attempting to recover post %d by scraping thread webpage' % post['id'])
	url = 'https://' + st.ingest[post['community']]['domain'] + '/p/' + post['uuid']
	main = scoredapi.scrape_page(url, {}, 'main')
	scraped = error = None
	if main:
		scraped = main.select_one('.post')
		error = main.select_one('.error')
	if scraped is not None:
		logger.logdebug('Successfully scraped post')
		successful = True
		post['title'] = scraped.select_one('.title').text.strip()
		inner = scraped.select_one('.content .inner')
		if post['type'] == 'text' and inner is not None:
			post['raw_content'] = markdownify.markdownify(str(inner))
		elif post['type'] == 'link':
			post['link'] = scraped.select_one('.title')['href']
	elif error is not None:
		errText = error.div.text.strip()
		logger.logerr('Error on scraped domain: %s' % errText)
	else:
		logger.logdebug('Did not manage to scrape post')
	return successful, post


def scrape_from_profile(db: database.DBRequest, post: dict):
	successful = False
	logger.logdebug('Attempting to recover post %d by scraping profile' % post['id'])
	url = 'https://' + st.ingest[post['community']]['domain'] + '/u/' + post['author']
	main = scoredapi.scrape_page(url, {'type': 'post'}, 'main')
	scraped = error = None
	if main:
		scraped = main.select_one('.post[data-id="' + str(post['id']) + '"]')
		error = main.select_one('.error')
	if scraped is not None:
		logger.logdebug('Successfully scraped post')
		successful = True
		post['title'] = scraped.select_one('.title').text.strip()
		inner = scraped.select_one('.content .inner')
		if post['type'] == 'text' and inner is not None:
			post['raw_content'] = markdownify.markdownify(str(inner))
		elif post['type'] == 'link' and inner is not None:
			if inner.a is not None:
				post['link'] = inner.a['href']
			elif inner.img is not None:
				post['link'] = inner.img['data-src']
			elif inner.div is not None and inner.div['class'] == 'video-container':
				post['link'] = inner.div['data-src']
		elif post['type'] == 'link' and scraped.select_one('.expand-link') is not None:
			post['link'] = scraped.select_one('.expand-link')['href']
		elif post['type'] == 'link' and scraped.select_one('.thumb a') is not None:
			post['link'] = scraped.select_one('.thumb a')['href']
	elif error is not None:
		errText = error.div.text.strip()
		if errText == 'User has been suspended.':
			logger.logdebug('Author suspended: %s' % post['author'])
			archive.mark_user_suspended(db, post['author'])
			successful, post = scrape_from_page(post)
		else:
			logger.logerr('Error on scraped domain: %s' % errText)
	else:
		logger.logdebug('Did not manage to scrape post from profile')
	return successful, post
	


def ingest_missing_post(db: database.DBRequest, post_id: int):
	logger.logdebug('Ingesting missing post: %d' % post_id)
	resp = scoredapi.apireq('GET', '/api/v2/post/post.json', {
		'id': post_id,
		'comments': 'false'
	})
	if resp['status']:
		post = resp['posts'][0]
		community = post['community']
		recovered_from_scrape = False
		if post['is_removed'] and not post['is_deleted'] and not post['title']:
			if community in st.ingest and st.ingest[community]['domain']:
				recovered_from_scrape, post = scrape_from_profile(db, post)
		try:
			if not post['is_deleted']:
				archive.add_post(db, community, post)
		except Exception:
			logger.log_traceback()
		else:
			if recovered_from_scrape:
				db.exec("UPDATE posts SET recovered_from_scrape = TRUE WHERE id = ?", post_id)


			
def ingest_post_and_comments(db: database.DBRequest, post_id: int):
	logger.log('Ingesting post: %s' % post_id)
	resp = scoredapi.apireq('GET', '/api/v2/post/post.json', {
		'id': post_id,
		'comments': 'true'
	})
	if resp['status']:
		post = resp['posts'][0]
		community = post['community']
		recovered_from_scrape = False
		if post['is_removed'] and not post['is_deleted'] and not post['title']:
			if community in st.ingest and st.ingest[community]['domain']:
				recovered_from_scrape, post = scrape_from_page(post)
		try:
			if not post['is_deleted']:
				archive.add_post(db, community, post)
		except Exception:
			logger.log_traceback()
		else:
			if recovered_from_scrape:
				db.exec("UPDATE posts SET recovered_from_scrape = TRUE WHERE id = ?", post_id)
		comments = resp['comments']
		for comment in comments:
			try:
				archive.add_comment(db, community, comment)
			except Exception:
				logger.log_traceback()


def ingest_complete_modlog(db: database.DBRequest, community: str):
	ban_logs = st.ingest[community]['banlogs'] and not st.ingest[community]['modlogs']
	logger.log('Ingesting every mod log record from %s' % community)
	if ban_logs:
		endpoint = '/api/v2/community/ban-logs.json'
	else:
		endpoint = '/api/v2/community/logs.json'
	logger.logdebug('Mod log endpoint for %s: %s' % (community, endpoint))
	records = []

	page = 1
	previousTimestamp = 0
	while True:
		resp = scoredapi.apireq('GET', endpoint, {
			'community': community,
			'page': page
		})
		page += 1
		if resp['status'] and len(resp['logs']) > 0:
			for record in resp['logs']:
				if record['created'] == previousTimestamp:
					continue
				if record['type'] in archive.MONITORED_MODLOG_ACTIONS:
					previousTimestamp = record['created']
					records.append(record)
		else:
			break
	
	for record in reversed(records):
		archive.add_modlog_record(db, community, record)



def ingest_global_posts(db: database.DBRequest):
	firstId = None
	finalId = st.ingest['global']['last_post_id']
	fromId = None
	previousId = None
	reqCount = 0
	postCount = 0
	end = False
	idsFound = set()
	logger.log('Fetching new posts from global feed up to id %d' % finalId)

	while reqCount < st.config['ingest_limit']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['ingest_limit']))
		resp = scoredapi.apireq('GET', '/api/v2/post/newv2.json', {
			'community': 'win',
			'feedId': 2,
			'from': fromId
		})
		if resp['status'] and len(resp['posts']) > 0:
			for post in resp['posts']:
				if post['id'] <= finalId:
					end = True
					break
				if post['id'] == previousId: #Skip duplicates
					continue
				if firstId is None:
					firstId = post['id']
				if post['is_deleted']:
					continue
				idsFound.add(post['id'])
				previousId = post['id']
				postCount += 1
				try:
					archive.add_post(db, post['community'], post)
				except Exception:
					logger.log_traceback()
			fromId = resp['posts'][-1]['uuid']
			if end or not resp['has_more_entries']:
				break
		else:
			break
	
	if postCount:
		logger.log('Ingested %d new posts from global feed up to id %d' % (postCount, firstId))
		st.ingest['global']['last_post_id'] = firstId
		st.save_state()
		missingIds = [id for id in range(min(idsFound) if finalId == 0 else finalId + 1, firstId) if id not in idsFound]
		logger.log('%d ids missing' % len(missingIds))
		if len(missingIds) > st.config['max_missing_ids']:
			logger.logwrn('Too many missing ids!')
		else:
			for id in missingIds:
				ingest_missing_post(db, id)
	else:
		logger.log('No new posts from global feed')

	

def ingest_community_posts(db: database.DBRequest, community: str):
	firstId = None
	finalId = st.ingest[community]['last_post_id']
	fromId = None
	previousId = None
	reqCount = 0
	postCount = 0
	end = False
	logger.log('Fetching new posts from %s up to id %d' % (community, finalId))

	while reqCount < st.config['ingest_limit']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['ingest_limit']))
		resp = scoredapi.apireq('GET', '/api/v2/post/newv2.json', {
			'community': community,
			'from': fromId
		})
		if resp['status'] and len(resp['posts']) > 0:
			for post in resp['posts']:
				if post['id'] <= finalId:
					end = True
					break
				if post['id'] == previousId: #Skip duplicates
					continue
				if firstId is None:
					firstId = post['id']
				if post['is_deleted']:
					continue
				previousId = post['id']
				postCount += 1
				try:
					archive.add_post(db, community, post)
				except Exception:
					logger.log_traceback()
			fromId = resp['posts'][-1]['uuid']
			if end or not resp['has_more_entries']:
				break
		else:
			break
	if postCount:
		logger.log('Ingested %d new posts from %s up to id %d' % (postCount, community, firstId))
		if community in st.ingest:
			st.ingest[community]['last_post_id'] = firstId
		st.save_state()
	else:
		logger.log('No new posts from %s' % community)


def ingest_community_comments(db: database.DBRequest, community: str):
	firstId = None
	finalId = st.ingest[community]['last_comment_id']
	page = 1
	previousId = None
	reqCount = 0
	commentCount = 0
	end = False
	newInterval = 0
	logger.log('Fetching new comments from %s up to id %d' % (community, finalId))

	while reqCount < st.config['ingest_limit']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['ingest_limit']))
		resp = scoredapi.apireq('GET', '/api/v2/comment/community.json', {
			'community': community,
			'page': page
		})
		page += 1
		if resp['status'] and len(resp['comments']) > 0:
			if not newInterval:
				newInterval = calculate_new_interval(resp['comments'])
			for comment in resp['comments']:
				if comment['id'] <= finalId:
					end = True
					break
				if comment['id'] == previousId: #Skip duplicates
					continue
				if firstId is None:
					firstId = comment['id']
				previousId = comment['id']
				commentCount += 1
				try:
					archive.add_comment(db, community, comment)
				except Exception:
					logger.log_traceback()
			if end or not resp['has_more_entries']:
				break
		else:
			break
	if not newInterval:
		newInterval = random.randint(MAX_INGEST_INTERVAL + 1, int(1.5 * MAX_INGEST_INTERVAL))
	if commentCount:
		logger.log('Ingested %d new comments from %s up to id %d (new interval = %d)' % (commentCount, community, firstId, newInterval))
		st.ingest[community]['last_comment_id'] = firstId
		st.ingest[community]['interval'] = newInterval
	else:
		logger.log('No new comments from %s (new interval = %d)' % (community, newInterval))
		st.ingest[community]['interval'] = newInterval


def check_community_modlog_state(community: str):
	if st.ingest[community]['modlogs'] is None:
		resp = scoredapi.apireq('GET', '/api/v2/community/logs.json', {
			'community': community,
			'page': 1
		})
		logsEnabled = resp['status']
		st.ingest[community]['modlogs'] = logsEnabled
		st.save_state()
	if st.ingest[community]['banlogs'] is None:
		resp = scoredapi.apireq('GET', '/api/v2/community/ban-logs.json', {
			'community': community,
			'page': 1
		})
		banlogsEnabled = resp['status']
		st.ingest[community]['banlogs'] = banlogsEnabled
		st.save_state()


def ingest_community_modlogs(db: database.DBRequest, community: str, ban_logs=False):
	firstTimestamp = None
	finalTimestamp = st.ingest[community]['last_modlog_timestamp']
	page = 1
	previousTimestamp = None
	reqCount = 0
	recordCount = 0
	end = False
	logger.log('Fetching new mod log records from %s up to timestamp %d' % (community, finalTimestamp))
	if ban_logs:
		endpoint = '/api/v2/community/ban-logs.json'
	else:
		endpoint = '/api/v2/community/logs.json'
	logger.logdebug('Mod log endpoint for %s: %s' % (community, endpoint))
	records = []

	while reqCount < st.config['modlog_ingest_limit']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['modlog_ingest_limit']))
		resp = scoredapi.apireq('GET', endpoint, {
			'community': community,
			'page': page
		})
		page += 1
		if resp['status'] and len(resp['logs']) > 0:
			for record in resp['logs']:
				if record['created'] == finalTimestamp:
					end = True
					break
				if record['created'] == previousTimestamp: #Skip duplicates
					continue
				if firstTimestamp is None:
					firstTimestamp = record['created']
				if record['type'] in archive.MONITORED_MODLOG_ACTIONS:
					previousTimestamp = record['created']
					recordCount += 1
					records.append(record)
			if end:
				break
		else:
			break

	for record in reversed(records):
		try:
			archive.add_modlog_record(db, community, record)
		except Exception:
			logger.log_traceback()

	if recordCount:
		logger.log('Ingested %d new mod log records from %s up to timestamp %d' % (recordCount, community, firstTimestamp))
		st.ingest[community]['last_modlog_timestamp'] = firstTimestamp
	else:
		logger.log('No new mod log records from %s' % community)



def thread_backingest():
	post_id = st.ingest['global'].get('last_backingest_id', 1)
	logger.log('Starting backingest from id %d' % post_id)
	with database.DBRequest() as db:
		while post_id < st.ingest['global']['last_post_id']:
			ingest_post_and_comments(db, post_id)
			post_id += 1
			st.ingest['global']['last_backingest_id'] = post_id
			time.sleep(st.config['backingest_cooldown'])
		else:
			logger.log('Backingest reached max id')



enqueued = {}

def thread_ingest():
	logger.log('Initializing communities')

	i = 0
	for name, community in st.ingest.items():
		enqueued[community.get('last_ingested', 0) + community['interval'] + i] = name
		check_community_modlog_state(name)
		i += 1

	with open('data/enqueued.json', 'w') as f:
		import json; json.dump(enqueued, f, indent='\t')

	logger.log('Starting ingest schedule loop')
	while True:
		next = min(enqueued.keys())
		community = enqueued[next]
		timeDiff = max(0, int(next - time.time()))
		logger.logtrace('Next ingest in %ds: %s' % (timeDiff, community))
		if timeDiff > 0:
			time.sleep(timeDiff)
		logger.logdebug('Ingesting: %s' % community)
		with database.DBRequest() as db:
			try:
				if community == 'global':
					ingest_global_posts(db)
				else:
					ingest_community_comments(db, community)
					if st.ingest[community]['modlogs']:
						ingest_community_modlogs(db, community, ban_logs=False)
					elif st.ingest[community]['banlogs']:
						ingest_community_modlogs(db, community, ban_logs=True)
					st.ingest[community]['last_ingested'] = int(time.time())
					st.save_state()
			except Exception:
				logger.log_traceback()
		del enqueued[next]
		scheduled = time.time() + st.ingest[community]['interval']
		enqueued[scheduled] = community