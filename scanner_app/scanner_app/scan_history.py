"""Append-only snapshots written in the same transaction as scanner submissions."""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


def record_history(doc, operation, details, source_doctype=None, source_name=None):
	log = frappe.get_doc({
		"doctype": "Scanner Scan History",
		"recorded_at": now_datetime(),
		"scanned_by": frappe.session.user,
		"company": doc.company,
		"operation": operation,
		"reference_doctype": doc.doctype,
		"reference_name": doc.name,
		"source_doctype": source_doctype or None,
		"source_name": source_name or None,
		"details": json.dumps(details, ensure_ascii=False),
	})
	log.flags.from_scanner = True
	log.insert(ignore_permissions=True)
	return log.name


def record_stock_history(doc, scans, source_doctype=None, source_name=None):
	# Item/quantity/racks come from the validated document, not browser display data.
	details = []
	for row, scan in zip(doc.items, scans, strict=True):
		details.append({
			"item_code": row.item_code, "batch_no": row.batch_no,
			"serial_no": row.serial_no, "qty": row.qty, "uom": row.uom,
			"stock_qty": flt(row.qty) * flt(row.conversion_factor), "stock_uom": row.stock_uom,
			"source_warehouse": row.s_warehouse, "target_warehouse": row.t_warehouse,
			"qr_values": scan.get("qr_values") or [],
			"barcode": row.barcode,
		})
	return record_history(doc, doc.purpose, details, source_doctype, source_name)


@frappe.whitelist(methods=["GET"])
def get_history(start=0, search="", activity="", scope="mine"):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view scanner history."), frappe.PermissionError)
	start = max(0, min(cint(start), 1000000))
	search = str(search or "").strip()[:100]
	can_view_all = "System Manager" in frappe.get_roles()
	filters = {}
	if scope != "all" or not can_view_all:
		filters["scanned_by"] = frappe.session.user
	if activity:
		if activity not in ("Stock Entry", "Pick List", "Delivery Note"):
			frappe.throw(_("Invalid scanner activity."))
		filters["reference_doctype"] = activity
	or_filters = None
	if search:
		pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
		or_filters = {field: ["like", pattern] for field in ("reference_name", "source_name", "details")}
	rows = frappe.get_all("Scanner Scan History", filters=filters, or_filters=or_filters,
		fields=["name", "recorded_at", "scanned_by", "company", "operation", "reference_doctype",
			"reference_name", "source_doctype", "source_name", "details"],
		order_by="recorded_at desc, creation desc, name desc", start=start, page_length=21)
	result = []
	for row in rows[:20]:
		# Even a user's own history must respect current access to the document.
		if not frappe.has_permission(row.reference_doctype, "read", doc=row.reference_name):
			continue
		row.details = json.loads(row.details)
		result.append(row)
	return {"rows": result, "has_more": len(rows) > 20, "next_start": start + 20, "can_view_all": can_view_all}
