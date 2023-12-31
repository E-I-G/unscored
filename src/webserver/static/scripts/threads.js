const html = (strings, ...values) => String.raw({ raw: strings }, ...values);

function dispError(error) {
	document.getElementById('spinner').hidden = true;
	document.getElementById('error-container').hidden = false;
	document.getElementById('error-message').innerText = error;
}

function dispLoadingSpinner() {
	if (document.getElementById('error-container')) {
		document.getElementById('error-container').hidden = true;
	}
	if (document.getElementById('thread')) {
		document.getElementById('thread').hidden = true;
	}
	document.getElementById('spinner').hidden = false;
}

function hideLoadingSpinner() {
	document.getElementById('spinner').hidden = true;
	if (document.getElementById('error-container') != null) {
		document.getElementById('error-container').hidden = true;
	}
	if (document.getElementById('status-container') != null) {
		document.getElementById('status-container').hidden = true;
	}
	if (document.getElementById('thread') != null) {
		document.getElementById('thread').hidden = false;
	}
	if (document.getElementById('feed') != null) {
		document.getElementById('feed').hidden = false;
	}
	if (document.getElementById('profile') != null) {
		document.getElementById('profile').hidden = false;
	}
	if (document.getElementById('communities') != null) {
		document.getElementById('communities').hidden = false;
	}
	if (document.getElementById('modlog') != null) {
		document.getElementById('modlog').hidden = false;
	}
}



//Markdown and linkify

