const HTTP_STATUS_CODES = {
	200 : 'OK',
	201 : 'Created',
	202 : 'Accepted',
	203 : 'Non-Authoritative Information',
	204: 'No Content',
	205: 'Reset Content',
	206: 'Partial Content',
	300: 'Multiple Choices',
	301: 'Moved Permanently',
	302: 'Found',
	303: 'See Other',
	304: 'Not Modified',
	305: 'Use Proxy',
	307: 'Temporary Redirect',
	400: 'Bad Request',
	401: 'Unauthorized',
	402: 'Payment Required',
	403: 'Forbidden',
	404: 'Not Found',
	405: 'Method Not Allowed',
	406: 'Not Acceptable',
	407: 'Proxy Authentication Required',
	408: 'Request Timeout',
	409: 'Conflict',
	410: 'Gone',
	411: 'Length Required',
	412: 'Precondition Failed',
	413: 'Request Entity Too Large',
	414: 'Request-URI Too Long',
	415: 'Unsupported Media Type',
	416: 'Requested Range Not Satisfiable',
	417: 'Expectation Failed',
	500: 'Internal Server Error',
	501: 'Not Implemented',
	502: 'Bad Gateway',
	503: 'Service Unavailable',
	504: 'Gateway Timeout',
	505: 'HTTP Version Not Supported'
};

var toastTimer = null;


function serializeObjToParam(obj) {
	var str = [];
	for (var p in obj) {
		if (obj.hasOwnProperty(p)) {
			str.push(encodeURIComponent(p) + '=' + encodeURIComponent(obj[p]));
		}
	}
	return str.join('&');
}

function ajaxRequest(method, url, data, callback) {
	if (method == 'GET' && Object.keys(data).length > 0) {
		url += '?' + serializeObjToParam(data);
	}
	var form = new FormData();
	for (var key in data) {
		form.append(key, data[key]);
	}
	var xhr = new XMLHttpRequest();
	xhr.onreadystatechange = function () {
		if (this.readyState == 4) {
			try {
				var result = JSON.parse(this.responseText);
			} catch (e) {
				if (e.name == 'SyntaxError' && this.status != 0) {
					showToast(this.status + ' ' + HTTP_STATUS_CODES[this.status], 'warning');
				}
				return;
			}
			try {
				callback(result, this.status);
			} catch (e) {
				showToast('Error in application', 'warning');
				throw (e);
			}
		}
	};
	xhr.ontimeout = function () {
		showToast('Request timed out', 'warning');
	};
	xhr.onerror = function () {
		showToast('A network error occured', 'warning');
	};
	xhr.open(method, url, true);
	xhr.send(form);
}

function isLoggedInAsAdmin() {
	return Boolean(document.querySelector('html').getAttribute('data-isadmin') * 1);
}

// Toast

const TOAST_ICON_SPRITES = {
	'info': '<i class="fa-solid fa-circle-info"></i>',
	'warning': '<i class="fa-solid fa-triangle-exclamation"></i>',
	'error': '<i class="fa-solid fa-circle-exclamation"></i>'
};

function showToast(message, type) {
	if (typeof type == 'undefined') type = 'info';
	var toast = document.getElementById('toast');
	toast.setAttribute('data-type', type);
	toast.querySelector('.sprite-container').innerHTML = TOAST_ICON_SPRITES[type];
	toast.querySelector('.text').innerText = message;
	toast.classList.add('show');
	console.log('[' + type.toUpperCase() + '] ' + message);
	if (toastTimer != null) clearTimeout(toastTimer);
	toastTimer = setTimeout(function () {
		toast.className = '';
		toastTimer = null;
	}, 5000);
}


// Modal

var savedScrollPos = [0, 0];

function disableScrolling() {
	savedScrollPos = [window.scrollX, window.scrollY];
	body = document.getElementsByTagName('body')[0];
	body.style = 'overflow: hidden;';
}

function enableScrolling() {
	body = document.getElementsByTagName('body')[0];
	body.style = '';
	window.scrollTo(savedScrollPos[0], savedScrollPos[1]);
}

function modalOpen(allowScrolling) {
	var modal = document.getElementById('modal');
	if (typeof allowScrolling == 'undefined') allowScrolling = false;
	modal.style.display = 'block';
	if (!allowScrolling) disableScrolling();
}

function modalClose() {
	var modal = document.getElementById('modal');
	modal.style.display = 'none';
	enableScrolling();
}

