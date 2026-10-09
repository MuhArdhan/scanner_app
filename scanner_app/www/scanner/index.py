"""Standalone scanner PWA."""

import hashlib
from pathlib import Path

import frappe

no_cache = 1


def get_context(context):
	context.no_breadcrumbs = 1
	context.no_header = 1
	context.no_footer = 1
	context.no_sidebar = 1
	context.show_sidebar = 0
	context.no_cache = 1
	# Static assets may stay cached on mobile despite clearing the Frappe cache.
	# Change their URLs whenever the actual source changes, without deleting scans.
	for field, filename in (("packing_layout_version", "packing.js"), ("packing_qz_version", "remote-qz.js")):
		content = Path(frappe.get_app_path("scanner_app", "public", filename)).read_bytes()
		context[field] = hashlib.sha256(content).hexdigest()[:12]
