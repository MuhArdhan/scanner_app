"""
Context for the Scan Delivery Note PWA page.
Serves as a standalone full-page app (no Frappe web wrapper).
"""

no_cache = 1

def get_context(context):
	# Allow access even for guests – the page itself handles auth via JS
	context.no_breadcrumbs = 1
	context.no_header = 1
	context.no_footer = 1
	context.no_sidebar = 1
	context.show_sidebar = 0
	context.no_cache = 1
