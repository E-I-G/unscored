import re
import urllib.parse


class RequestFailed(Exception): pass
class InvalidURL(RequestFailed): pass


from utils import helpers, logger

import state as st
import database
import scoredapi
import archive



GLOBAL_DOMAINS = ['scored.co', 'communities.win']

BOT_REMOVAL_THRESHOLD = 60*10

BOT_NAMES = ['Scored', 'AutoModerator', 'Filter', 'CommunityFilter', 'GlobalFilter']


###################
### URL parsing ###

def get_valid_domains():
	domains = GLOBAL_DOMAINS.copy()
	for community in st.communities:
		if community['standalone_domain']:
			domains.append(community['standalone_domain'])
	return domains

def get_community_from_domain(domain: str):
	for community in st.communities:
		if domain == community['standalone_domain']:
			return community['name']

def get_content_urls(community: str, post_id, comment_id=None):
	urls = []
	postPath = '/p/' + scoredapi.scored_id_to_uuid(post_id)
	if comment_id:
		postPath += '/x/c/' + scoredapi.scored_id_to_uuid(comment_id)
	for domain in GLOBAL_DOMAINS:
		urls.append('https://' + domain + '/c/' + community + postPath)
	if community in st.ingest and st.ingest[community]['domain']:
		domain = st.ingest[community]['domain']
		urls.append('https://' + domain + postPath)
	return urls

def parse_url(raw_url: str):
	validDomains = get_valid_domains()
	url = urllib.parse.urlparse(raw_url)
	domain = url.netloc
	path = url.path.rstrip('/')
	params = {
		key: ''.join(vals)
		for key, vals in urllib.parse.parse_qs(url.query).items()
	}
	if re.match('^[A-z0-9_]+$', raw_url.strip()):
		return {
			'type': 'profile',
			'user': raw_url.strip(),
			'content': 'removed',
			'page': 1,
			'normalized_path': '/u/' + raw_url.strip() + '?type=removed'
		}
	elif domain in validDomains or not domain:
		if domain and domain not in GLOBAL_DOMAINS:
			community = get_community_from_domain(domain)
		if url.path.startswith('/u/'):
			username = url.path[3:].rstrip('/')
			contentType = params.get('type', 'comment')
			page = helpers.safeint(params.get('page'), 1)
			if '/' in username:
				raise InvalidURL('Invalid user profile URL')
			return {
				'type': 'profile',
				'user': username,
				'content': contentType,
				'page': page,
				'normalized_path': '/u/' + username + '?type=' + contentType
			}
		else:
			if domain and domain not in GLOBAL_DOMAINS:
				community = get_community_from_domain(domain)
			elif path.startswith('/p/'):
				community = None
			else:
				result = re.findall('^/c/([^/]+)/?', path)
				if not result:
					logger.logtrace('Invalid URL [1]')
					raise InvalidURL('Invalid URL')
				community = result[0]
				sp = path.split('/', 3)
				path = '/' if len(sp) == 3 else '/' + sp[3]
			if not path:
				path = '/'
			if path in ('/', '/rising', '/top', '/active', '/new'):
				#hot, rising, top, active are not yet supported. Redirect to /new
				normalized_path = '/c/%s/new' % community
				if 'from' in params:
					normalized_path += '?from=' + params['from']
				return {
					'type': 'feed',
					'community': community,
					'sort': 'new',
					'from_uuid': params.get('from'),
					'normalized_path': normalized_path
				}
			elif path.startswith('/p/'):
				result = re.findall('^/p/([^/]+)(?:/[^/]+/c/([^/]+)?)?', path)
				if not result:
					logger.logtrace('Invalid URL [2]')
					raise InvalidURL('Invalid URL')
				post_uuid, comment_uuid = result[0]
				sort = params.get('sort', 'top')
				if community:
					normalized_path = '/c/' + community + '/p/' + post_uuid
				else:
					normalized_path = '/p/' + post_uuid
				if comment_uuid:
					normalized_path += '/x/c/' + comment_uuid
				if sort != 'top':
					normalized_path += '?sort=' + sort
				return {
					'type': 'thread',
					'community': community,
					'post_uuid': post_uuid,
					'post_id': scoredapi.scored_uuid_to_id(post_uuid),
					'comment_uuid': comment_uuid if comment_uuid else None,
					'comment_id': scoredapi.scored_uuid_to_id(comment_uuid) if comment_uuid else None,
					'sort': sort,
					'normalized_path': normalized_path
				}
			else:
				logger.logtrace('Invalid URL [3]')
				raise InvalidURL('Invalid URL')
	else:
		logger.logtrace('Invalid URL [4]')
		raise InvalidURL('Unknown domain name')
	


