import os
import secrets
import contextlib
from functools import wraps
from logging import getLogger

from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
import flask
import flask_compress

import eventlet
import eventlet.wsgi

from utils import logger
import state as st


MAX_CONTENT_LENGTH = 5 * 2**20
PERMANENT_SESSION_LIFETIME = 365 * 24 * 60 * 60

SVGFILES = {}

def _load_svgs():
	directory = os.path.join(wapp.root_path, 'static', 'svg')
	for filename in os.listdir(directory):
		with open(os.path.join(directory, filename), 'r') as f:
			SVGFILES[filename[:filename.rfind('.')]] = f.read()


class WebApplication:
	running = False
	host = '0.0.0.0'
	port = 0

	def __init__(self):
		self.app = flask.Flask(__name__)
		self.root_path = self.app.root_path
		self.registeredFlaskRoutes = []
	
	def initialize(self):
		logger.logtrace('Initializing Flask app')
		logger.logtrace('Initializing compression')
		compress = flask_compress.Compress()
		compress.init_app(self.app)
		logger.logtrace('Initializing ProxyFix')
		self.app.wsgi_app = ProxyFix(self.app.wsgi_app)
		logger.logtrace('Adding URL routes to Flask app')
		for rule in self.registeredFlaskRoutes:
			url = rule['url']
			func = rule['func']
			methods = rule['methods']
			self.app.add_url_rule(url, func.__name__, func, methods=methods)

	def get_secret_key(self):
		if os.path.exists(st.SESSION_SECRET_FILE):
			with open(st.SESSION_SECRET_FILE, 'r') as f:
				return f.read().strip()
		else:
			secret = secrets.token_urlsafe(48)
			with open(st.SESSION_SECRET_FILE, 'w') as f:
				f.write(secret)
			return secret

	def start(self, host, port):
		self.host = host
		self.port = port
		logger.log('Starting web server on %s:%s' % (self.host, self.port))
		self.app.secret_key = self.get_secret_key()
		self.app.config['SECRET_KEY'] = self.get_secret_key()
		self.app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
		self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 12 * 60 * 60
		self.app.config['SESSION_COOKIE_PATH'] = '/'
		self.app.config['SESSION_REFRESH_EACH_REQUEST'] = True
		self.app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
		self.app.config['PERMANENT_SESSION_LIFETIME'] = 365 * 24 * 60 * 60
		self.running = True
		werkzeugLog = getLogger('werkzeug')
		werkzeugLog.disabled = True
		self.app.logger.disabled = True
		eventlet.wsgi.server(eventlet.listen((self.host, self.port)), self.app, log_output=False)

	def is_admin(self):
		return flask.session.get('is_admin', False)

	def route(self, methods, urls, is_admin=False):
		if isinstance(methods, str):
			methods = [methods]
		if isinstance(urls, str):
			urls = [urls]
		def decorator(f):
			@wraps(f)
			def decorated_function(*args, **kwargs):
				if is_admin and not self.is_admin():
					flask.abort(403)
				return f(*args, **kwargs)
			for url in urls:
				self.registeredFlaskRoutes.append({
					'url': url,
					'func': decorated_function,
					'methods': methods
				})
			return decorated_function
		return decorator


wapp = WebApplication()


def start_webserver():
	wapp.initialize()
	_load_svgs()
	wapp.start(st.config['host'], st.config['port'])



from . import routes
from . import weblogging
from datafetch import InvalidURL

@wapp.app.context_processor
def template_context_processor():
	return {
		'SVGFILES': SVGFILES,
		'config': st.config,
		'is_admin': wapp.is_admin,
		'VERSION': st.VERSION
	}

@wapp.app.after_request
def after_request_events(response):
	flask.g.requestData = {
		'addr': flask.request.remote_addr,
		'method': flask.request.method,
		'url': flask.request.url,
		'status': response.status_code
	}
	return response

@wapp.app.teardown_request
def teardown_request_events(error):
	if isinstance(error, SystemExit):
		return
	weblogging.log_completed_request()
	if error is not None:
		weblogging.log_unhandled_error(error)


# Error handlers

@wapp.app.errorhandler(400)
def web_error_400(error):
	logger.logerr('400 error - %s: %s' % (error.__class__.__name__, str(error)))
	with contextlib.suppress(Exception):
		logger.log_traceback('ERROR', error)
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': '400 Bad Request'
		}), 400
	return flask.render_template('error/http_status.html', code=400), 400 

@wapp.app.errorhandler(403)
def web_error_403(error):
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': '403 Forbidden'
		}), 403
	return flask.render_template('error/http_status.html', code=403), 403 

@wapp.app.errorhandler(404)
def web_error_404(error):
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': '404 Resource not found'
		}), 404
	return flask.render_template('error/http_status.html', code=404), 404 

@wapp.app.errorhandler(413)
def web_error_413(error):
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': '413 Too large'
		}), 413
	return flask.render_template('error/http_status.html', code=413), 413

@wapp.app.errorhandler(InvalidURL)
def web_error_InvalidUrl(error):
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': 'Invalid URL'
		}), 404
	return flask.render_template('error/invalid_url.html'), 404

@wapp.app.errorhandler(st.RateLimitExceeded)
def web_error_RateLimitExceeded(error):
	logger.logwrn('%s - rate limit exceeded' % flask.request.remote_addr)
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': 'Rate limit exceeded. Try again later.'
		}), 429
	return 'Rate limit exceeded', 429

@wapp.app.errorhandler(st.AddressBlocked)
def web_error_AddressBlocked(error):
	logger.logwrn('%s - ip blocked' % flask.request.remote_addr)
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': 'Your IP address is blocked. Contact the website operator for more information.'
		}), 403
	return 'Your IP address is blocked.', 403

@wapp.app.errorhandler(Exception)
def web_error_internal(error):
	if isinstance(error, HTTPException):
		return error
	lines = weblogging.log_request_error(error)
	if weblogging.is_json_request():
		return flask.jsonify({
			'error': 'Internal server error'
		}), 500
	return flask.render_template('error/http_status.html', code=500, lines=lines), 500


