import time

from utils import logger, helpers

import state as st
import database
import scoredapi


MONITORED_MODLOG_ACTIONS = [
	'removepost',
	'approvepost',
	'removecomment',
	'approvecomment',
	'lockpost',
	'unlockpost',
	'ignoreposts',
	'ignorecomments',
	'ban',
	'unban'
]


######################
### Data ingestion ###

def add_post(db: database.DBRequest, community: str, post: dict):
	logger.logdebug('Adding post: %s %d' % (community, post['id']))
	db.commit()
	board_id = database.get_board_id(db, community)
	author_id = database.get_author_id(db, post['author'])
	moderation = post.get('moderation', scoredapi.DEFAULT_MODERATION_INFO)
	IntegrityError = db.get_IntegrityError()
	try:
		db.exec(
			"""
			INSERT INTO posts (
				id,
				board_id,
				author_id,
				type,
				link,
				preview,
				title,
				raw_content,
				created_ms,
				known_deleted,
				archived_at_ms,
				removed_at_ms,
				removed_by,
				approved_at_ms,
				approved_by
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			post['id'],
			board_id,
			author_id,
			post['type'],
			post['link'],
			post['preview'],
			post['title'],
			post['raw_content'].replace('\r\n', '\n'),
			post['created'],
			post['is_deleted'],
			time.time_ns() // 1000,
			moderation['removed_at'] if moderation['removed_at'] else None,
			moderation['removed_by'] if moderation['removed_by'] else None,
			moderation['approved_at'] if moderation['approved_at'] else None,
			moderation['approved_by'] if moderation['approved_by'] else None
		)
	except IntegrityError:
		logger.logwrn('Post %d already in database' % post['id'])
		db.rollback()
	else:
		db.commit()


def add_comment(db: database.DBRequest, community: str, comment: dict):
	logger.logdebug('Adding comment: %s %d' % (community, comment['id']))
	db.commit()
	board_id = database.get_board_id(db, community)
	author_id = database.get_author_id(db, comment['author'])
	moderation = comment.get('moderation', scoredapi.DEFAULT_MODERATION_INFO)
	IntegrityError = db.get_IntegrityError()
	try:
		db.exec(
			"""
			INSERT INTO comments (
				id,
				board_id,
				author_id,
				post_id,
				comment_parent_id,
				raw_content,
				created_ms,
				archived_at_ms,
				removed_at_ms,
				removed_by,
				approved_at_ms,
				approved_by
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			comment['id'],
			board_id,
			author_id,
			comment['parent_id'],
			comment['comment_parent_id'],
			comment['raw_content'].replace('\r\n', '\n'),
			comment['created'],
			time.time_ns() // 1000,
			moderation['removed_at'] if moderation['removed_at'] else None,
			moderation['removed_by'] if moderation['removed_by'] else None,
			moderation['approved_at'] if moderation['approved_at'] else None,
			moderation['approved_by'] if moderation['approved_by'] else None
		)
	except IntegrityError:
		logger.logwrn('Comment %d already in database' % comment['id'])
		db.rollback()
	else:
		db.commit()


def update_comment_with_parentid(db: database.DBRequest, comment_id: int, comment_parent_id: int):
	logger.logdebug('Added parent id %d to comment %d' % (comment_parent_id, comment_id))
	db.exec("UPDATE comments SET comment_parent_id = ? WHERE id = ?", comment_id, comment_parent_id)



def _add_ban_record(db: database.DBRequest, timestamp_ms: int, board_id: int,
					moderator_id: int, target_id: int, is_banned: bool, reason='', nuke=False, permanent=False):
	logger.logdebug('Adding ban record: board_id=%d, target_id=%d, is_banned=%s' % (board_id, target_id, is_banned))
	current = db.queryrow("SELECT * FROM known_bans WHERE board_id = ? AND target_id = ?", board_id, target_id)
	if current is None:
		db.exec(
			"""
			INSERT INTO known_bans (
				board_id,
				moderator_id,
				target_id,
				permabanned,
				nuked_at_ms,
				reason
			) VALUES (?, ?, ?, ?, ?, ?)
			""",
			board_id,
			moderator_id,
			target_id,
			is_banned and permanent,
			timestamp_ms if nuke else 0,
			reason
		)
	elif is_banned:
		db.exec(
			"""
			UPDATE known_bans SET
				moderator_id = ?,
				permabanned = ?,
				nuked_at_ms = ?,
				reason = ?
			WHERE
				board_id = ? AND
				target_id = ?
			""",
			moderator_id,
			permanent,
			timestamp_ms if nuke else current.nuked_at_ms,
			reason,
			board_id,
			target_id
		)
	elif not is_banned:
		db.exec(
			"""
			UPDATE known_bans SET
				permabanned = FALSE
			WHERE
				board_id = ? AND
				target_id = ?
			""",
			board_id,
			target_id
		)


def add_modlog_record(db: database.DBRequest, community: str, record: dict):
	logger.logdebug('Adding mod log record: %s, type=%s, created_ms=%d' % (community, record['type'], record['created']))
	board_id = database.get_board_id(db, community)
	moderator = record['moderator']
	moderator_id = database.get_author_id(db, record['moderator'])
	target_id = database.get_author_id(db, record['target'])
	timestamp = record['created']
	post_id = record['postId']
	comment_id = record['commentId']
	description = record['description'] if len(record['description']) < 200 else record['description'] + '...'
	
	IntegrityError = db.get_IntegrityError()
	try:
		db.exec(
			"""
			INSERT INTO modlogs (
				board_id,
				moderator_id, 
				target_id,
				created_ms,
				type,
				description,
				post_id,
				comment_id
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			board_id,
			moderator_id,
			target_id,
			record['created'],
			record['type'],
			record['description'],
			record['postId'] if record['postId'] else None,
			record['commentId'] if record['commentId'] else None
		)
	except IntegrityError:
		logger.logwrn('Modlog record %d already in database' % record['created'])
		db.rollback()
		return
	else:
		db.commit()

	if record['type'] in ('ban', 'unban'):
		desc: str = record['description']
		logger.logtrace('New ban record: %s %s in %s (%s)' % (record['type'], record['target'], community, desc))
		is_banned = record['type'] == 'ban'
		permanent = desc.startswith('0 day')
		nuke = 'nuke' in desc[:desc.find(':')]
		reason = desc[desc.find(':')+1:].strip()
		_add_ban_record(db, record['created'], board_id, moderator_id, target_id, is_banned, reason, nuke, permanent)
	
	elif record['type'] == 'approvepost':
		db.exec("UPDATE posts SET approved_at_ms = ?, approved_by = ? WHERE id = ?", timestamp, moderator, post_id)

	elif record['type'] == 'approvecomment':
		db.exec("UPDATE comments SET approved_at_ms = ?, approved_by = ? WHERE id = ?", timestamp, moderator, comment_id)

	elif record['type'] == 'removepost':
		db.exec("UPDATE posts SET removed_at_ms = ?, removed_by = ? WHERE id = ?", timestamp, moderator, post_id)

	elif record['type'] == 'removecomment':
		db.exec("UPDATE comments SET removed_at_ms = ?, removed_by = ? WHERE id = ?", timestamp, moderator, comment_id)
		db.exec("UPDATE comments SET raw_content = ?, recovered_from_log = TRUE WHERE id = ? AND raw_content = ''", description, comment_id)


def mark_user_suspended(db: database.DBRequest, username):
	user_id = database.get_author_id(db, username)
	db.exec("UPDATE authors SET is_suspended = TRUE WHERE id = ? AND NOT is_suspended", user_id)
	if db.rowcount:
		logger.log('Marked user %s as suspended' % username)

def mark_user_deleted(db: database.DBRequest, username):
	user_id = database.get_author_id(db, username)
	db.exec("UPDATE authors SET is_deleted = TRUE WHERE id = ? AND NOT is_deleted", user_id)
	if db.rowcount:
		logger.log('Marked user %s as deleted' % username)
		if st.config['purge_deleted']:
			logger.log('Purging content by deleted user %s from database' % username)
			db.exec("UPDATE posts SET title = '', link = '', raw_content = '', known_deleted = TRUE WHERE author_id = ?", user_id)
			logger.log('%d posts purged' % db.rowcount)
			db.exec("UPDATE comments SET raw_content = '' WHERE author_id = ?", user_id)
			logger.log('%d comments purged' % db.rowcount)



def process_removal_request(db: database.DBRequest, ip: str, content_type: str, content_id: int, reason: str, description: str):
	if content_type == 'post':
		item = db.queryrow("SELECT * FROM posts WHERE id = ?", content_id)
	else:
		item = db.queryrow("SELECT * FROM comments WHERE id = ?", content_id)
	if item and st.config['reporting_enabled'] and not item.legal_approved and not item.legal_removed:
		post_id = comment_id = None
		if content_type == 'post':
			post_id = content_id
			logger.log("Removal request submitted on post %d" % content_id)
			db.exec("UPDATE posts SET legal_removed = TRUE WHERE id = ?", content_id)
		else:
			post_id = db.queryval("SELECT post_id FROM comments WHERE id = ?", content_id)
			comment_id = content_id
			logger.log("Removal request submitted on comment %d" % content_id)
			db.exec("UPDATE comments SET legal_removed = TRUE WHERE id = ?", content_id)
		db.exec("""
			INSERT INTO removal_requests (time, ip, reason, description, post_id, comment_id)
			VALUES (?, ?, ?, ?, ?, ?)
		""", int(time.time()), ip, reason, description, post_id, comment_id)
		return {'status': True}
	else:
		return {
			'status': False,
			'error': 'Not reportable'
		}

def approve_item(db: database.DBRequest, content_type: str, content_id: int):
	if content_type == 'post':
		db.exec("UPDATE posts SET legal_removed = FALSE, legal_approved = TRUE WHERE id = ?", content_id)
		db.exec("UPDATE removal_requests SET cleared = TRUE WHERE post_id = ?", content_id)
	else:
		db.exec("UPDATE comments SET legal_removed = FALSE, legal_approved = TRUE WHERE id = ?", content_id)
		db.exec("UPDATE removal_requests SET cleared = TRUE WHERE comment_id = ?", content_id)
	logger.log('Approved archived content: %s %d' % (content_type, content_id))

def remove_item(db: database.DBRequest, content_type: str, content_id: int):
	if content_type == 'post':
		db.exec("UPDATE posts SET legal_removed = TRUE, legal_approved = FALSE WHERE id = ?", content_id)
		db.exec("UPDATE removal_requests SET cleared = TRUE WHERE post_id = ?", content_id)
	else:
		db.exec("UPDATE comments SET legal_removed = TRUE, legal_approved = FALSE WHERE id = ?", content_id)
		db.exec("UPDATE removal_requests SET cleared = TRUE WHERE comment_id = ?", content_id)
	logger.log('Removed archived content: %s %d' % (content_type, content_id))

def fetch_removal_requests(db: database.DBRequest, cleared=False):
	r = []
	for request in db.query("SELECT * FROM removal_requests WHERE cleared = ?", cleared):
		if request.comment_id:
			comment_uuid = scoredapi.scored_id_to_uuid(request.comment_id)
			post_uuid = scoredapi.scored_id_to_uuid(request.post_id)
			url = '/p/%s/x/c/%s' % (post_uuid, comment_uuid)
		else:
			post_uuid = scoredapi.scored_id_to_uuid(request.post_id)
			url = '/p/%s' % post_uuid
		r.append({
			'ip': request.ip,
			'time': request.time,
			'timeago': helpers.timeago(request.time),
			'reason': request.reason,
			'description': request.description,
			'post_id': request.post_id,
			'comment_id': request.comment_id,
			'url': url,
		})
	return r