###############
### Threads ###

def merge_post_with_archived(db: database.DBRequest, remote_post: dict, archived_post):
	d_archive = scoredapi.DEFAULT_ARCHIVE_INFO.copy()
	d_moderation = scoredapi.DEFAULT_MODERATION_INFO.copy()
	d_ban = scoredapi.DEFAULT_BAN_INFO.copy()
	post = {
		'id': remote_post['id'],
		'uuid': remote_post['uuid'],
		'author': remote_post['author'],
		'community': remote_post['community'],
		'created': remote_post.get('created', 0),
		'is_admin': remote_post.get('is_admin', False),
		'is_moderator': remote_post.get('is_moderator', False),
		'is_removed': remote_post.get('is_removed', False),
		'is_filtered': 'filter' in remote_post.get('removal_source', '').lower(),
		'is_deleted': remote_post.get('is_deleted', False),
		'is_edited': remote_post.get('is_edited', False),
		'is_locked': remote_post.get('is_locked', False),
		'is_nsfw': remote_post.get('is_nsfw', False),
		'is_image': remote_post.get('is_image', False),
		'removal_source': remote_post.get('removal_source', ''),
		'type': remote_post['type'],
		'link': remote_post['link'],
		'domain': urllib.parse.urlparse(remote_post['link']).netloc,
		'preview': remote_post.get('preview', ''),
		'title': remote_post.get('title', '').strip(),
		'raw_content': remote_post['raw_content'].replace('\r\n', '\n'),
		'comments': remote_post.get('comments', 0),
		'score': remote_post.get('score', 0),
		'score_up': remote_post.get('score_up', 0),
		'score_down': remote_post.get('score_down', 0),
		'normalized_path': '/c/' + remote_post['community'] + '/p/' + remote_post['uuid'],
		'urls': get_content_urls(remote_post['community'], remote_post['id']),
		'archive': d_archive,
		'moderation': d_moderation,
		'ban': d_ban
	}
	
	if archived_post is not None:
		if (post['is_removed'] or post['is_deleted']) and not archived_post.legal_removed:
			post['author'] = archived_post.author
			post['title'] = archived_post.title.strip()
			post['raw_content'] = archived_post.raw_content.replace('\r\n', '\n')
			post['type'] = archived_post.type
			post['link'] = archived_post.link
			post['domain'] = urllib.parse.urlparse(archived_post.link).netloc
			post['preview'] = archived_post.preview
		post['ban'] = {
			'is_banned': bool(archived_post.is_banned),
			'is_suspended': bool(archived_post.is_suspended),
			'is_nuked': bool(archived_post.is_nuked),
			'banned_by': archived_post.banned_by,
			'ban_reason': archived_post.ban_reason,
		}
		post['moderation'] = {
			'removed_at': archived_post.removed_at_ms if archived_post.removed_at_ms else 0,
			'removed_by': archived_post.removed_by if archived_post.removed_by else '',
			'approved_at': archived_post.approved_at_ms if archived_post.approved_at_ms else 0,
			'approved_by': archived_post.approved_by if archived_post.approved_by else ''
		}
		post['archive'] = {
			'is_archived': True,
			'archived_at': archived_post.archived_at_ms,
			'legal_removed': bool(archived_post.legal_removed),
			'legal_approved': bool(archived_post.legal_approved),
			'recovered_from_log': bool(archived_post.recovered_from_log),
			'recovered_from_scrape': bool(archived_post.recovered_from_scrape),
			'reportable': (
				st.config['reporting_enabled'] and
				post['title'] and
				not archived_post.legal_removed and
				not archived_post.legal_approved and
				(post['is_removed'] or post['is_deleted'])
			)
		}
	if post['is_deleted'] and not post['is_removed'] and not st.config['show_deleted']:
		if st.config['purge_deleted'] and archived_post['raw_content'] != '':
			logger.logtrace('Purging deleted post %d' % post['id'])
			db.exec("UPDATE posts SET raw_content = '', link = '', preview = '' WHERE id = ?", post['id'])
		post['raw_content'] = post['link'] = post['domain'] = post['preview'] = ''
	return post