const LINK_REGEX = /(?:http|https):\/\/((?:[a-z0-9-]+\.)+[a-z0-9\-]{2,})(\/[-a-zA-Z0-9@:%._\\+~#?&/\(\)=*]*)?|\b[cu]\/\w+/igm;

function linkify(element, ignoreLines) {
	if (typeof (ignoreLines) == 'undefined') ignoreLines = false;

	function linkifyInnerText(node) {
		var text = node.innerText;
		var matches = node.innerText.match(LINK_REGEX);
		var parts = [];
		if (matches == null) return;
		for (var i = 0; i < matches.length; i++) {
			var match = matches[i];
			var before = text.substring(0, text.search(escapeRegExp(matches[i])));
			if (before) parts.push(escapeHTML(before));
			if (match.startsWith('u/') || match.startsWith('c/')) {
				parts.push('<a href="https://scored.co/' + match + '" target="_blank">' + match + '</a>');
			} else {
				parts.push('<a href="' + match + '" target="_blank">' + match + '</a>');
			}
			text = text.substring(match.length + before.length);
		}
		if (text) parts.push(escapeHTML(text));
		node.innerHTML = parts.join('');
	}
	
	for (var i = 0; i < element.childNodes.length; i++) {
		var node = element.childNodes[i];
		if (node.nodeType == Node.TEXT_NODE && node.textContent && node.textContent.match(LINK_REGEX)) {
			if (!ignoreLines || node.textContent.trim() != '') {
				var replacementNode = document.createElement('span');
				replacementNode.innerText = node.textContent;
				linkifyInnerText(replacementNode);
				node.replaceWith(replacementNode);
			}
		} else if (['STRONG', 'EM', 'B', 'I'].includes(node.nodeName)) {
			linkifyInnerText(node);
		} else if (['BLOCKQUOTE', 'CODE', 'P', 'LI', 'OL', 'UL'].includes(node.nodeName)) {
			linkify(node, ignoreLines);
		}
	}
}

function formatMarkdownElement(converter, el) {
	var elementText = convertHTMLIntoText(el);
	el.innerHTML = converter.makeHtml(elementText);
	linkify(el, true);
	el.classList.add('markdown-formatted');
}

function formatMarkdownElements(callback) {
	function recursiveFormat(i, elements) {
		console.log('markdown ' + i + '/' + elements.length);
		for (let count = 0; count < 25 && i < elements.length; i++, count++) {
			var el = elements[i];
			if (!(el.classList.contains('markdown-formatted'))) {
				formatMarkdownElement(converter, el);
			}
		}
		if (i < elements.length) {
			console.log('more')
			setTimeout(recursiveFormat, 100, i, elements);
		} else {
			console.log('done');
			if (typeof(callback) == 'function') {
				callback();
			}
		}
	}

	var converter = new showdown.Converter({
		extensions: ['htmlescape', 'xssfilter']
	});
	converter.setOption('openLinksInNewWindow', true);
	console.log('Formatting markdown');
	var elements = document.getElementsByClassName('markdown-required');
	recursiveFormat(0, elements);
}


//Image resize by dragging

var imageDragState = {
	dragging: false,
	imgWidth: 0,
	imgHeight: 0,
	delta: 0
};

function getImageDragSize(e) {
	var rect = e.target.getBoundingClientRect();
	return Math.pow(Math.pow(e.clientX - rect.left, 2) + Math.pow(e.clientY - rect.top, 2), .5);
}

function makeImageUserResizable(image) {
	image.style.cursor = 'grab';
	image.addEventListener('mousedown', function (e) {
		if (e.button != 0) return;
		e.preventDefault();
		imageDragState.imgWidth = e.target.width;
		imageDragState.imgHeight = e.target.height;
		imageDragState.dragging = true;
		imageDragState.delta = getImageDragSize(e);
		e.target.style.cursor = 'grabbing';
	}, true);
	image.addEventListener('mousemove', function (e) {
		if (!imageDragState.dragging || Math.abs(imageDragState.delta - getImageDragSize(e)) < 5) return;
		e.target.style.maxWidth = e.target.style.width = Math.floor(((getImageDragSize(e)) * imageDragState.imgWidth / imageDragState.delta)) + "px";
		e.target.style.maxHeight = 'unset';
		e.target.style.height = 'auto';
	}, false);

	image.addEventListener('mouseup', function (e) {
		if (!imageDragState.dragging) return;
		imageDragState.dragging = false;
		e.target.style.cursor = 'grab';
	}, true);

	image.addEventListener('mouseout', function (e) {
		if (!imageDragState.dragging) return;
		imageDragState.dragging = false;
		e.target.style.cursor = 'grab';
	}, true);
}


// Post and comment rendering

function findItemRoot(el) {
	while (!el.hasAttribute('data-itemtype')) {
		el = el.parentElement;
		if (el == null) return null;
	}
	return el;
}

function loadPostEmbedPreview(post, transitionEnabled) {
	function setAutoHeight() {
		setTimeout(function () { embed.style.height = 'auto'; }, transitionEnabled ? 500 : 0);
	}
	var isImage = Boolean(post.getAttribute('data-isimage') * 1);
	var hasText = Boolean(post.getAttribute('data-hastext') * 1);
	var embed = post.querySelector('.embed');
	var preview = post.querySelector('.embed .preview');
	var content = post.querySelector('.embed .content');
	if (embed == null) return;
	if (transitionEnabled) embed.classList.add('slide-transition');
	if (embed.getAttribute('data-expanded') * 1) {
		embed.style.height = '0px';
		embed.firstElementChild.innerHTML = '';
		embed.setAttribute('data-expanded', 0);
	} else {
		embed.style.height = '0px';
		embed.setAttribute('data-expanded', 1);
		if (isImage) {
			var img = document.createElement('img');
			img.src = post.getAttribute('data-link');
			img.onload = function () {
				embed.style.height = (embed.scrollHeight + 5) + 'px';
				makeImageUserResizable(img);
				setAutoHeight();
			};
			embed.firstElementChild.appendChild(img);
		}
		if (hasText) {
			var postTextEl = post.querySelector('.content');
			postTextEl.classList.add('markdown-required');
			formatMarkdownElements(function () {
				embed.style.height = (preview.scrollHeight + content.scrollHeight) + 'px';
				if (!isImage) setAutoHeight();
			});
		}
	}
}


function submitRemovalRequestForm(form, item) {
	var reason = form.querySelector('select[name="reason"]').value;
	var description = form.querySelector('textarea[name="description"]').value;
	var confirmation = form.querySelector('input[name="confirmation"]').checked;
	if (reason && description && confirmation) {
		ajaxRequest('POST', '/ajax/removal-request', {
			'type': item.getAttribute('data-itemtype'),
			'id': item.getAttribute('data-id') * 1,
			'reason': reason,
			'description': description
		}, function (response, code) {
			modalClose();
			if ('error' in response) {
				showToast(response.error, 'error');
			} else {
				showToast('Removal request sent');
			}
		})
	}
}


function renderItemAttributes(type, item, data) {
	var isThread = document.querySelector('main').getAttribute('data-disptype') == 'thread';
	item.setAttribute('data-itemtype', type);
	item.setAttribute('data-id', data.id);
	item.setAttribute('data-isimage', data.is_image * 1);
	item.setAttribute('data-hastext', Boolean(data.raw_content) * 1);
	item.setAttribute('data-archived', data.archive.is_archived * 1);
	item.setAttribute('data-deleted', data.is_deleted * 1);
	item.setAttribute('data-removed', data.is_removed * 1);
	item.setAttribute('data-filtered', data.is_filtered * 1);
	item.setAttribute('data-isadmin', data.is_admin * 1);
	item.setAttribute('data-ismoderator', data.is_moderator * 1);
	item.setAttribute('data-nsfw', data.is_nsfw * 1);
	item.setAttribute('data-link', data.link);
	var isRecovered = data.archive.recovery_method != null;

	if (type == 'post') {
		if (data.is_image || data.raw_content) {
			item.querySelector('.thumbnail').onclick = function (event) {
				event.stopImmediatePropagation();
				event.preventDefault();
				var post = findItemRoot(event.target);
				loadPostEmbedPreview(post, true);
			};
		} else if (data.link) {
			var thumb = item.querySelector('.thumbnail');
			var anchor = document.createElement('a');
			anchor.href = data.link;
			anchor.target = '_blank';
			anchor.innerHTML = thumb.outerHTML;
			thumb.replaceWith(anchor);
		}
		
		if (data.preview) {
			var thumbnail = document.createElement('img')
			thumbnail.src = data.preview;
			item.querySelector('.thumbnail').appendChild(thumbnail);
		}
		item.querySelector('.title-link').innerText = data.title;
		if (isThread && data.link) {
			item.querySelector('.title-link').href = data.link;
		} else {
			item.querySelector('.title-link').href = data.normalized_path;
		}
		if (!data.domain) {
			item.querySelector('.domain').hidden = true;
		}
		item.querySelector('.nsfw').hidden = !data.is_nsfw;
	} else if (type == 'comment') {
		if (isThread) {
			item.querySelector('.parent').remove();
		} else {
			item.querySelector('.threadName').innerText = data.post_title;
		}
		item.querySelector('.toggle').onclick = function () {
			this.parentElement.classList.toggle('collapsed');
		};
	}

	var distinguish = item.querySelector('.distinguish');
	if (data.is_moderator) {
		var dist = document.createElement('span');
		dist.className = 'moderator';
		dist.innerText = 'M';
		distinguish.appendChild(dist);
		distinguish.appendChild(document.createTextNode(','));
	}
	if (data.is_admin) {
		var dist = document.createElement('span');
		dist.className = 'admin';
		dist.innerText = 'A';
		distinguish.appendChild(dist);
		distinguish.appendChild(document.createTextNode(','));
	}
	if (distinguish.hasChildNodes()) {
		distinguish.removeChild(distinguish.lastChild);
	}

	if (data.raw_content) {
		item.querySelector('.content').innerText = data.raw_content;
		item.querySelector('.content').classList.add('markdown-required');
	}

	var attrsStatusDel = item.querySelector('.archive-attributes .status-deleted');
	if (data.is_deleted) {
		var icon = document.createElement('span');
		icon.className = 'icon deleted';
		icon.innerHTML = '<i class="fa-solid fa-trash"></i>';
		attrsStatusDel.appendChild(icon);
		attrsStatusDel.appendChild(document.createTextNode('Deleted by author'));
	}

	var attrsStatus = item.querySelector('.archive-attributes .status')
	if (data.is_removed) {
		var icon = document.createElement('span');
		icon.className = 'icon removed';
		if (data.removal_source.startsWith('nuke') || data.ban.is_nuked) {
			var message = 'Removed upon ban';
			icon.innerHTML = '<i class="fa-solid fa-explosion"></i>';
		} else if (data.removal_source.startsWith('communityFilter')) {
			var message = 'Removed by local community filter';
			icon.innerHTML = '<i class="fa-solid fa-filter"></i>';
		} else if (data.removal_source.startsWith('riskFilter')) {
			var message = 'User filtered for risk of posting political content';
			icon.innerHTML = '<i class="fa-solid fa-filter"></i>';
		} else if (data.removal_source.startsWith('spamFilter')) {
			var message = 'Removed by platform-wide filter';
			icon.innerHTML = '<i class="fa-solid fa-filter"></i>';
		} else if (data.removal_source == 'deleted') {
			var message = 'Removed before deletion';
			icon.innerHTML = '<i class="fa-solid fa-comment-slash"></i>';
		} else {
			var message = 'Removed';
			icon.innerHTML = '<i class="fa-solid fa-comment-slash"></i>';
		}
		attrsStatus.appendChild(icon);
		if (type == 'post' && !data.title || type == 'comment' && !data.raw_content) {
			message += ' before archival'
		}
		if (data.moderation.removed_by) {
			message += ' by ' + data.moderation.removed_by
		}
		var text = document.createElement('span');
		text.innerText = message;
		attrsStatus.appendChild(text);
		if (data.moderation.removed_at) {
			var time = document.createElement('span');
			time.className = 'timeago';
			time.title = isoTimeFromMs(data.moderation.removed_at);
			time.setAttribute('data-timestamp', Math.floor(data.moderation.removed_at / 1000));
			time.innerText = ' ' + timeAgo(data.moderation.removed_at / 1000);
			attrsStatus.appendChild(time);
		}
		if (data.removal_source && data.removal_source != 'deleted') {
			var text = document.createElement('i');
			text.innerText = '[' + data.removal_source + ']';
			attrsStatus.appendChild(text);
		}
	} else if (data.moderation.approved_at || isRecovered && !data.is_removed && !data.is_deleted) {
		var icon = document.createElement('span');
		icon.className = 'icon approved';
		icon.innerHTML = '<i class="fa-solid fa-check"></i>';
		attrsStatus.appendChild(icon);
		if (data.moderation.approved_at) {
			var message = 'Approved';
			if (data.moderation.approved_by) {
				message += ' by ' + data.moderation.approved_by;
			}
		} else {
			var message = 'Likely reinstated after being auto-removed';
		}
		var text = document.createElement('span');
		text.innerText = message;
		attrsStatus.appendChild(text);
		if (data.moderation.approved_at) {
			var time = document.createElement('span');
			time.className = 'timeago';
			time.title = isoTimeFromMs(data.moderation.approved_at);
			time.setAttribute('data-timestamp', Math.floor(data.moderation.approved_at / 1000));
			time.innerText = ' ' + timeAgo(data.moderation.approved_at / 1000);
			attrsStatus.appendChild(time);
		}
	}

	var attrsLocalBan = item.querySelector('.archive-attributes .local-ban');
	if (data.ban.is_banned) {
		var icon = document.createElement('span');
		icon.className = 'icon banned';
		icon.innerHTML = '<i class="fa-solid fa-gavel"></i>';
		attrsLocalBan.appendChild(icon);
		var text = document.createElement('span');
		text.innerText = 'Permanently banned from community';
		if (data.ban.banned_by) {
			text.innerText += ' by ' + data.ban.banned_by;
		}
		attrsLocalBan.appendChild(text);
		if (data.ban.ban_reason.trim()) {
			var reason = document.createElement('i');
			reason.innerText = '(' + data.ban.ban_reason.trim() + ')';
			attrsLocalBan.appendChild(reason);
		}
	}

	var attrsGlobalBan = item.querySelector('.archive-attributes .global-ban');
	if (data.ban.is_suspended) {
		var icon = document.createElement('span');
		icon.className = 'icon suspended';
		icon.innerHTML = '<i class="fa-solid fa-user-slash"></i>';
		attrsGlobalBan.appendChild(icon);
		attrsGlobalBan.appendChild(document.createTextNode('Globally suspended'));
	}

	var buttons = item.querySelector('.buttons');

	if (data.archive.legal_removed) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon archive-partial';
		icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><span class="tooltip">Flagged for illegal content</span>';
		buttons.appendChild(icon);
	} else if (data.archive.recovery_method == 'log' && (data.is_removed || data.is_deleted)) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon archive-partial';
		icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><span class="tooltip">Partially recovered from mod log</span>';
		buttons.appendChild(icon);
	} else if (data.archive.recovery_method == 'scrape' && (data.is_removed || data.is_deleted)) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon archive-partial';
		icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i><span class="tooltip">Recovered by scraping profile page</span>';
		buttons.appendChild(icon);
	} else if (data.archive.is_archived) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon archive-ok';
		icon.innerHTML = '<i class="fa-solid fa-cloud"></i><span class="tooltip">Archived</span>';
		buttons.appendChild(icon);
	} else if (data.archive.just_added) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon archive-ok';
		icon.innerHTML = '<i class="fa-solid fa-star-of-life"></i><span class="tooltip">Archived just now</span>';
		buttons.appendChild(icon);
	} else {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon unarchived';
		icon.innerHTML = '<i class="fa-solid fa-xmark"></i><span class="tooltip">Not archived</span>';
		buttons.appendChild(icon);
	}

	if (data.is_locked) {
		var icon = document.createElement('span');
		icon.className = 'tooltip-container right icon locked';
		icon.innerHTML = '<i class="fa-solid fa-lock"></i><span class="tooltip">Locked</span>';
		buttons.appendChild(icon);
	}

	if (type == 'post') {
		var a = document.createElement('a');
		a.className = 'link comments';
		a.href = data.normalized_path;
		a.innerText = data.comments + ' comments';
		buttons.appendChild(a);
	} else {
		var a = document.createElement('a');
		a.className = 'link';
		a.href = data.normalized_path;
		a.innerText = 'link';
		buttons.appendChild(a);
	}

	for (let i = 0; i < data.urls.length; i++) {
		let url = new URL(data.urls[i]);
		var a = document.createElement('a');
		a.className = 'link';
		a.innerText = url.hostname;
		a.target = '_blank';
		a.href = data.urls[i];
		buttons.appendChild(a);
	}

	if (data.archive.reportable) {
		var a = document.createElement('a');
		a.href = 'javascript:void(0);';
		a.className = 'link red';
		a.innerText = 'request removal';
		a.onclick = function () {
			var content = html`
				<form action="" class="report-form">
					<div class="reason">
						<select id="report-reason" name="reason" style="width: 100%;">
							<option value=""><i>Select reason...</i></option>
							<option value="illegal">Contains illegal content</option>
							<option value="dox">Contains personal information (doxing)</option>
							<option value="privacy">Privacy concerns</option>
						</select>
					</div>
					<div class="description">
						<textarea name="description" placeholder="Describe your issue"></textarea>
					</div>
					<div class="confirmation">
						<input type="checkbox" name="confirmation" id="reportmodal-confirm">
						<label for="reportmodal-confirm">I acknowledge that misuse of removal requests may get my IP blocked.</label>
					</div>
					<div class="submit">
						<input type="submit" value="Submit">
					</div>
				</form>
			`;
			var modal = modalPrepare('Request removal from archive', 'removal', content);
			modal.querySelector('.report-form').onsubmit = function (event) {
				event.preventDefault();
				var form = event.target;
				submitRemovalRequestForm(form, item);
			};
			modalOpen();
		};
		buttons.appendChild(a);
	}

	if (isLoggedInAsAdmin() && data.archive.is_archived) {
		var a = document.createElement('a');
		a.href = 'javascript:void(0);';
		a.className = 'link red';
		a.innerText = data.archive.legal_removed ? 'reremove' : 'remove';
		a.onclick = function () {
			ajaxRequest('POST', '/ajax/legal-remove-item', {
				'type': type,
				'id': data.id
			}, function (response, code) {
				showToast('Removed');
			});
		};
		buttons.appendChild(a);

		var a = document.createElement('a');
		a.href = 'javascript:void(0);';
		a.className = 'link green';
		a.innerText = data.archive.legal_approved ? 'reapprove' : 'approve';
		a.onclick = function () {
			ajaxRequest('POST', '/ajax/legal-approve-item', {
				'type': type,
				'id': data.id
			}, function (response, code) {
				showToast('Approved');
			});
		};
		buttons.appendChild(a);
	}
}


