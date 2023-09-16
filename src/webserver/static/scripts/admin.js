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


function sendDbQuery() {
	var query = document.getElementById('db-query').value;
	ajaxRequest('POST', '/ajax/db-query', {
		query: query
	}, function (response, code) {
		var div = document.getElementById('db-response');
		div.innerHTML = '';
		var input = document.createElement('div');
		input.className = 'input';
		input.innerText = query;
		div.appendChild(input);
		if (response.data && response.data.length > 0) {
			var tableContainer = document.createElement('div');
			var table = document.createElement('table');
			var tbody = document.createElement('tbody');
			var row = document.createElement('tr');
			for (var i = 0; i < response.fields.length; i++) {
				var cell = document.createElement('th');
				cell.innerText = response.fields[i];
				row.appendChild(cell);
			}
			tbody.appendChild(row);
			for (var i = 0; i < response.data.length; i++) {
				var rowData = response.data[i];
				var row = document.createElement('tr');
				for (var j = 0; j < rowData.length; j++) {
					var cell = document.createElement('td');
					cell.innerText = rowData[j];
					row.appendChild(cell);
				}
				tbody.appendChild(row);
			}
			table.appendChild(tbody);
			tableContainer.appendChild(table);
			div.appendChild(tableContainer);
		}
		if (response.statusmessage) {
			var statusmessage = document.createElement('div');
			statusmessage.innerText = response.statusmessage;
			div.appendChild(statusmessage);
		}
		if (response.rowcount && response.rowcount > 0) {
			var rowcount = document.createElement('div');
			rowcount.innerText = response.rowcount + ' rows affected';
			div.appendChild(rowcount);
		}
		if (response.error) {
			var error = document.createElement('div');
			error.className = 'error';
			error.innerText = response.error;
			div.appendChild(error);
		}
	})
}