def merge_comment_with_archived(db: database.DBRequest, remote_comment: dict, archived_comment):
	d_archive = scoredapi.DEFAULT_ARCHIVE_INFO.copy()
	d_moderation = scoredapi.DEFAULT_MODERATION_INFO.copy()
	d_ban = scoredapi.DEFAULT_BAN_INFO.copy()
	comment = {
		'id': remote_comment['id'],
		'uuid': remote_comment['uuid'],
		'author': remote_comment['author'],
		'community': remote_comment['community'],
		'created': remote_comment.get('created', 0),
		'is_admin': remote_comment.get('is_admin', False),
		'is_moderator': remote_comment.get('is_moderator', False),
		'is_removed': remote_comment.get('is_removed', False),
		'is_filtered': 'filter' in remote_comment.get('removal_source', '').lower(),
		'is_deleted':remote_comment.get('is_deleted', False),
		'is_edited': remote_comment.get('is_edited', False),
		'is_locked': False,
		'is_nsfw': False,
		'is_image': False,
		'removal_source': remote_comment.get('removal_source', ''),
		'raw_content': remote_comment['raw_content'].replace('\r\n', '\n'),
		'score': remote_comment.get('score', 0),
		'score_up': remote_comment.get('score_up', 0),
		'score_down': remote_comment.get('score_down', 0),
		'normalized_path': '/c/' + remote_comment['community'] + '/p/' + remote_comment['parent_uuid'] + '/x/c/' + remote_comment['uuid'],
		'parent_id': remote_comment.get('parent_id'),
		'parent_uuid': remote_comment.get('parent_uuid'),
		'post_title': remote_comment.get('post_title', ''),
		'post_author': remote_comment.get('post_author', ''),
		'comment_parent_id': remote_comment.get('comment_parent_id'),
		'child_ids': remote_comment.get('child_ids'),
		'urls': get_content_urls(remote_comment['community'], remote_comment['parent_id'], remote_comment['id']),
		'archive': d_archive,
		'moderation': d_moderation,
		'ban': d_ban,
	}
	
	if archived_comment is not None:
		if (comment['is_removed'] or comment['is_deleted']) and not archived_comment.legal_removed:
			comment['author'] = archived_comment.author
			comment['raw_content'] = archived_comment.raw_content.replace('\r\n', '\n')
		comment['ban'] = {
			'is_banned': bool(archived_comment.is_banned),
			'is_suspended': bool(archived_comment.is_suspended),
			'is_nuked': bool(archived_comment.is_nuked),
			'banned_by': archived_comment.banned_by,
			'ban_reason': archived_comment.ban_reason,
		}
		comment['moderation'] = {
			'removed_at': archived_comment.removed_at_ms if archived_comment.removed_at_ms else 0,
			'removed_by': archived_comment.removed_by if archived_comment.removed_by else '',
			'approved_at': archived_comment.approved_at_ms if archived_comment.approved_at_ms else 0,
			'approved_by': archived_comment.approved_by if archived_comment.approved_by else ''
		}
		comment['archive'] = {
			'is_archived': True,
			'archived_at': archived_comment.archived_at_ms,
			'legal_removed': bool(archived_comment.legal_removed),
			'legal_approved': bool(archived_comment.legal_approved),
			'recovered_from_log': bool(archived_comment.recovered_from_log),
			'recovered_from_scrape': False,
			'reportable': (
				st.config['reporting_enabled'] and
				comment['raw_content'] and
				not archived_comment.legal_removed and
				not archived_comment.legal_approved and
				(comment['is_removed'] or comment['is_deleted'])
			)
		}
	if comment['is_deleted'] and not comment['is_removed'] and not st.config['show_deleted']:
		if st.config['purge_deleted'] and archived_comment['raw_content'] != '':
			logger.logtrace('Purging deleted comment %d' % comment['id'])
			db.exec("UPDATE comments SET raw_content = '' WHERE id = ?", comment['id'])
		comment['raw_content'] = ''
	return comment






