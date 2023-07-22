import time

import markdownify
from bs4 import BeautifulSoup

from utils import logger

import database
import state as st
import archive
import scoredapi


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
		if post['author'] and community in st.ingest and st.ingest[community]['domain']:
			logger.logdebug('Attempting to recover post %d by scraping profile' % post_id)
			url = 'https://' + st.ingest[community]['domain'] + '/u/' + post['author']
			main = scoredapi.scrape_page(url, {'type': 'post'}, 'main')
			scraped = error = None
			if main:
				scraped = main.select_one('.post[data-id="' + str(post_id) + '"]')
				error = main.select_one('.error')
			if scraped is not None:
				logger.logdebug('Successfully scraped post')
				recovered_from_scrape = True
				post['title'] = scraped.select_one('.title').text.strip()
				inner = scraped.select_one('.content .inner')
				if post['type'] == 'text' and inner is not None:
					post['raw_content'] = markdownify.markdownify(str(inner))
				elif post['type'] == 'link' and inner is not None:
					if inner.a is not None:
						post['link'] = inner.a['href']
					elif inner.img is not None:
						post['link'] = inner.img['data-src']
				elif post['type'] == 'link' and scraped.select_one('.expand-link') is not None:
					post['link'] = scraped.select_one('.expand-link')['href']
			elif error is not None:
				errText = error.div.text.strip()
				if errText == 'User has been suspended.':
					archive.mark_user_suspended(db, post['author'])
			else:
				logger.logdebug('Did not manage to scrape post')
		try:
			if not post['is_deleted']:
				archive.add_post(db, community, post)
		except Exception:
			logger.log_traceback()
		else:
			if recovered_from_scrape:
				db.exec("UPDATE posts SET recovered_from_scrape = TRUE WHERE id = ?", post_id)



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
		missingIds = [id for id in range(finalId + 1, firstId) if id not in idsFound]
		logger.log('%d ids missing' % len(missingIds))
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
	if commentCount:
		logger.log('Ingested %d new comments from %s up to id %d' % (commentCount, community, firstId))
		st.ingest[community]['last_comment_id'] = firstId
		st.save_state()
	else:
		logger.log('No new comments from %s' % community)


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
	logger.logdebug('Mod log state for %s: logs = %s, ban-logs = %s' % (
		community,
		st.ingest[community]['modlogs'],
		st.ingest[community]['banlogs'])
	)


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

	while reqCount < st.config['ingest_limit']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['ingest_limit']))
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
		st.save_state()
	else:
		logger.log('No new mod log records from %s' % community)



enqueued = {}

def thread_ingest():
	logger.log('Initializing communities')
	enqueued[time.time()] = 'global'
	for i, community in enumerate(st.communities):
		enqueued[time.time() + i + 1] = community['name']
		check_community_modlog_state(community['name'])

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
			except Exception:
				logger.log_traceback()
		del enqueued[next]
		scheduled = time.time() + st.ingest[community]['interval']
		enqueued[scheduled] = community
			
			