function renderPost(data) {
	var post = document.createElement('div');
	post.className = 'post';
	post.innerHTML = html`
		<div class="main">
			<div class="vote">
				<span>${data.score != null ? data.score : 'N/A'}</span>
			</div>
			<div class="thumbnail"></div>
			<div class="body">
				<div class="title">
					<a class="title-link"></a>
					<span class="domain">(${data.domain})</span>
					<span class="nsfw" title="Not Safe For Work" hidden>NSFW</span>
				</div>
				<div class="details">
					posted
					<span class="timeago"
						title=${isoTimeFromMs(data.created)}
						data-timestamp="${Math.floor(data.created / 1000)}"
						>${timeAgo(data.created / 1000)}</span>
					by <a class="author" href="/u/${data.author}">${data.author}</a>
					<span class="distinguish"></span>
					in <a class="community" href="/c/${data.community}">${data.community}</a>
					<span class="score-breakdown">
						(<span class="up">+${ data.score_up }</span>
						/
						<span class="down">-${ data.score_down }</span>)
					</span>
				</div>
				<div class="archive-attributes">
					<div class="status-deleted"></div>
					<div class="status"></div>
					<div class="local-ban"></div>
					<div class="global-ban"></div>
				</div>
				<div class="buttons"></div>
			</div>
		</div>
		<div class="embed" data-expanded="0">
			<div class="preview"></div>
			<div class="content"></div>
		</div>
	`;

	renderItemAttributes('post', post, data);
	return post;
}

