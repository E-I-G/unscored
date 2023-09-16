import re
import time
import sqlite3
import contextlib
from collections import namedtuple

with contextlib.suppress(ImportError):
	import psycopg2
	import psycopg2.extras

from utils import logger

import state as st

def sqlite3_namedtuple_factory(cursor, row):
	fields = [column[0] for column in cursor.description]
	cls = namedtuple("Row", fields)
	return cls._make(row)



class DBRequest:
	rowcount = 0
	statusmessage = None
	def __init__(self, dbType=None):
		if dbType:
			self.dbType = dbType
		else:
			self.dbType = st.config['database']
		tStart = time.time_ns()
		if self.dbType == 'postgres':
			self.con = psycopg2.connect(
				dbname = st.config['postgres_dbname'],
				host = st.config['postgres_host'],
				port = st.config['postgres_port'],
				user = st.config['postgres_user'],
				password = st.config['postgres_password'],
				cursor_factory = psycopg2.extras.NamedTupleCursor
			)
		else:
			self.con = sqlite3.connect(st.config['sqlite_path'])
			self.con.row_factory = sqlite3_namedtuple_factory
		ms = (time.time_ns() - tStart) // 10**6
		logger.logtrace('Connected to %s in %d ms' % (self.dbType, ms))

	def _convert_query(self, query):
		if self.dbType == 'postgres':
			query = query.replace('?', '%s')
			query = re.sub(re.escape('integer PRIMARY KEY AUTOINCREMENT'), 'bigserial PRIMARY KEY', query, flags=re.IGNORECASE)
			query = re.sub(re.escape('group_concat'), 'string_agg', query, flags=re.IGNORECASE)
			query = re.sub(r'(\s)(LIKE)(\s)', r'\1I\2\3', query, flags=re.IGNORECASE)
		return query
	
	def _get_ProgrammingError(self):
		if self.dbType == 'postgres':
			return psycopg2.ProgrammingError
		else:
			return sqlite3.ProgrammingError
		
	def get_IntegrityError(self):
		if self.dbType == 'postgres':
			return psycopg2.IntegrityError
		else:
			return sqlite3.IntegrityError

	def _execute_query(self, query, args=tuple(), convert_query=True, return_mode=None):
		ProgrammingError = self._get_ProgrammingError()

		if convert_query:
			query = self._convert_query(query)

		if args and isinstance(args[0], tuple):
			args = args[0]

		with contextlib.closing(self.con.cursor()) as cur:
			cur.execute(query, args)
			self.rowcount = cur.rowcount
			if self.dbType == 'postgres':
				self.statusmessage = cur.statusmessage
			if return_mode == 'all':
				try:
					return cur.fetchall()
				except (ProgrammingError):
					return []
			elif return_mode == 'row':
				try:
					return cur.fetchone()
				except (ProgrammingError):
					return None
			elif return_mode == 'scalar':
				try:
					return cur.fetchone()[0]
				except (IndexError, TypeError, ProgrammingError):
					return None
			elif return_mode == 'boolean':
				try:
					return bool(cur.fetchone())
				except (IndexError, ProgrammingError):
					return False

	def has_table(self, name):
		with contextlib.closing(self.con.cursor()) as cur:
			if self.dbType == 'postgres':
				cur.execute("SELECT * FROM information_schema.tables WHERE table_name=%s", (name.lower(),))
			else:
				cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,))
			r = cur.fetchall()
		return bool(r)

	def has_field(self, table, field):
		with contextlib.closing(self.con.cursor()) as cur:
			if self.dbType == 'postgres':
				q = "SELECT column_name FROM information_schema.columns WHERE table_name=%s and column_name=%s;"
				cur.execute(q, (table.lower(), field.lower()))
				return bool(cur.fetchall())
			else:
				cur.execute("SELECT COUNT(*) AS CNTREC FROM pragma_table_info(?) WHERE name = ?", (table, field))
				return bool(cur.fetchall()[0][0])

	def exec(self, query, *args):
		self._execute_query(query, args)

	def query(self, query, *args):
		tStart = time.time_ns()
		rows = self._execute_query(query, args, return_mode='all')
		ms = (time.time_ns() - tStart) // 10**6
		logger.logtrace("Query finished in %d ms returning %d rows" % (ms, len(rows)))
		return rows

	def queryrow(self, query, *args):
		return self._execute_query(query, args, return_mode='row')

	def queryval(self, query, *args):
		return self._execute_query(query, args, return_mode='scalar')

	def queryexists(self, query, *args):
		return self._execute_query(query, args, return_mode='boolean')

	def queryraw(self, query):
		if self.dbType == 'postgres':
			query = query.replace('%', '%%')
		return self._execute_query(query, convert_query=False, return_mode='all')

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()

	def commit(self):
		self.con.commit()

	def rollback(self):
		self.con.rollback()

	def close(self):
		self.con.commit()
		self.con.close()


