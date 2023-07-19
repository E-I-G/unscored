function submitBlockIPForm(event) {
	event.preventDefault();
	var form = event.target;
	var ip = form.querySelector('input[name="ip"]').value;
	ajaxRequest('POST', '/ajax/block-ip', {
		'ip': ip
	}, function (response, code) {
		form.querySelector('input[name="ip"]').value = '';
		showToast('Address blocked');
	});
}

function submitUnblockIPForm(event) {
	event.preventDefault();
	var form = event.target;
	var ip = form.querySelector('input[name="ip"]').value;
	ajaxRequest('POST', '/ajax/unblock-ip', {
		'ip': ip
	}, function (response, code) {
		form.querySelector('input[name="ip"]').value = '';
		showToast('Address unblocked');
	});
}