function renderComment(data) {
	var comment = document.createElement('div');
	comment.className = 'comment';
	comment.innerHTML = html`
		<div class="parent">
			<a class="threadName" href="/c/${ data.community }/p/${ data.parent_uuid }"></a>
			<span>by</span>
			<a class="author" href="/u/${ data.post_author }">${ data.post_author }</a>
		</div>
		<a class="toggle" href="javascript:void(0);"></a>
		<div class="body">
			<div class="details">
				<a class="author" href="/u/${ data.author }">${ data.author }</a>
				<span class="score">${ data.score } points</span>
				<span class="timeago" title=${isoTimeFromMs(data.created)} data-timestamp="${Math.floor(data.created / 1000)}">${timeAgo(data.created / 1000)}</span>
				<span class="distinguish"></span>
				in <a class="community" href="/c/${data.community}">${data.community}</a>
				<span class="score-breakdown">
					(<span class="up">+${ data.score_up }</span>
					/
					<span class="down">-${ data.score_down }</span>)
				</span>
			</div>
			<div class="content"></div>
			<div class="archive-attributes">
				<div class="status-deleted"></div>
				<div class="status"></div>
				<div class="local-ban"></div>
				<div class="global-ban"></div>
			</div>
			<div class="buttons"></div>
		</div>
		<div class="children"></div>
	`;

	renderItemAttributes('comment', comment, data);
	return comment;
}



// Feed