def fetch_thread(db: database.DBRequest, post_id: int):
	archived_post = db.queryrow("""
		SELECT
			posts.*,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			authors.is_suspended,
			authors.name AS author,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= posts.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM posts
		INNER JOIN authors ON authors.id = posts.author_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = posts.author_id AND known_bans.board_id = posts.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE posts.id = ?
	""", post_id)

	query = """
		SELECT
			comments.*,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			authors.is_suspended,
			authors.name AS author,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= comments.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM comments
		INNER JOIN authors ON authors.id = comments.author_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = comments.author_id AND known_bans.board_id = comments.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE comments.post_id = ?
	"""
	archivedCommentsById = {}
	for archived_comment in db.query(query, post_id):
		archivedCommentsById[archived_comment.id] = archived_comment

	resp = scoredapi.apireq('GET', '/api/v2/post/post.json', {
		'id': post_id,
		'comments': 'true'
	}, cache_ttl=150)
	if not resp['status']:
		raise RequestFailed(resp['error'])

	return {
		'post': merge_post_with_archived(db, resp['posts'][0], archived_post),
		'comments': [
			merge_comment_with_archived(db, comment, archivedCommentsById.get(comment['id']))
			for comment in sorted(resp['comments'], key=lambda c: c['id'])
		]
	}



def _fetch_suspended_profile_posts(db: database.DBRequest, username: str, page: int):
	author_id = database.get_author_id(db, username)
	query = """
		SELECT
			posts.*,
			authors.name AS author,
			boards.name AS community,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			TRUE AS is_suspended,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= posts.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM posts
		INNER JOIN authors ON authors.id = posts.author_id
		INNER JOIN boards ON boards.id = posts.board_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = posts.author_id AND known_bans.board_id = posts.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE posts.author_id = ?
		ORDER BY posts.id DESC
		LIMIT ?
		OFFSET ?
	"""
	limit = scoredapi.ITEMS_PER_PAGE
	offset = max(0, page - 1) * scoredapi.ITEMS_PER_PAGE
	archived_posts = db.query(query, author_id, limit, offset)
	simulated_posts = [
		{
			'id': archived_post.id,
			'uuid': scoredapi.scored_id_to_uuid(archived_post.id),
			'author': username,
			'community': archived_post.community,
			'type': archived_post.type,
			'link': archived_post.link,
			'raw_content': archived_post.raw_content,
			'is_removed': True
		}
		for archived_post in archived_posts
	]
	return {
		'is_suspended': True,
		'posts': [
			merge_post_with_archived(db, post, archived_post)
			for post, archived_post in zip(simulated_posts, archived_posts)
		],
		'has_more_entries': len(archived_posts) == limit
	}