function modalPrepare(title, modalType, content, modalStyle) {
	if (typeof modalType == 'undefined') modalType = '';
	if (typeof modalType == 'undefined') modalStyle = 'default';
	var modal = document.getElementById('modal');
	modal.setAttribute('data-type', modalType);
	modal.setAttribute('data-style', modalStyle);
	modal.style = '';
	modal.querySelector('#modal-back').classList.add('hide');
	modal.querySelector('#modal-title').innerText = title;
	var main = modal.querySelector('#modal-content');
	main.style = '';
	main.innerHTML = '';
	if (content) main.innerHTML = content;
	return main;
}



//Helpers

const GREGORIAN_YEAR = 31556952;

function timeAgo(epochTimeStamp) {
	var curDate = new Date();
	var difference = curDate.getTime() / 1000 - epochTimeStamp;
	if (difference < 10) {
		return 'just now';
	} else if (difference < 60) {
		return Math.floor(difference) + ' seconds ago';
	} else if (difference < 60 * 60) {
		var minutes = Math.floor(difference / 60);
		return minutes + ' minute' + (minutes == 1 ? '' : 's') + ' ago';
	} else if (difference < 60 * 60 * 24) {
		var hours = Math.floor(difference / (60 * 60));
		return hours + ' hour' + (hours == 1 ? '' : 's') + ' ago';
	} else if (difference < GREGORIAN_YEAR / 12) {
		var days = Math.floor(difference / (60 * 60 * 24));
		return days + ' day' + (days == 1 ? '' : 's') + ' ago';
	} else if (difference < GREGORIAN_YEAR) {
		var months = Math.floor(difference / (GREGORIAN_YEAR / 12));
		return months + ' month' + (months == 1 ? '' : 's') + ' ago';
	} else {
		var years = Math.floor(difference / GREGORIAN_YEAR);
		return years + ' year' + (years == 1 ? '' : 's') + ' ago';
	}
}

function updateTimeAgoValues() {
	var elements = document.getElementsByClassName('timeago');
	for (var i = 0; i < elements.length; i++) {
		elements[i].innerText = timeAgo(elements[i].getAttribute('data-timestamp') * 1);
	}
}

function zeroPad(num, len) {
	return num.toString().padStart(len, '0');
}

function isoTimeFromMs(timestamp) {
	var d = new Date(timestamp);
	return d.getFullYear() + '-' +
		   zeroPad(d.getMonth(), 2) + '-' +
		   zeroPad(d.getDate(), 2) + ' ' +
		   zeroPad(d.getHours(), 2) + ':' +
		   zeroPad(d.getMinutes(), 2) + ':' +
		   zeroPad(d.getSeconds(), 2);
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHTML(str) {
	var p = document.createElement("p");
	p.appendChild(document.createTextNode(str));
	return p.innerHTML;
}

function convertHTMLIntoText(element) {
	function convertElement(element) {
		switch(element.tagName) {
			case "BR": 
				return "\n";
			case "P":
			case "DIV": 
				return (element.previousSibling ? "\n" : "") 
					+ [].map.call(element.childNodes, convertElement).join("");
			default: 
				return element.textContent.replace(/\u00a0/igm, ' ').replace(/\n/igm, '');
		}
	};
	
	return [].map.call(element.childNodes, convertElement).join("");
}


//OnLoad


function getCurTheme() {
	try {
		var theme = localStorage.getItem('theme');
		return theme == null ? 'dark': theme;
	} catch (e) {}
}

function toggleTheme() {
	try {
		localStorage.setItem('theme', getCurTheme() == 'light' ? 'dark' : 'light');
		document.querySelector('html').setAttribute('data-theme', getCurTheme());
	} catch (e) {}
}

function submitURLForm(event) {
	event.preventDefault();
	var form = event.target;
	var url = form.querySelector('#url-box').value;
	if (url) {
		ajaxRequest('GET', '/ajax/parseurl.json', {
			'url': url
		}, function (response, code) {
			if ('error' in response) {
				showToast(response.error, 'error');
			} else {
				window.location = response.normalized_path;
			}
		});
	}
}


document.addEventListener('DOMContentLoaded', function () {
	document.getElementById('btn-toggletheme').onclick = toggleTheme;
	document.getElementById('url-form').onsubmit = submitURLForm;
	document.querySelector('html').setAttribute('data-theme', getCurTheme());
	setInterval(updateTimeAgoValues, 20000);
});