function renderFeed(urlinfo, posts, has_more_entries) {
	console.log(urlinfo)
	document.getElementById('posts').innerHTML = '';
	document.getElementById('loading-text').innerText = 'Rendering content...';
	var countTotal = 0;
	var countRemoved = 0;
	var countDeleted = 0;
	for (let i = 0; i < posts.length; i++) {
		countTotal++;
		if (posts[i].is_removed) countRemoved++;
		if (posts[i].is_deleted) countDeleted++;
		console.log(posts[i])
		var rendered = renderPost(posts[i]);
		document.getElementById('posts').appendChild(rendered);
	}
	var removedPercent = countTotal > 0 ? Math.round((countRemoved / countTotal) * 100) : 0;
	var deletedPercent = countTotal > 0 ? Math.round((countDeleted / countTotal) * 100) : 0;
	document.getElementById('item-count').innerText = countTotal + ' post' + (countTotal != 1 ? 's' : '') + ' on page';
	document.getElementById('item-count-removed').innerText = countRemoved + ' removed (' + removedPercent + '%)';
	document.getElementById('item-count-deleted').innerText = countDeleted + ' deleted (' + deletedPercent + '%)';
	if (has_more_entries && posts.length > 0) {
		document.getElementById('nav-btns').hidden = false;
		document.getElementById('btn-nextpage').href = '?from=' + posts[posts.length - 1].uuid;
	} else {
		document.getElementById('nav-btns').hidden = true;
	}
	formatMarkdownElements(function () {
		hideLoadingSpinner();
	});
}

function onLoadFetchFeed(urlinfo) {
	document.getElementById('feed-community').innerText = '/c/' + urlinfo.community;
	document.getElementById('feed-community').href = '/c/' + urlinfo.community;
	document.getElementById('modlog-link').href = '/c/' + urlinfo.community + '/logs';
	document.getElementById('loading-text').innerText = 'Fetching feed...';
	ajaxRequest('GET', '/ajax/feed.json', {
		'community': urlinfo.community,
		'from': urlinfo.from_uuid
	}, function (response, code) {
		console.log(response)
		if ('error' in response) {
			dispError(response.error);
		} else {
			if (response.modlog_status == 'full') {
				document.getElementById('modlog-link').innerText = 'Mod log';
				document.getElementById('modlog-link').hidden = false;
			} else if (response.modlog_status == 'bans') {
				document.getElementById('modlog-link').innerText = 'Ban log';
				document.getElementById('modlog-link').hidden = false;
			} else {
				document.getElementById('modlog-link').hidden = true;
			}
			setTimeout(function () {
				renderFeed(urlinfo, response.posts, response.has_more_entries);
			}, 200);
		}
	});
}


// Thread

function renderThread(urlinfo, post, comments) {
	var countTotal = 0;
	var countDeleted = 0;
	var countRemoved = 0;
	var renderedComments = {};

	function sortComments(roots, sort) {
		if (sort == 'top') {
			roots.sort((a, b) => {
				return b.score - a.score;
			});
		} else if (sort == 'controversial') {
			roots.sort((a, b) => {
				return a.score - b.score;
			});
		} else if (sort == 'old') {
			roots.sort((a, b) => {
				return a.id - b.id;
			});
		} else {
			roots.sort((a, b) => {
				return b.id - a.id;
			});
		}
		for (let i = 0; i < roots.length; i++) {
			if (roots[i].children) {
				sortComments(roots[i].children, sort);
			}
		}
	}

	function finalize() {
		document.getElementById('loading-text').innerText = 'Formatting markdown...';
		if (urlinfo.comment_id) {
			document.querySelector('#single-thread').hidden = false;
		}
	
		var removedPercent = countTotal > 0 ? Math.round((countRemoved / countTotal) * 100) : 0;
		var deletedPercent = countTotal > 0 ? Math.round((countDeleted / countTotal) * 100) : 0;
		document.getElementById('item-count').innerText = countTotal + ' comment' + (countTotal != 1 ? 's' : '');
		document.getElementById('item-count-removed').innerText = countRemoved + ' removed (' + removedPercent + '%)';
		document.getElementById('item-count-deleted').innerText = countDeleted + ' deleted (' + deletedPercent + '%)';
	
		document.getElementById('sort').onchange = function () {
			urlinfo.sort = this.value;
			var newLocation = '?sort=' + this.value;
			console.log(newLocation);
			window.history.replaceState(null, '', newLocation);
			dispLoadingSpinner();
			setTimeout(function () {
				renderThread(urlinfo, post, comments);
			}, 250);
		};
	
		formatMarkdownElements(function () {
			if (post.raw_content) {
				loadPostEmbedPreview(renderedPost, false);
			}
			hideLoadingSpinner();
		});
	}

	function displayComments(container, roots) {
		document.getElementById('loading-text').innerText = 'Displaying comments';
		for (let i = 0; i < roots.length; i++) {
			container.appendChild(roots[i].rendered);
			if (roots[i].children.length > 0) {
				displayComments(roots[i].rendered.querySelector('.children'), roots[i].children);
			}
		}
	}

	function renderCommentSection(comments, i) {
		console.log('render comments ' + i + "/" + comments.length)
		var percent = Math.round(((i + 1) / comments.length) * 100)
		document.getElementById('loading-text').innerText = 'Rendering comments (' + percent + '%)';
		for (let count = 0; count < 50 && i < comments.length; i++, count++) {
			var comment = comments[i];
			var rc = {
				'id': comment.id,
				'score': comment.score,
				'rendered': renderComment(comment),
				'isRoot': !comment.comment_parent_id,
				'children': []
			};
			renderedComments[comment.id] = rc;
			if (comment.comment_parent_id in renderedComments) {
				renderedComments[comment.comment_parent_id].children.push(rc);
			}
			countTotal++;
			if (comment.is_deleted) countDeleted++;
			if (comment.is_removed) countRemoved++;
		}
		if (i < comments.length) {
			console.log('more')
			setTimeout(function () {
				renderCommentSection(comments, i);
			}, 250);
		} else {
			console.log('end')
			var roots = [];
			for (let id in renderedComments) {
				let rc = renderedComments[id];
				if (!urlinfo.comment_id && rc.isRoot || urlinfo.comment_id && rc.id == urlinfo.comment_id) {
					roots.push(rc);
				}
			}
			sortComments(roots, urlinfo.sort);
			displayComments(document.getElementById('comments'), roots);
			finalize();
		}
	}

	document.getElementById('post').innerHTML = '';
	document.getElementById('comments').innerHTML = '';
	document.getElementById('loading-text').innerText = 'Rendering content...';
	var renderedPost = renderPost(post);
	document.getElementById('post').appendChild(renderedPost);
	document.querySelector('#single-thread').hidden = true;
	document.querySelector('#single-thread a').href = post.normalized_path;

	renderCommentSection(comments, 0);
}