def _fetch_suspended_profile_comments(db: database.DBRequest, username: str, page: int):
	author_id = database.get_author_id(db, username)
	query = """
		SELECT
			comments.*,
			authors.name AS author,
			boards.name AS community,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			TRUE AS is_suspended,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= comments.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM comments
		INNER JOIN authors ON authors.id = comments.author_id
		INNER JOIN boards ON boards.id = comments.board_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = comments.author_id AND known_bans.board_id = comments.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE comments.author_id = ?
		ORDER BY comments.id DESC
		LIMIT ?
		OFFSET ?
	"""
	limit = scoredapi.ITEMS_PER_PAGE
	offset = max(0, page - 1) * scoredapi.ITEMS_PER_PAGE
	archived_comments = db.query(query, author_id, limit, offset)
	simulated_comments = [
		{
			'id': archived_comment.id,
			'uuid': scoredapi.scored_id_to_uuid(archived_comment.id),
			'parent_id': archived_comment.post_id,
			'parent_uuid': scoredapi.scored_id_to_uuid(archived_comment.post_id),
			'author': username,
			'community': archived_comment.community,
			'raw_content': archived_comment.raw_content,
			'is_removed': True
		}
		for archived_comment in archived_comments
	]
	return {
		'is_suspended': True,
		'comments': [
			merge_comment_with_archived(db, comment, archived_comment)
			for comment, archived_comment in zip(simulated_comments, archived_comments)
		],
		'has_more_entries': len(archived_comments) == limit
	}


def fetch_profile_posts(db: database.DBRequest, username: str, page: int):
	isSuspended = False
	isDeleted = False
	resp = scoredapi.apireq('GET', '/api/v2/user/about.json', {
		'user': username
	}, cache_ttl=300)
	if not resp['status']:
		if resp['error'] == 'user is suspended':
			isSuspended = True
		else:
			raise RequestFailed(resp['error'])
	else:
		username = resp['users'][0]['username']
		if resp['users'][0]['is_deleted']:
			isDeleted = True
		if resp['users'][0]['is_suspended']:
			isSuspended = True

	if isDeleted:
		archive.mark_user_deleted(db, username)
		raise RequestFailed('User account deleted')

	elif isSuspended:
		archive.mark_user_suspended(db, username)
		return _fetch_suspended_profile_posts(db, username, page)

	else:
		resp = scoredapi.apireq('GET', '/api/v2/post/profile.json', {
			'user': username,
			'sort': 'new',
			'page': page,
			'community': 'win'
		})
		if not resp['status']:
			raise RequestFailed(resp['error'])
		
		query = """
			SELECT
				posts.*,
				authors.name AS author,
				COALESCE(known_bans.permabanned, FALSE) AS is_banned,
				authors.is_suspended,
				CASE
					WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= posts.created_ms THEN TRUE
					ELSE FALSE
				END is_nuked,
				moderators.name AS banned_by,
				known_bans.reason AS ban_reason
			FROM posts
			INNER JOIN authors ON authors.id = posts.author_id
			LEFT OUTER JOIN known_bans ON known_bans.target_id = posts.author_id AND known_bans.board_id = posts.board_id
			LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
			WHERE posts.id <= ? AND posts.id >= ? AND posts.author_id = ?
		"""
		archivedPostsById = {}
		if resp['posts']:
			firstId = resp['posts'][0]['id']
			lastId = resp['posts'][-1]['id']
			for archived_post in db.query(query, firstId, lastId, database.get_author_id(db, username)):
				archivedPostsById[archived_post.id] = archived_post

		return {
			'is_suspended': isSuspended,
			'posts': [
				merge_post_with_archived(db, post, archivedPostsById.get(post['id']))
				for post in sorted(resp['posts'], key=lambda p: p['id'])
			],
			'has_more_entries': resp['has_more_entries']
		}


