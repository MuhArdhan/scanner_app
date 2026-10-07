"""Keep the Scanner App Desk entry in sync after install and migrate."""

import frappe


SIDEBAR = "Scanner App"
ITEMS = [
	{"label": "Scanner App", "link_to": "Scanner App", "link_type": "Workspace", "type": "Link", "icon": "scan-barcode", "idx": 1},
	{"label": "Scanner PWA", "url": "/scanner/", "link_type": "URL", "type": "Link", "icon": "scan-barcode", "idx": 2},
]


def apply():
	if not frappe.db.exists("Workspace Sidebar", SIDEBAR):
		frappe.get_doc({
			"doctype": "Workspace Sidebar",
			"title": SIDEBAR,
			"header_icon": "scan-barcode",
			"app": "scanner_app",
			"standard": 1,
			"items": [dict(item, doctype="Workspace Sidebar Item") for item in ITEMS],
		}).insert(ignore_permissions=True)
	else:
		sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR)
		if sidebar.app == "scanner_app" and sidebar.standard:
			current = [
				{key: row.get(key) for key in item}
				for item, row in zip(ITEMS, sorted(sidebar.items, key=lambda row: row.idx or 0), strict=False)
			]
			if len(sidebar.items) != len(ITEMS) or current != ITEMS or sidebar.header_icon != "scan-barcode":
				sidebar.header_icon = "scan-barcode"
				sidebar.set("items", [dict(item, doctype="Workspace Sidebar Item") for item in ITEMS])
				sidebar.save(ignore_permissions=True)

	if not frappe.db.exists("Desktop Icon", {"label": SIDEBAR}):
		frappe.get_doc({
			"doctype": "Desktop Icon",
			"label": SIDEBAR,
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": SIDEBAR,
			"icon": "scan-barcode",
			"standard": 0,
			"app": "scanner_app",
		}).insert(ignore_permissions=True)