function onLoadFetchThread(urlinfo) {
	console.log('Fetching thread');
	document.getElementById('loading-text').innerText = 'Fetching thread...';
	document.getElementById('feed-community').innerText = '/c/' + urlinfo.community;
	document.getElementById('feed-community').href = '/c/' + urlinfo.community;
	document.getElementById('modlog-link').href = '/c/' + urlinfo.community + '/logs';
	ajaxRequest('GET', '/ajax/thread.json', {
		'post_id': urlinfo.post_id
	}, function (response, code) {
		console.log(response)
		if ('error' in response) {
			dispError(response.error);
		} else {
			if (response.modlog_status == 'full') {
				document.getElementById('modlog-link').innerText = 'Mod log';
				document.getElementById('modlog-link').hidden = false;
			} else if (response.modlog_status == 'bans') {
				document.getElementById('modlog-link').innerText = 'Ban log';
				document.getElementById('modlog-link').hidden = false;
			} else {
				document.getElementById('modlog-link').hidden = true;
			}
			setTimeout(function () {
				renderThread(urlinfo, response.post, response.comments);
			}, 200);
		}
	});
}


// Profile

function profileLoadMore(user, from_post, from_comment) {
	ajaxRequest('GET', '/ajax/profile.json', {
		'user': user,
		'type': 'removed',
		'from_post': from_post,
		'from_comment': from_comment
	}, function (response, code) {
		if ('error' in response) {
			dispError(response.error);
		} else {
			hideLoadingSpinner();
			for (let i = response.content.length - 1; i >= 0; i--) {
				var item = response.content[i];
				if ('title' in item) {
					var rendered = renderPost(item);
				} else {
					var rendered = renderComment(item);
				}
				document.getElementById('profile-content').appendChild(rendered);
			}
			if (response.upto) {
				var lastItemTime = Math.floor(response.upto / 1000);
				document.getElementById('loadmore-upto').innerText = 'Showing content up to ' + timeAgo(lastItemTime);
			}
			document.getElementById('loadmore-loading-container').hidden = true;
			document.getElementById('loadmore-btn-container').hidden = false;
			if (response.has_more_entries) {
				document.getElementById('btn-loadmore').onclick = function () {
					document.getElementById('loadmore-btn-container').hidden = true;
					document.getElementById('loadmore-loading-container').hidden = false;
					profileLoadMore(user, response.from_post, response.from_comment);
				};
			} else {
				document.getElementById('loadmore-upto').innerText = 'Reached the end.';
				if (document.getElementById('btn-loadmore') != null) {
					document.getElementById('btn-loadmore').remove();
				}
			}
			formatMarkdownElements();
		}
	});
}

function renderProfile(urlinfo, content, has_more_entries) {
	console.log(urlinfo)
	document.getElementById('profile-content').innerHTML = '';
	document.getElementById('loading-text').innerText = 'Rendering profile...';
	document.getElementById('nav-btns').hidden = false;
	for (let i = content.length - 1; i >= 0; i--) {
		if (urlinfo.content == 'post') {
			var rendered = renderPost(content[i]);
		} else {
			var rendered = renderComment(content[i]);
		}
		document.getElementById('profile-content').appendChild(rendered);
	}
	if (urlinfo.page > 1) {
		document.getElementById('btn-prevpage').style = '';
		document.getElementById('btn-prevpage').href = '?type=' + urlinfo.content + '&page=' + (urlinfo.page - 1);
	} else {
		document.getElementById('btn-prevpage').style = 'display: none;';
	}
	if (has_more_entries) {
		document.getElementById('btn-nextpage').style = '';
		document.getElementById('btn-nextpage').href = '?type=' + urlinfo.content + '&page=' + (urlinfo.page + 1);
	} else {
		document.getElementById('btn-nextpage').style = 'display: none;';
	}
	formatMarkdownElements(function () {
		hideLoadingSpinner();
	});
}

function onLoadFetchProfile(urlinfo) {
	document.getElementById('profile-username').innerText = '/u/' + urlinfo.user;
	if (urlinfo.content == 'removed') {
		document.getElementById('loading-text').innerText = 'Fetching removed content...';
		profileLoadMore(urlinfo.user, 0, 0);
	} else {
		document.getElementById('loading-text').innerText = 'Fetching profile...';
		ajaxRequest('GET', '/ajax/profile.json', {
			'user': urlinfo.user,
			'type': urlinfo.content,
			'page': urlinfo.page
		}, function (response, code) {
			console.log(response)
			if ('error' in response) {
				dispError(response.error);
			} else {
				setTimeout(function () {
					renderProfile(
						urlinfo,
						urlinfo.content == 'post' ? response.posts : response.comments,
						response.has_more_entries
					);
				}, 200);
			}
		});
	}
}



// Communities

function renderCommunity(data) {
	var community = document.createElement('div');
	community.className = 'community';
	community.setAttribute('data-visibility', data.visibility);
	community.innerHTML = html`
		<div class="left">
			<a href="/c/${ data.name }">
				<div class="icon-circle"></div>
			</a>
		</div>
		<div class="right">
			<div class="name">
				<a href="/c/${ data.name }">
					/c/${ data.name }
				</a>
			</div>
			<div class="description"></div>
			<div class="status"></div>
			<div class="debug">
				<span>Modlog: ${ data.modlog_status }</span>
				<br>
				<span>Interval: <span title="${ data.interval }">${ timeDuration(data.interval) }</span></span>
				<br>
				<span>Last ingest: <span title="${ isoTimeFromMs(data.last_ingested * 1000) }"></span>${ timeAgo(data.last_ingested) }</span>
			</div>
		</div>
	`;
	if (data.has_icon) {
		var icon = document.createElement('img');
		icon.src = 'https://img.scored.co/community/' + data.name.toLowerCase() + '-icon-32x32.png';
		community.querySelector('.icon-circle').appendChild(icon);
	}
	if (data.visibility == 'unlisted') {
		var span = document.createElement('span');
		span.className = 'status-unlisted';
		span.innerText = 'unlisted';
		community.querySelector('.status').appendChild(span);
	}
	if (data.visibility == 'restricted') {
		var span = document.createElement('span');
		span.className = 'status-restricted';
		span.innerText = 'restricted';
		community.querySelector('.status').appendChild(span);
	}
	if (!data.app_safe) {
		var span = document.createElement('span');
		span.className = 'status-notappsafe';
		span.innerText = 'hidden from app';
		community.querySelector('.status').appendChild(span);
	}
	community.querySelector('.description').innerText = data.description;
	return community;
}

