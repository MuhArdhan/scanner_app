"""Scan an existing draft Pick List and submit that same document."""

import json
import math

import frappe
from frappe import _
from frappe.utils import flt

from scanner_app.scanner_app.scan_uom import conversion_factor, default_inventory_uom
from scanner_app.scanner_app.stock_entry_scan import _get_item, resolve_item, verified_rack


def _draft(name, permission="read"):
	if not name:
		frappe.throw(_("Select a Pick List."))
	doc = frappe.get_doc("Pick List", name)
	doc.check_permission(permission)
	if doc.docstatus != 0:
		frappe.throw(_("Pick List {0} is no longer a draft.").format(frappe.bold(name)))
	if not doc.locations:
		frappe.throw(_("Pick List {0} has no item locations.").format(frappe.bold(name)))
	return doc


def _guide(doc):
	items = []
	for row in doc.locations:
		if not row.item_code or flt(row.stock_qty) <= 0:
			frappe.throw(_("Pick List row {0} needs an Item and positive stock quantity.").format(row.idx))
		item = _get_item(row.item_code)
		if row.serial_and_batch_bundle:
			frappe.throw(_("Pick List row {0} already has a Serial and Batch Bundle; finish it in ERPNext.").format(row.idx))
		uom = row.uom or default_inventory_uom(item)
		factor = conversion_factor(item, uom)
		if row.uom and row.conversion_factor and abs(flt(row.conversion_factor) - factor) > 0.000001:
			frappe.throw(_("Pick List row {0} has an invalid UOM conversion factor.").format(row.idx))
		items.append({
			"name": row.name, "item_code": row.item_code,
			"item_name": row.item_name or item.item_name,
			"warehouse": row.warehouse, "batch_no": row.batch_no or "",
			"uom": uom, "conversion_factor": factor,
			"stock_qty": flt(row.stock_qty), "picked_qty": flt(row.picked_qty),
			"qty": flt(row.stock_qty) / factor,
		})
	if len(items) > 200:
		frappe.throw(_("Pick List has more than 200 item rows."))
	return items


@frappe.whitelist(methods=["GET"])
def list_drafts(query=""):
	if not frappe.has_permission("Pick List", "read"):
		frappe.throw(_("You do not have permission to read Pick Lists."), frappe.PermissionError)
	query = str(query or "").strip()[:100]
	filters = {"docstatus": 0}
	if query:
		filters["name"] = ["like", f"%{query}%"]
	return frappe.get_list(
		"Pick List", filters=filters, fields=["name", "company", "purpose", "modified"],
		order_by="modified desc", limit_page_length=30,
	)


@frappe.whitelist(methods=["GET"])
def get_draft(name):
	doc = _draft(name)
	doc.check_permission("write")
	doc.check_permission("submit")
	return {"name": doc.name, "company": doc.company, "purpose": doc.purpose,
		"modified": str(doc.modified), "items": _guide(doc)}


@frappe.whitelist(methods=["GET"])
def lookup_item(code, company=None):
	if not frappe.has_permission("Pick List", "read"):
		frappe.throw(_("You do not have permission to read Pick Lists."), frappe.PermissionError)
	return resolve_item(code, company)


