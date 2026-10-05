"""Standalone scanner PWA."""

no_cache = 1


def get_context(context):
	context.no_breadcrumbs = 1
	context.no_header = 1
	context.no_footer = 1
	context.no_sidebar = 1
	context.show_sidebar = 0
	context.no_cache = 1