function renderCommunityList(urlinfo, content, has_more_entries) {
	var countTotal = 0;
	var countRestricted = 0;
	var countUnlisted = 0;
	var countAppUnsafe = 0;
	
	console.log(urlinfo)
	document.getElementById('communities-content').innerHTML = '';
	document.getElementById('loading-text').innerText = 'Rendering community list...';
	document.getElementById('nav-btns').hidden = false;
	for (let i = 0; i < content.length; i++) {
		document.getElementById('communities-content').appendChild(renderCommunity(content[i]));
		countTotal++;
		if (content[i].visibility == 'unlisted') countUnlisted++;
		if (content[i].visibility == 'restricted') countRestricted++;
		if (!content[i].app_safe) countAppUnsafe++;
	}
	var unlistedPercent = countTotal > 0 ? Math.round((countUnlisted / countTotal) * 100) : 0;
	var restrictedPercent = countTotal > 0 ? Math.round((countRestricted / countTotal) * 100) : 0;
	var appUnsafePercent = countTotal > 0 ? Math.round((countAppUnsafe / countTotal) * 100) : 0;
	document.getElementById('item-count').innerText = countTotal + ' communities on page';
	document.getElementById('item-count-restricted').innerText = countRestricted + ' restricted (' + restrictedPercent + '%)';
	document.getElementById('item-count-removed').innerText = countUnlisted + ' unlisted or closed (' + unlistedPercent + '%)';
	document.getElementById('item-count-hidden').innerText = countAppUnsafe + ' not app-safe (' + appUnsafePercent + '%)';
	if (urlinfo.page > 1) {
		document.getElementById('btn-prevpage').style = '';
		document.getElementById('btn-prevpage').href = '?sort=' + urlinfo.sort + '&page=' + (urlinfo.page - 1);
	} else {
		document.getElementById('btn-prevpage').style = 'display: none;';
	}
	if (has_more_entries) {
		document.getElementById('btn-nextpage').style = '';
		document.getElementById('btn-nextpage').href = '?sort=' + urlinfo.sort + '&page=' + (urlinfo.page + 1);
	} else {
		document.getElementById('btn-nextpage').style = 'display: none;';
	}
	hideLoadingSpinner();
}

function onLoadFetchCommunities(urlinfo) {
	document.getElementById('loading-text').innerText = 'Fetching communities...';
	ajaxRequest('GET', '/ajax/communities.json', {
		'sort': urlinfo.sort,
		'page': urlinfo.page
	}, function (response, code) {
		console.log(response)
		if ('error' in response) {
			dispError(response.error);
		} else {
			setTimeout(function () {
				renderCommunityList(urlinfo, response.communities, response.has_more_entries);
			}, 200);
		}
	});
}




// Mod log

const ACTION_DESCRIPTIONS = {
	'removepost': 'removed post',
	'approvepost': 'approved post',
	'removecomment': 'removed comment',
	'approvecomment': 'approved comment',
	'lockpost': 'locked post',
	'unlockpost': 'unlocked post',
	'ignoreposts': 'ignored reports on post',
	'ignorecomments': 'ignored reports on comment',
	'addmoderator': 'added moderator',
	'removemoderator': 'removed moderator',
	'ban': 'banned user',
	'unban': 'unbanned user',
};

function renderModlogRecord(community, data) {
	var record = document.createElement('div');
	record.className = 'modlog-record';
	var r_time = document.createElement('span');
	r_time.className = 'timeago';
	r_time.setAttribute('data-timestamp', Math.floor(data.created_ms / 1000));
	r_time.title = isoTimeFromMs(data.created_ms);
	r_time.innerText = timeAgo(Math.floor(data.created_ms / 1000));
	record.appendChild(r_time);
	record.appendChild(document.createTextNode(' '));
	if (data.moderator) {
		var r_mod = document.createElement('a');
		r_mod.href = '/u/' + data.moderator;
		r_mod.target = '_blank';
	} else {
		var r_mod = document.createElement('span');
	}
	r_mod.className = 'moderator';
	r_mod.innerText = data.moderator;
	record.appendChild(r_mod);
	record.appendChild(document.createTextNode(' '));
	var r_action = document.createElement('span');
	r_action.className = 'action';
	r_action.innerText = data.type in ACTION_DESCRIPTIONS ? ACTION_DESCRIPTIONS[data.type] : data.type;
	record.appendChild(r_action);
	if (data.post_id) {
		record.appendChild(document.createTextNode(' by '));
	} else {
		record.appendChild(document.createTextNode(' '));
	}
	var r_target = document.createElement('a');
	r_target.className = 'target';
	r_target.href = '/u/' + data.target + '?type=removed'
	r_target.target = '_blank';
	r_target.innerText = data.target;
	record.appendChild(r_target);
	record.appendChild(document.createTextNode(' - '));
	if (data.post_id) {
		var r_description = document.createElement('a');
		if (data.comment_id) {
			r_description.href = '/c/' + community + '/p/' + data.post_uuid + '/x/c/' + data.comment_uuid;
		} else {
			r_description.href = '/c/' + community + '/p/' + data.post_uuid;
		}
		r_description.target = '_blank';
	} else {
		var r_description = document.createElement('span');
	}
	r_description.className = 'description'
	if (data.description) {
		var desc = document.createElement('span');
		desc.innerText = data.description;
		r_description.appendChild(desc);
	} else if (data.post_id) {
		var desc = document.createElement('i');
		desc.innerText = 'link';
		r_description.appendChild(desc);
	}
	record.appendChild(r_description);
	var r_content = document.createElement('div');
	r_content.className = 'item-content';
	if (data.post_id) {
		r_content.innerHTML = '<a href="javascript:void(0);" class="btn-show">Show content</a>';
		r_content.querySelector('.btn-show').onclick = function () {
			r_content.querySelector('.btn-show').remove();
			if (data.comment_id) {
				ajaxRequest('GET', '/ajax/comment.json', {
					'post_id': data.post_id,
					'comment_id': data.comment_id
				}, function (response, code) {
					var comment = renderComment(response.comment);
					comment.querySelector('.parent').remove();
					r_content.appendChild(comment);
					r_content.classList.add('rendered');
				});
			} else {
				ajaxRequest('GET', '/ajax/post.json', {
					'post_id': data.post_id
				}, function (response, code) {
					r_content.appendChild(renderPost(response.post));
					r_content.classList.add('rendered');
				});
			}
			formatMarkdownElements();
		};
		record.appendChild(r_content);
	}
	return record;
}