@frappe.whitelist(methods=["POST"])
def submit_draft(name, modified, scans):
	if isinstance(scans, str):
		scans = json.loads(scans)
	if not isinstance(scans, list) or len(scans) > 10000:
		frappe.throw(_("Invalid scan list."))
	if not frappe.has_permission("Pick List", "submit"):
		frappe.throw(_("You do not have permission to submit Pick Lists."), frappe.PermissionError)
	# Lock the draft so two scanner sessions cannot submit different results.
	current = frappe.db.get_value("Pick List", name, ["modified", "docstatus"], as_dict=True, for_update=True)
	if not current or current.docstatus != 0 or str(current.modified) != str(modified):
		frappe.throw(_("Pick List changed in ERPNext. Reload it before submitting."))
	doc = _draft(name, "write")
	guide = {row["name"]: row for row in _guide(doc)}
	rows = {row.name: row for row in doc.locations}
	# The scanner replaces the draft picking result, including any old picked quantity.
	progress = {key: 0.0 for key in guide}
	selected_batches = {}
	selected_racks = {}
	seen_qr = set()
	seen_serials = set()
	for row in doc.locations:
		row.serial_no = None
	for scan in scans:
		if not isinstance(scan, dict) or scan.get("row_name") not in rows:
			frappe.throw(_("Scanned item refers to an invalid Pick List row."))
		row = rows[scan["row_name"]]
		expected = guide[row.name]
		rack = verified_rack(scan.get("source_rack_code"), doc.company, expected["warehouse"])
		if row.name in selected_racks and selected_racks[row.name] != rack:
			frappe.throw(_("Pick List row {0} was scanned from multiple racks.").format(row.idx))
		selected_racks[row.name] = rack
		code = str(scan.get("code") or "").strip()
		if not code or len(code) > 500:
			frappe.throw(_("Invalid scanned code."))
		found = resolve_item(code, doc.company)
		if found.get("warehouse") or found.get("item_code") != row.item_code:
			frappe.throw(_("Scan {0} does not match Pick List row {1}.").format(frappe.bold(code), row.idx))
		batch = found.get("batch_no") or ""
		item = _get_item(row.item_code)
		if item.has_batch_no and not batch:
			frappe.throw(_("Scan the Batch or Product QR for Pick List row {0}.").format(row.idx))
		if item.has_serial_no and not found.get("serial_no"):
			frappe.throw(_("Scan a Serial No for Pick List row {0}.").format(row.idx))
		if row.name in selected_batches and selected_batches[row.name] != batch:
			frappe.throw(_("Pick List row {0} contains scans from different batches.").format(row.idx))
		selected_batches[row.name] = batch
		row.batch_no = batch or None
		if found.get("qr_value"):
			if found["qr_value"] in seen_qr:
				frappe.throw(_("QR {0} was scanned more than once.").format(frappe.bold(code)))
			seen_qr.add(found["qr_value"])
		if found.get("serial_no"):
			serial = found["serial_no"]
			if serial in seen_serials or frappe.db.get_value("Serial No", serial, "item_code") != row.item_code:
				frappe.throw(_("Serial No {0} is duplicate or does not belong to the Item.").format(serial))
			seen_serials.add(serial)
			row.serial_no = "\n".join(filter(None, [row.serial_no, serial]))
		qty = flt(scan.get("qty"))
		if not math.isfinite(qty) or qty <= 0 or qty > 1000000000:
			frappe.throw(_("Invalid scan quantity."))
		progress[row.name] += qty * expected["conversion_factor"]
		if progress[row.name] > expected["stock_qty"] + 0.000001:
			frappe.throw(_("Scanned quantity exceeds Pick List row {0}.").format(row.idx))
	for key, expected in guide.items():
		if abs(progress[key] - expected["stock_qty"]) > 0.000001:
			frappe.throw(_("Scan all quantities for Pick List row {0} first.").format(rows[key].idx))
		row = rows[key]
		row.warehouse = selected_racks[key]
		row.picked_qty = progress[key]
		if row.meta.has_field("custom_picked_qty"):
			row.custom_picked_qty = flt(progress[key] / expected["conversion_factor"], 9)
		if row.meta.has_field("custom_picked_qty_warehouse_uom"):
			item = _get_item(row.item_code)
			warehouse_uom = default_inventory_uom(item)
			warehouse_factor = conversion_factor(item, warehouse_uom)
			row.custom_picked_qty_warehouse_uom = flt(progress[key] / warehouse_factor, 9)
		if row.batch_no or row.serial_no:
			row.use_serial_batch_fields = 1
	doc.scan_mode = 1
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}