boardIds = {}
authorIds = {}

def get_board_id(db: DBRequest, community: str, allow_insert=True):
	if community.lower() in boardIds:
		return boardIds[community.lower()]
	else:
		if not allow_insert:
			return 0
		id = db.queryval("INSERT INTO boards (name) VALUES (?) RETURNING id", community)
		boardIds[community.lower()] = id
		logger.logdebug('Assigned id %d to board %s' % (id, community))
		return id
	
def get_author_id(db: DBRequest, author: str, allow_insert=True):
	if author.lower() in authorIds:
		return authorIds[author.lower()]
	else:
		if not allow_insert:
			return 0
		id = db.queryval("INSERT INTO authors (name) VALUES (?) RETURNING id", author)
		authorIds[author.lower()] = id
		logger.logdebug('Assigned id %d to author %s' % (id, repr(author)))
		return id
	


def convert_database(db1: DBRequest, db2: DBRequest):
	for row in db1.query("SELECT id, name FROM boards ORDER BY id"):
		db2.exec("INSERT INTO boards (name) VALUES (?)", row.name)


def _perform_db_upgrades(db: DBRequest):
	if not db.has_field('comments', 'known_deleted'):
		db.exec("ALTER TABLE comments ADD COLUMN known_deleted boolean DEFAULT FALSE")

	if not db.has_field('posts', 'recovery_method'):
		db.exec("UPDATE posts SET archived_at_ms = archived_at_ms / 1000")
		db.exec("ALTER TABLE posts ADD COLUMN recovery_method text DEFAULT NULL")
		fromScrape = [row.id for row in db.query("SELECT id FROM posts WHERE recovered_from_scrape")]
		for id in fromScrape:
			db.exec("UPDATE posts SET recovery_method = 'scrape' WHERE id = ?", id)
		fromLog = [row.id for row in db.query("SELECT id FROM posts WHERE recovered_from_log")]
		for id in fromLog:
			db.exec("UPDATE posts SET recovery_method = 'log' WHERE id = ?", id)
		db.exec("ALTER TABLE posts DROP column recovered_from_scrape")
		db.exec("ALTER TABLE posts DROP column recovered_from_log")
		db.commit()
	
	if not db.has_field('comments', 'recovery_method'):
		db.exec("UPDATE comments SET archived_at_ms = archived_at_ms / 1000")
		db.exec("ALTER TABLE comments ADD COLUMN recovery_method text DEFAULT NULL")
		fromLog = [row.id for row in db.query("SELECT id FROM comments WHERE recovered_from_log")]
		for id in fromLog:
			db.exec("UPDATE comments SET recovery_method = 'log' WHERE id = ?", id)
		db.exec("ALTER TABLE comments DROP column recovered_from_log")
		db.commit()
	
	if not db.has_field('posts', 'removal_source'):
		db.exec("ALTER TABLE posts ADD COLUMN removal_source text DEFAULT NULL")
		db.exec("UPDATE posts SET removal_source = 'unknown' WHERE recovery_method IS NOT NULL")
		db.exec("UPDATE posts SET removal_source = 'unknown' WHERE title = ''")
		cfIds = [row.id for row in db.query("SELECT id FROM posts WHERE removed_by = 'CommunityFilter' OR removed_by = 'Filter'")]
		gfIds = [row.id for row in db.query("SELECT id FROM posts WHERE removed_by = 'GlobalFilter'")]
		for id in cfIds:
			db.exec("UPDATE posts SET removal_source = 'communityFilter' WHERE id = ?", id)
		for id in gfIds:
			db.exec("UPDATE posts SET removal_source = 'spamFilter' WHERE id = ?", id)
		db.commit()
	
	if not db.has_field('comments', 'removal_source'):
		db.exec("ALTER TABLE comments ADD COLUMN removal_source text DEFAULT NULL")
		db.exec("UPDATE comments SET removal_source = 'unknown' WHERE recovery_method IS NOT NULL")
		db.exec("UPDATE comments SET removal_source = 'unknown' WHERE raw_content = ''")
		cfIds = [row.id for row in db.query("SELECT id FROM comments WHERE removed_by = 'CommunityFilter' OR removed_by = 'Filter'")]
		gfIds = [row.id for row in db.query("SELECT id FROM comments WHERE removed_by = 'GlobalFilter'")]
		for id in cfIds:
			db.exec("UPDATE comments SET removal_source = 'communityFilter' WHERE id = ?", id)
		for id in gfIds:
			db.exec("UPDATE comments SET removal_source = 'spamFilter' WHERE id = ?", id)
		db.commit()



