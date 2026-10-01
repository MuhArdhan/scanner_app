frappe.pages['delivery_note_scan'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Scan Delivery Note'),
		single_column: true,
	});

	const $main = $(wrapper).find('.layout-main');
	$main.html(`
		<div class="dns-root">
			<p class="text-muted dns-intro">
				${__('Scan the QR code on a Delivery Note when you reach its delivery stop.')}
			</p>
			<div class="dns-actions">
				<button class="btn btn-primary dns-camera">
					${__('Scan with Camera')}
				</button>
			</div>
			<div class="dns-manual">
				<label for="dns-delivery-note">${__('Or use a handheld scanner')}</label>
				<div class="dns-input-row">
					<input id="dns-delivery-note" class="form-control" type="text"
						placeholder="${__('Scan or enter Delivery Note ID')}" autocomplete="off" />
					<button class="btn btn-default dns-submit">${__('Mark Visited')}</button>
				</div>
			</div>
			<div class="dns-feedback text-muted" role="status" aria-live="polite"></div>
		</div>
	`);

	const $input = $main.find('#dns-delivery-note');
	const $submit = $main.find('.dns-submit');
	const $feedback = $main.find('.dns-feedback');
	let busy = false;

	function set_feedback(message, kind) {
		$feedback
			.removeClass('text-muted text-success text-danger')
			.addClass(kind === 'error' ? 'text-danger' : kind === 'success' ? 'text-success' : 'text-muted')
			.text(message || '');
	}

	function mark_visited(raw_value) {
		const delivery_note = String(raw_value || '').trim();
		if (!delivery_note || busy) return;

		busy = true;
		$submit.prop('disabled', true);
		set_feedback(__('Processing scan...'), 'muted');

		frappe.call({
			method: 'scanner_app.scanner_app.delivery_note_scan.mark_stop_visited',
			args: { delivery_note },
			type: 'POST',
			freeze: true,
			freeze_message: __('Updating delivery stop...'),
		}).then(
			(r) => {
				const result = r.message || {};
				const message = result.already_visited
					? __('Already visited: {0} · {1} · {2}', [result.customer, result.trip, result.trip_status])
					: __('Stop marked visited: {0} · {1} · {2}', [result.customer, result.trip, result.trip_status]);
				set_feedback(message, 'success');
				$input.val('').trigger('focus');
				busy = false;
				$submit.prop('disabled', false);
			},
			() => {
				set_feedback(__('Could not update this stop. Check the error message and try again.'), 'error');
				busy = false;
				$submit.prop('disabled', false);
			}
		);
	}

	$main.on('click', '.dns-camera', () => {
		new frappe.ui.Scanner({
			dialog: true,
			multiple: false,
			on_scan(data) {
				const value = data && data.result && data.result.text;
				if (value) {
					$input.val(value);
					mark_visited(value);
				}
			},
		});
	});

	$submit.on('click', () => mark_visited($input.val()));
	$input.on('keydown', (event) => {
		if (event.key === 'Enter') {
			event.preventDefault();
			mark_visited($input.val());
		}
	});
};