def fetch_profile_comments(db: database.DBRequest, username: str, page: int):
	isSuspended = False
	isDeleted = False
	resp = scoredapi.apireq('GET', '/api/v2/user/about.json', {
		'user': username
	}, cache_ttl=300)
	if not resp['status']:
		if resp['error'] == 'user is suspended':
			isSuspended = True
		else:
			raise RequestFailed(resp['error'])
	else:
		username = resp['users'][0]['username']
		if resp['users'][0]['is_deleted']:
			isDeleted = True
		if resp['users'][0]['is_suspended']:
			isSuspended = True

	if isDeleted:
		archive.mark_user_deleted(db, username)
		raise RequestFailed('User account deleted')

	elif isSuspended:
		archive.mark_user_suspended(db, username)
		return _fetch_suspended_profile_comments(db, username, page)

	else:
		resp = scoredapi.apireq('GET', '/api/v2/comment/profile.json', {
			'user': username,
			'sort': 'new',
			'page': page,
			'community': 'win'
		})
		if not resp['status']:
			raise RequestFailed(resp['error'])
		
		query = """
			SELECT
				comments.*,
				COALESCE(known_bans.permabanned, FALSE) AS is_banned,
				authors.is_suspended,
				authors.name AS author,
				CASE
					WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= comments.created_ms THEN TRUE
					ELSE FALSE
				END is_nuked,
				moderators.name AS banned_by,
				known_bans.reason AS ban_reason
			FROM comments
			INNER JOIN authors ON authors.id = comments.author_id
			LEFT OUTER JOIN known_bans ON known_bans.target_id = comments.author_id AND known_bans.board_id = comments.board_id
			LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
			WHERE comments.id <= ? AND comments.id >= ? AND comments.author_id = ?
		"""
		archivedCommentsById = {}
		if resp['comments']:
			firstId = resp['comments'][0]['id']
			lastId = resp['comments'][-1]['id']
			for archived_comment in db.query(query, firstId, lastId, database.get_author_id(db, username)):
				archivedCommentsById[archived_comment.id] = archived_comment

		return {
			'is_suspended': isSuspended,
			'comments': [
				merge_comment_with_archived(db, comment, archivedCommentsById.get(comment['id']))
				for comment in sorted(resp['comments'], key=lambda c: c['id'])
			],
			'has_more_entries': resp['has_more_entries']
		}


def fetch_profile_removedcontent(db: database.DBRequest, username: str, from_post: int, from_comment: int):
	isSuspended = False
	isDeleted = False
	resp = scoredapi.apireq('GET', '/api/v2/user/about.json', {
		'user': username
	}, cache_ttl=300)
	if not resp['status']:
		if resp['error'] == 'user is suspended':
			isSuspended = True
		else:
			raise RequestFailed(resp['error'])
	else:
		username = resp['users'][0]['username']
		if resp['users'][0]['is_deleted']:
			isDeleted = True
		if resp['users'][0]['is_suspended']:
			isSuspended = True

	if isDeleted:
		archive.mark_user_deleted(db, username)
		raise RequestFailed('User account deleted.')

	if isSuspended:
		archive.mark_user_suspended(db, username)
		raise RequestFailed('User account suspended.')

	queryPost = """
		SELECT
			posts.*,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			authors.is_suspended,
			authors.name AS author,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= posts.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM posts
		INNER JOIN authors ON authors.id = posts.author_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = posts.author_id AND known_bans.board_id = posts.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE posts.id = ?
	"""

	queryComment = """
		SELECT
			comments.*,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			authors.is_suspended,
			authors.name AS author,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= comments.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM comments
		INNER JOIN authors ON authors.id = comments.author_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = comments.author_id AND known_bans.board_id = comments.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE comments.id = ?
	"""

	removed = []
	reqCount = 0
	has_more_entries = True
	upto = 0
	while reqCount < st.config['request_limit_profile']:
		reqCount += 1
		logger.logtrace('Request #%d (limit=%d)' % (reqCount, st.config['request_limit_profile']))
		resp = scoredapi.apireq('GET', '/api/v2/content/profile.json', {
			'user': username,
			'community': 'win',
			'post': from_post,
			'comment': from_comment,
		}, cache_ttl=120)
		if resp['status'] and len(resp['content']) > 0:
			upto = resp['content'][-1]['created']
			for content in resp['content']:
				if 'title' in content:
					from_post += 1
					if content['is_removed']:
						archived_post = db.queryrow(queryPost, content['id'])
						removed.append(merge_post_with_archived(db, content, archived_post))
				else:
					from_comment += 1
					if content['is_removed']:
						archived_comment = db.queryrow(queryComment, content['id'])
						removed.append(merge_comment_with_archived(db, content, archived_comment))
			if not resp['has_more_entries']:
				has_more_entries = False
				break
			
	return {
		'is_suspended': isSuspended,
		'content': sorted(removed, key=lambda x: x['created']),
		'from_post': from_post,
		'from_comment': from_comment,
		'upto': upto,
		'has_more_entries': has_more_entries
	}