def init_database():
	logger.log('Preparing database')
	db = DBRequest()

	db.exec("""
		CREATE TABLE IF NOT EXISTS boards (
			id integer PRIMARY KEY AUTOINCREMENT,
			name text
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS authors (
			id integer PRIMARY KEY AUTOINCREMENT,
			name text,
			is_suspended boolean DEFAULT FALSE,
			is_deleted boolean DEFAULT FALSE
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS posts (
			id integer PRIMARY KEY,
			board_id integer NOT NULL,
			author_id integer NOT NULL,
			type text,
			link text,
			preview text,
			title text,
			raw_content text,
			created_ms bigint,
			archived_at_ms bigint,
			known_deleted boolean DEFAULT FALSE,
			removal_source text DEFAULT NULL,
			approved_at_ms bigint DEFAULT NULL,
			approved_by text DEFAULT NULL,
			removed_at_ms bigint DEFAULT NULL,
			removed_by text DEFAULT NULL,
			legal_removed boolean DEFAULT FALSE,
			legal_approved boolean DEFAULT FALSE,
			FOREIGN KEY(board_id) REFERENCES boards(id),
			FOREIGN KEY(author_id) REFERENCES authors(id)
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS comments (
			id integer PRIMARY KEY,
			board_id integer NOT NULL,
			author_id integer NOT NULL,
			post_id integer,
			comment_parent_id integer DEFAULT NULL,
			raw_content text,
			created_ms bigint,
			archived_at_ms bigint,
			known_deleted boolean DEFAULT FALSE,
			removal_source text DEFAULT NULL,
			approved_at_ms bigint DEFAULT NULL,
			approved_by text DEFAULT NULL,
			removed_at_ms bigint DEFAULT NULL,
			removed_by text DEFAULT NULL,
			legal_removed boolean DEFAULT FALSE,
			legal_approved boolean DEFAULT FALSE,
			FOREIGN KEY(board_id) REFERENCES boards(id),
			FOREIGN KEY(author_id) REFERENCES authors(id)
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS modlogs (
			created_ms bigint PRIMARY KEY,
			board_id integer NOT NULL,
			moderator_id integer NOT NULL,
			target_id integer NOT NULL,
			type text,
			description text,
			post_id integer DEFAULT NULL,
			comment_id integer DEFAULT NULL,
			FOREIGN KEY(board_id) REFERENCES boards(id),
			FOREIGN KEY(target_id) REFERENCES authors(id),
			FOREIGN KEY(moderator_id) REFERENCES authors(id)
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS known_bans (
			board_id integer NOT NULL,
			moderator_id integer NOT NULL,
			target_id integer NOT NULL,
			permabanned boolean,
			nuked_at_ms bigint,
			reason text,
			FOREIGN KEY(board_id) REFERENCES boards(id),
			FOREIGN KEY(moderator_id) REFERENCES authors(id),
			FOREIGN KEY(target_id) REFERENCES authors(id)
		);
	""")

	db.exec("""
		CREATE TABLE IF NOT EXISTS removal_requests (
			time bigint,
			ip text,
			reason text,
			description text,
			post_id integer DEFAULT NULL,
			comment_id integer DEFAULT NULL,
			cleared boolean DEFAULT FALSE
		);
	""")

	_perform_db_upgrades(db)

	for row in db.query("SELECT id, name FROM boards ORDER BY id"):
		if row.name.lower() in boardIds:
			logger.logwrn('Removing duplicate board id: %d %s' % (row.id, row.name))
			db.exec("UPDATE posts SET board_id = ? WHERE board_id = ?", boardIds[row.name.lower()], row.id)
			db.exec("UPDATE comments SET board_id = ? WHERE board_id = ?", boardIds[row.name.lower()], row.id)
			db.exec("UPDATE modlogs SET board_id = ? WHERE board_id = ?", boardIds[row.name.lower()], row.id)
			db.exec("UPDATE known_bans SET board_id = ? WHERE board_id = ?", boardIds[row.name.lower()], row.id)
			db.exec("DELETE FROM boards WHERE id = ?", row.id)
		else:
			boardIds[row.name.lower()] = row.id

	for row in db.query("SELECT id, name FROM authors ORDER BY id"):
		if row.name.lower() in authorIds:
			logger.logwrn('Removing duplicate author id: %d %s' % (row.id, row.name))
			db.exec("UPDATE posts SET author_id = ? WHERE author_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("UPDATE comments SET author_id = ? WHERE author_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("UPDATE modlogs SET moderator_id = ? WHERE moderator_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("UPDATE modlogs SET target_id = ? WHERE target_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("UPDATE known_bans SET moderator_id = ? WHERE moderator_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("UPDATE known_bans SET target_id = ? WHERE target_id = ?", authorIds[row.name.lower()], row.id)
			db.exec("DELETE FROM authors WHERE id = ?", row.id)
		authorIds[row.name.lower()] = row.id

	db.close()