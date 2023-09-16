import os
import mimetypes
import json
import urllib.parse

import flask

from utils import helpers
import state as st
import database
import datafetch
import scoredapi
import archive

from webserver import wapp

@wapp.route('GET', '/')
def root_page():
	return flask.render_template('pages/front.html')


@wapp.route('GET', '/admin-dashboard/')
def admin_dashboard():
	if wapp.is_admin():
		with database.DBRequest() as db:
			removalRequests = archive.fetch_removal_requests(db, cleared=False)
		return flask.render_template('pages/admin/dashboard.html', removalRequests=removalRequests)
	else:
		return flask.render_template('pages/admin/login.html')

@wapp.route('GET', '/admin-dashboard/ip-blocks/', is_admin=True)
def admin_dashboard_ipblocks():
	return flask.Response('\n'.join(st.blockedIPs), mimetype='text/plain')

@wapp.route('GET', '/admin-dashboard/db/', is_admin=True)
def admin_dbtool():
	return flask.render_template('pages/admin/dbquery.html')

@wapp.route('POST', '/admin-login')
def admin_login():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	username = flask.request.form['username']
	password = flask.request.form['password']
	if username == st.config['admin_username'] and password == st.config['admin_password']:
		flask.session['is_admin'] = True
	return flask.redirect('/admin-dashboard/')


@wapp.route('GET', [
	'/<path:path>/',
	'/<path:path>'
])
def scored_path(path):
	path = '/' + path
	url = urllib.parse.urlparse(path)
	params = datafetch.parse_url(path)
	normUrl = urllib.parse.urlparse(params['normalized_path'])
	if url.path != normUrl.path:
		return flask.redirect(normUrl.path + url.params)
	elif params['type'] == 'thread':
		return flask.render_template('pages/thread.html')
	elif params['type'] == 'feed':
		return flask.render_template('pages/feed.html')
	elif params['type'] == 'profile':
		return flask.render_template('pages/profile.html')
	elif params['type'] == 'communities':
		return flask.render_template('pages/communities.html')
	elif params['type'] == 'modlog':
		return flask.render_template('pages/modlog.html')
	else:
		flask.abort(404)



#########################
### AJAX .json routes ###

@wapp.route('GET', '/ajax/parseurl.json')
def ajax_parseurl():
	raw_url = flask.request.args.get('url', '')
	try:
		return flask.jsonify(datafetch.parse_url(raw_url))
	except datafetch.InvalidURL:
		return flask.jsonify({
			'error': 'Invalid URL'
		})
	

@wapp.route('GET', '/ajax/thread.json')
def ajax_get_thread():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	if 'post_uuid' in flask.request.args:
		post_id = scoredapi.scored_uuid_to_id(flask.request.args['post_uuid'])
	else:
		post_id = helpers.safeint(flask.request.args.get('post_id'))
	if post_id < 1:
		return flask.jsonify({
			'error': 'Invalid or missing post_id'
		})
	with database.DBRequest() as db:
		try:
			return flask.jsonify(datafetch.fetch_thread(db, post_id))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})


@wapp.route('GET', '/ajax/profile.json')
def ajax_get_profile():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	username = flask.request.args.get('user', '')
	contentType = flask.request.args.get('type', 'comment')
	page = helpers.safeint(flask.request.args.get('page'), 1)
	from_post = helpers.safeint(flask.request.args.get('from_post'), 0)
	from_comment = helpers.safeint(flask.request.args.get('from_comment'), 0)
	with database.DBRequest() as db:
		try:
			if contentType == 'removed':
				return flask.jsonify(datafetch.fetch_profile_removedcontent(db, username, from_post, from_comment))
			if contentType == 'post':
				return flask.jsonify(datafetch.fetch_profile_posts(db, username, page))
			else:
				return flask.jsonify(datafetch.fetch_profile_comments(db, username, page))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})


@wapp.route('GET', '/ajax/feed.json')
def ajax_get_feed():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	community = flask.request.args.get('community', '')
	from_uuid = flask.request.args.get('from', None)
	with database.DBRequest() as db:
		try:
			return flask.jsonify(datafetch.fetch_new_feed(db, community, from_uuid))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})
		

@wapp.route('GET', '/ajax/communities.json')
def ajax_get_communities():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	page = helpers.safeint(flask.request.args.get('page'), 1)
	sort = flask.request.args.get('sort', 'activity')
	communities = [
		{
			'name': key,
			'modlog_status': 'full' if c['modlogs'] else 'bans' if c['banlogs'] else 'none',
			'interval': c.get('interval', 0),
			'last_ingested': c.get('last_ingested', 0),
			'description': c.get('description', '').replace('\r', '').replace('\n', ' '),
			'has_icon': c.get('has_icon', False),
			'app_safe': c.get('app_safe', True),
			'visibility': c.get('visibility', 'public')
		}
		for key, c in st.ingest.items()
		if key != 'global'
	]
	if sort == 'activity':
		communities.sort(key=lambda x: x['interval'])
	elif sort == 'restricted':
		communities = [c for c in communities if c['visibility'] != 'public' or not c['app_safe']]
		communities.sort(key=lambda x: x['interval'])
	else:
		communities.sort(key=lambda x: x['name'])
	return flask.jsonify({
		'communities': communities[(page-1)*25:(page-1)*25+25],
		'page': page,
		'has_more_entries': (page-1)*25+25 < len(communities)
	})