def fetch_new_feed(db: database.DBRequest, community: str, from_uuid: str = None):
	resp = scoredapi.apireq('GET', '/api/v2/post/newv2.json', {
		'community': community,
		'from': from_uuid
	}, cache_ttl=60)
	if not resp['status']:
		raise RequestFailed(resp['error'])
	if len(resp['posts']) == 0:
		raise RequestFailed('No public posts in this community')
	board_id = database.get_board_id(db, community)
	firstId = resp['posts'][0]['id']
	lastId = resp['posts'][-1]['id']
	postsById = {}
	for post in resp['posts']:
		postsById[post['id']] = post

	query = """
		SELECT
			posts.*,
			COALESCE(known_bans.permabanned, FALSE) AS is_banned,
			authors.is_suspended,
			authors.name AS author,
			CASE
				WHEN known_bans.nuked_at_ms IS NOT NULL AND known_bans.nuked_at_ms >= posts.created_ms THEN TRUE
				ELSE FALSE
			END is_nuked,
			moderators.name AS banned_by,
			known_bans.reason AS ban_reason
		FROM posts
		INNER JOIN authors ON authors.id = posts.author_id
		LEFT OUTER JOIN known_bans ON known_bans.target_id = posts.author_id AND known_bans.board_id = posts.board_id
		LEFT OUTER JOIN authors AS moderators ON moderators.id = known_bans.moderator_id
		WHERE posts.id <= ? AND posts.id >= ? AND posts.board_id = ? AND NOT posts.known_deleted
	"""

	archivedById = {}
	for archived_post in db.query(query, firstId, lastId, board_id):
		archivedById[archived_post.id] = archived_post

	for id in postsById:
		postsById[id] = merge_post_with_archived(db, postsById[id], archivedById.get(id))

	requestCount = 0
	for id in archivedById:
		if id not in postsById:
			archived_post = archivedById[id]
			requestCount += 1
			if requestCount >= st.config['request_limit_feed']:
				logger.logwrn('Stopped checking missing posts in feed due to having reached the request limit')
				break
			resp = scoredapi.apireq('GET', '/api/v2/post/post.json', {
				'id': archived_post.id,
				'comments': 'false'
			}, cache_ttl=1800)
			if resp['status']:
				post = resp['posts'][0]
				if post['is_deleted']:
					db.exec("UPDATE posts SET known_deleted = TRUE WHERE id = ?", archived_post.id)
					logger.logtrace('Marked post %d as deleted' % archived_post.id)
				elif post['is_removed']:
					post = merge_post_with_archived(db, post, archived_post)
					postsById[post['id']] = post

	return {
		'posts': sorted(list(postsById.values()), key=lambda p: p['id'], reverse=True),
		'has_more_entries': resp.get('has_more_entries', True)
	}