function renderModlog(urlinfo, content, moderators, has_more_entries) {
	console.log(urlinfo)

	var modfilter = document.getElementById('filter-moderator');
	if (moderators == null) {
		modfilter.disabled = true;
	} else {
		var g_moderators = document.getElementById('filter-moderator-moderators');
		for (let i = 0; i < moderators.moderators.length; i++) {
			var opt = document.createElement('option');
			opt.value = moderators.moderators[i];
			opt.innerText = moderators.moderators[i];
			g_moderators.appendChild(opt);
		}
		var g_admins = document.getElementById('filter-moderator-admins');
		for (let i = 0; i < moderators.admins.length; i++) {
			var opt = document.createElement('option');
			opt.value = moderators.admins[i];
			opt.innerText = moderators.admins[i];
			g_admins.appendChild(opt);
		}
		var g_filters = document.getElementById('filter-moderator-filters');
		for (let i = 0; i < moderators.filters.length; i++) {
			var opt = document.createElement('option');
			opt.value = moderators.filters[i];
			opt.innerText = moderators.filters[i];
			g_filters.appendChild(opt);
		}
	}
	if (modfilter.querySelector('option[value="' + urlinfo.moderator + '"]')) {
		modfilter.querySelector('option[value="' + urlinfo.moderator + '"]').selected = true;
	}

	var actionfilter = document.getElementById('filter-action');
	if (actionfilter.querySelector('option[value="' + urlinfo.action + '"]')) {
		actionfilter.querySelector('option[value="' + urlinfo.action + '"]').selected = true;
	}

	var targetfilter = document.getElementById('filter-target');
	if (urlinfo.target && urlinfo.target != '*') {
		targetfilter.value = urlinfo.target;
	}

	for (let i = 0; i < content.length; i++) {
		document.getElementById('modlog-content').appendChild(
			renderModlogRecord(urlinfo.community, content[i])
		);
	}
	if (urlinfo.page > 1) {
		document.getElementById('btn-prevpage').style = '';
		document.getElementById('btn-prevpage').href = '?type=' + urlinfo.action + '&moderator=' + urlinfo.moderator + '&target=' + urlinfo.target + '&page=' + (urlinfo.page - 1);
	} else {
		document.getElementById('btn-prevpage').style = 'display: none;';
	}
	if (has_more_entries) {
		document.getElementById('btn-nextpage').style = '';
		document.getElementById('btn-nextpage').href = '?type=' + urlinfo.action + '&moderator=' + urlinfo.moderator + '&target=' + urlinfo.target + '&page=' + (urlinfo.page + 1);
	} else {
		document.getElementById('btn-nextpage').style = 'display: none;';
	}
	hideLoadingSpinner();
}

function onLoadFetchModlog(urlinfo) {
	document.getElementById('loading-text').innerText = 'Fetching mod log...';
	document.getElementById('feed-community').innerText = '/c/' + urlinfo.community;
	document.getElementById('feed-community').href = '/c/' + urlinfo.community;
	document.getElementById('modlog-link').href = '/c/' + urlinfo.community + '/logs';
	ajaxRequest('GET', '/ajax/logs.json', {
		'community': urlinfo.community,
		'page': urlinfo.page,
		'action': urlinfo.action,
		'moderator': urlinfo.moderator,
		'target': urlinfo.target
	}, function (response, code) {
		console.log(response)
		if ('error' in response) {
			dispError(response.error);
		} else {
			setTimeout(function () {
				renderModlog(urlinfo, response.records, response.moderators, response.has_more_entries);
			}, 200);
		}
	});
}



// OnLoad

function onLoadFetchURLInfo() {
	document.getElementById('loading-text').innerText = 'Fetching URL info...';
	ajaxRequest('GET', '/ajax/parseurl.json', {
		'url': window.location.pathname + window.location.search
	}, function (response, code) {
		if ('error' in response) {
			dispError(response.error);
		} else if (response.type == 'thread') {
			onLoadFetchThread(response);
		} else if (response.type == 'profile') {
			onLoadFetchProfile(response);
		} else if (response.type == 'feed') {
			onLoadFetchFeed(response);
		} else if (response.type == 'communities') {
			onLoadFetchCommunities(response);
		} else if (response.type == 'modlog') {
			onLoadFetchModlog(response);
		}
	});
}



window.onload = function () {
	showdown.setOption('ghCodeBlocks', true);
	showdown.setOption('tables', true);
	showdown.setOption('strikethrough', true);
	showdown.setOption('literalMidWordUnderscores', true);
	showdown.setOption('simpleLineBreaks', true);
	showdown.setOption('noHeaderId', true);
	console.log('Fetching url info');
	onLoadFetchURLInfo();
};