@wapp.route('GET', '/ajax/logs.json')
def ajax_get_logs():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	page = helpers.safeint(flask.request.args.get('page'), 1)
	community = flask.request.args['community']
	action = flask.request.args.get('action', '*')
	moderator = flask.request.args.get('moderator', '*')
	target = flask.request.args.get('target', '*')
	with database.DBRequest() as db:
		try:
			return flask.jsonify(datafetch.fetch_modlogs(db, community, page, action, moderator, target))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})
		


@wapp.route('GET', '/ajax/post.json')
def ajax_get_post():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	post_id = helpers.safeint(flask.request.args.get('post_id'), 0)
	with database.DBRequest() as db:
		try:
			return flask.jsonify(datafetch.fetch_single_post(db, post_id))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})
		

@wapp.route('GET', '/ajax/comment.json')
def ajax_get_comment():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	post_id = helpers.safeint(flask.request.args.get('post_id'), 0)
	comment_id = helpers.safeint(flask.request.args.get('comment_id'), 0)
	with database.DBRequest() as db:
		try:
			return flask.jsonify(datafetch.fetch_single_comment(db, post_id, comment_id))
		except datafetch.RequestFailed as e:
			return flask.jsonify({
				'error': str(e)
			})




@wapp.route('POST', '/ajax/removal-request')
def ajax_removal_request():
	st.enforce_api_ratelimit(flask.request.remote_addr)
	ip = flask.request.remote_addr
	content_type = flask.request.form.get('type', 'post')
	content_id = helpers.safeint(flask.request.form.get('id'))
	reason = flask.request.form.get('reason', 'no reason')[:128]
	description = flask.request.form.get('description', 'no description')[:5000]
	with database.DBRequest() as db:
		resp = archive.process_removal_request(db, ip, content_type, content_id, reason, description)
		return flask.jsonify(resp)

@wapp.route('POST', '/ajax/legal-remove-item', is_admin=True)
def ajax_legal_remove_item():
	content_type = flask.request.form.get('type', 'post')
	content_id = helpers.safeint(flask.request.form.get('id'))
	with database.DBRequest() as db:
		archive.remove_item(db, content_type, content_id)
		return flask.jsonify({'status': True})

@wapp.route('POST', '/ajax/legal-approve-item', is_admin=True)
def ajax_legal_approve_item():
	if not wapp.is_admin():
		flask.abort(403)
	content_type = flask.request.form.get('type', 'post')
	content_id = helpers.safeint(flask.request.form.get('id'))
	with database.DBRequest() as db:
		archive.approve_item(db, content_type, content_id)
		return flask.jsonify({'status': True})

@wapp.route('POST', '/ajax/block-ip', is_admin=True)
def ajax_block_ip():
	ip = flask.request.form.get('ip', '')
	st.block_ip(ip)
	return flask.jsonify({'status': True})

@wapp.route('POST', '/ajax/unblock-ip', is_admin=True)
def ajax_unblock_ip():
	ip = flask.request.form.get('ip', '')
	st.unblock_ip(ip)
	return flask.jsonify({'status': True})


@wapp.route('POST', '/ajax/db-query', is_admin=True)
def ajax_db_query():
	query = flask.request.form['query']
	error = None
	r = None
	with database.DBRequest() as db:
		try:
			r = db.queryraw(query)
		except Exception as e:
			error = '%s: %s' % (e.__class__.__name__, e)
		return flask.jsonify({
			'data': [[json.dumps(cell) for cell in row] for row in r] if r else None,
			'fields': r[0]._fields if r else [],
			'rowcount': db.rowcount if not error else 0,
			'statusmessage': db.statusmessage if not error else None,
			'error': error,
			'status': not error
		})



########################
### Static resources ###

@wapp.route('GET', '/static/<path:path>')
def serve_static_file(path):
	#Not for use in a production environment.
	fileMimetype = mimetypes.guess_type(path, False)
	return flask.send_from_directory(
		os.path.join(wapp.root_path, 'static'),
		path,
		mimetype = fileMimetype
	)

@wapp.route('GET', '/robots.txt')
def serve_robots_file():
	#Not for use in a production environment.
	return flask.send_from_directory(os.path.join(wapp.root_path, 'static'), 'robots.txt')