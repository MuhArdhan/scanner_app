"""Permission-aware Stock Entry PWA API using ERPNext's native scan resolver."""

import json
import math

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from erpnext.stock.utils import scan_barcode

from scanner_app.scanner_app.stock_entry_source import (
	allowed_sources,
	guide_rows,
	list_source_names,
	make_source_doc,
	source_context,
)


PURPOSES = (
	"Material Receipt",
	"Material Issue",
	"Material Transfer",
	"Material Transfer for Manufacture",
	"Material Consumption for Manufacture",
	"Manufacture",
	"Repack",
	"Send to Subcontractor",
	"Disassemble",
	"Receive from Customer",
	"Return Raw Material to Customer",
	"Subcontracting Delivery",
	"Subcontracting Return",
)

SOURCE_WAREHOUSE_PURPOSES = {
	"Material Issue", "Material Transfer", "Send to Subcontractor",
	"Material Transfer for Manufacture", "Material Consumption for Manufacture",
	"Return Raw Material to Customer", "Subcontracting Delivery",
}
TARGET_WAREHOUSE_PURPOSES = {
	"Material Receipt", "Material Transfer", "Send to Subcontractor",
	"Material Transfer for Manufacture", "Receive from Customer", "Subcontracting Return",
}
MANUAL_PURPOSES = {"Material Receipt", "Material Issue", "Material Transfer"}


def _require_stock_entry_access():
	if not frappe.has_permission("Stock Entry", "create"):
		frappe.throw(_("You do not have permission to create Stock Entries."), frappe.PermissionError)
	if not frappe.has_permission("Stock Entry", "submit"):
		frappe.throw(_("You do not have permission to submit Stock Entries."), frappe.PermissionError)


def _get_item(item_code):
	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} was not found.").format(frappe.bold(item_code or "")))
	item = frappe.get_doc("Item", item_code)
	item.check_permission("read")
	if (
		item.disabled
		or not item.is_stock_item
		or (
			item.end_of_life
			and "1900-01-01" <= str(item.end_of_life) <= nowdate()
		)
	):
		frappe.throw(_("Item {0} is inactive or is not a stock item.").format(frappe.bold(item.name)))
	return item


def _check_warehouse(name, company):
	if not name or not frappe.db.exists(
		"Warehouse", {"name": name, "company": company, "is_group": 0, "disabled": 0}
	):
		frappe.throw(_("Select an active warehouse for this company."))
	frappe.get_doc("Warehouse", name).check_permission("read")


def _conversion_factor(item, uom):
	if uom == item.stock_uom:
		return 1
	factor = next((flt(row.conversion_factor) for row in item.uoms if row.uom == uom), 0)
	if factor <= 0:
		frappe.throw(_("UOM {0} has no conversion factor for item {1}.").format(uom, item.name))
	return factor


@frappe.whitelist(methods=["GET"])
def get_setup():
	_require_stock_entry_access()
	companies = frappe.get_list("Company", fields=["name"], order_by="name asc", limit_page_length=0)
	warehouses = frappe.get_list(
		"Warehouse", filters={"is_group": 0, "disabled": 0},
		fields=["name", "company"], order_by="name asc", limit_page_length=0,
	)
	return {
		"companies": [row.name for row in companies],
		"warehouses": warehouses,
		"default_company": frappe.defaults.get_user_default("Company"),
		"purposes": list(PURPOSES),
		"sources": {
			purpose: [source for source in allowed_sources(purpose)
				if frappe.has_permission(
					"Stock Entry" if source in ("Transit Entry", "Source Stock Entry")
					else "Batch" if source == "Expired Batches"
					else "Subcontracting Inward Order" if source.startswith("Subcontracting Inward Order")
					else source,
					"read",
				)]
			for purpose in PURPOSES
		},
	}


@frappe.whitelist(methods=["GET"])
def list_sources(source_type, company=None, purpose=None, query=""):
	_require_stock_entry_access()
	if purpose and purpose not in PURPOSES:
		frappe.throw(_("Unsupported Stock Entry purpose."))
	if company:
		frappe.get_doc("Company", company).check_permission("read")
	return list_source_names(source_type, company, purpose, query)


@frappe.whitelist(methods=["GET"])
def get_source_items(source_type, company=None, purpose=None, source_name=None, options=None):
	_require_stock_entry_access()
	company, purpose = source_context(source_type, source_name, company, purpose)
	if purpose not in PURPOSES:
		frappe.throw(_("Unsupported Stock Entry purpose."))
	if not company:
		frappe.throw(_("Select a company."))
	frappe.get_doc("Company", company).check_permission("read")
	doc = make_source_doc(source_type, source_name, company, purpose, options)
	def common_warehouse(field):
		values = {row.get(field) for row in doc.items if row.get(field)}
		return values.pop() if len(values) == 1 else ""
	return {
		"items": guide_rows(doc),
		"company": company,
		"purpose": purpose,
		"from_warehouse": doc.from_warehouse or common_warehouse("s_warehouse"),
		"to_warehouse": doc.to_warehouse or common_warehouse("t_warehouse"),
	}


@frappe.whitelist(methods=["GET"])
def lookup_item(code, company=None):
	"""Resolve exactly the same scan values as the native Stock Entry scanner."""
	_require_stock_entry_access()
	code = str(code or "").strip()
	if not code or len(code) > 140:
		frappe.throw(_("Scan a valid barcode, serial, batch, or warehouse code."))
	result = scan_barcode(code, ctx={"company": company} if company else None)
	if not result:
		frappe.throw(_("No Item or Warehouse was found for this scan."))
	if result.get("warehouse"):
		warehouse = result["warehouse"]
		_check_warehouse(warehouse, company)
		return {"warehouse": warehouse}

	item = _get_item(result.get("item_code"))
	uom = result.get("uom") or item.stock_uom
	_conversion_factor(item, uom)
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"stock_uom": item.stock_uom,
		"uom": uom,
		"conversion_factor": _conversion_factor(item, uom),
		"explicit_uom": bool(result.get("uom")),
		"barcode": result.get("barcode") or "",
		"serial_no": result.get("serial_no") or "",
		"batch_no": result.get("batch_no") or "",
		"has_serial_no": bool(item.has_serial_no),
		"has_batch_no": bool(item.has_batch_no),
	}


def _submit_source_entry(purpose, company, items, source_type, source_name, options, from_warehouse, to_warehouse):
	"""Submit verified scan quantities while retaining native source references."""
	doc = make_source_doc(source_type, source_name, company, purpose, options)
	if from_warehouse:
		_check_warehouse(from_warehouse, company)
		doc.from_warehouse = from_warehouse
	if to_warehouse:
		_check_warehouse(to_warehouse, company)
		doc.to_warehouse = to_warehouse
	source_rows = list(doc.items)
	doc.set("items", [])
	totals = [0.0] * len(source_rows)
	seen_serials = set()
	for scan in items:
		if not isinstance(scan, dict):
			frappe.throw(_("Invalid scanned item row."))
		try:
			index = int(scan.get("guide_key"))
		except (TypeError, ValueError):
			frappe.throw(_("Scanned item has no source row."))
		if index < 0 or index >= len(source_rows) or str(index) != str(scan.get("guide_key")):
			frappe.throw(_("Scanned item refers to an invalid source row."))
		mapped = source_rows[index]
		item = _get_item(scan.get("item_code"))
		if item.name != mapped.item_code:
			frappe.throw(_("Scanned item does not match the source row."))
		uom = str(mapped.uom)
		if scan.get("uom") != uom:
			frappe.throw(_("Scanned UOM must match the source row UOM for {0}.").format(item.name))
		factor = _conversion_factor(item, uom)
		qty = flt(scan.get("qty"))
		if not math.isfinite(qty) or qty <= 0:
			frappe.throw(_("Scanned quantity must be positive."))
		totals[index] += qty * factor
		if totals[index] > flt(mapped.qty) * flt(mapped.conversion_factor) + 0.000001:
			frappe.throw(_("Scanned quantity exceeds the source quantity for {0}.").format(item.name))

		need_source, need_target = _source_row_warehouse_roles(purpose, mapped)
		source = (scan.get("s_warehouse") or mapped.s_warehouse or doc.from_warehouse) if need_source else None
		target = (scan.get("t_warehouse") or mapped.t_warehouse or doc.to_warehouse) if need_target else None
		if need_source and source:
			_check_warehouse(source, company)
		if need_target and target:
			_check_warehouse(target, company)
		if (need_source and not source) or (need_target and not target):
			frappe.throw(_("Select warehouses for every scanned item."))
		if source and target and source == target and purpose not in ("Material Transfer", "Material Transfer for Manufacture"):
			frappe.throw(_("Source and target warehouses must be different."))
		barcode = str(scan.get("barcode") or "").strip()
		if barcode:
			match = next((b for b in item.barcodes if b.barcode == barcode), None)
			if not match:
				frappe.throw(_("Barcode does not match this item."))
		batch = str(scan.get("batch_no") or "").strip()
		if batch and (not item.has_batch_no or frappe.db.get_value("Batch", batch, "item") != item.name):
			frappe.throw(_("Batch does not belong to the source item."))
		if mapped.batch_no and batch != mapped.batch_no:
			frappe.throw(_("Scanned batch differs from the source row."))
		serials = [value.strip() for value in str(scan.get("serial_no") or "").splitlines() if value.strip()]
		if serials and not item.has_serial_no:
			frappe.throw(_("Item {0} does not use serial numbers.").format(item.name))
		for serial in serials:
			if serial in seen_serials or frappe.db.get_value("Serial No", serial, "item_code") != item.name:
				frappe.throw(_("Serial No is duplicate or belongs to another item."))
			seen_serials.add(serial)

		values = mapped.as_dict()
		for field in ("name", "parent", "parentfield", "parenttype", "idx", "docstatus", "creation", "modified", "modified_by", "owner"):
			values.pop(field, None)
		values.update({
			"qty": qty, "uom": uom, "stock_uom": item.stock_uom, "conversion_factor": factor,
			"s_warehouse": source, "t_warehouse": target,
			"barcode": barcode or None, "batch_no": batch or None,
			"serial_no": "\n".join(serials) or None,
			"serial_and_batch_bundle": None,
			"use_serial_batch_fields": 1 if item.has_serial_no or item.has_batch_no else 0,
		})
		doc.append("items", values)
	for index, mapped in enumerate(source_rows):
		if abs(totals[index] - flt(mapped.qty) * flt(mapped.conversion_factor)) > 0.000001:
			frappe.throw(_("Scan all required quantities before submitting the Stock Entry."))
	doc.set_stock_entry_type()
	doc.insert()
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


def _source_row_warehouse_roles(purpose, row):
	"""Return which row warehouses ERPNext expects for this purpose and item role."""
	if purpose in ("Manufacture", "Repack"):
		is_output = bool(row.is_finished_item or row.secondary_item_type or row.valuation_type)
		return (not is_output, is_output)
	if purpose == "Disassemble":
		# Native disassembly rows already mark the warehouse side when sourced from
		# a manufacture entry, Work Order, or BOM.
		is_source_item = bool(row.s_warehouse or row.is_finished_item or row.secondary_item_type or row.valuation_type)
		return is_source_item, not is_source_item
	return purpose in SOURCE_WAREHOUSE_PURPOSES, purpose in TARGET_WAREHOUSE_PURPOSES


@frappe.whitelist(methods=["POST"])
def submit_entry(purpose, company, items, from_warehouse=None, to_warehouse=None, source_type=None, source_name=None, source_options=None):
	_require_stock_entry_access()
	if purpose not in PURPOSES:
		frappe.throw(_("Unsupported Stock Entry purpose."))
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Select a valid company."))
	frappe.get_doc("Company", company).check_permission("read")

	if isinstance(items, str):
		try:
			items = json.loads(items)
		except (TypeError, ValueError):
			frappe.throw(_("Invalid item list."))
	if not isinstance(items, list) or not 0 < len(items) <= 200:
		frappe.throw(_("Add between 1 and 200 item rows."))
	if source_type:
		return _submit_source_entry(
			purpose, company, items, source_type, source_name, source_options,
			from_warehouse, to_warehouse,
		)
	if purpose not in MANUAL_PURPOSES:
		frappe.throw(_("Use Get Items From to prepare this Stock Entry purpose."))

	need_source = purpose in SOURCE_WAREHOUSE_PURPOSES
	need_target = purpose in TARGET_WAREHOUSE_PURPOSES
	if need_source and from_warehouse:
		_check_warehouse(from_warehouse, company)
	if need_target and to_warehouse:
		_check_warehouse(to_warehouse, company)
	if purpose == "Material Transfer" and from_warehouse and from_warehouse == to_warehouse:
		frappe.throw(_("Source and target warehouses must be different."))

	doc = frappe.new_doc("Stock Entry")
	doc.company = company
	doc.purpose = purpose
	doc.set_stock_entry_type()
	if not doc.stock_entry_type:
		frappe.throw(_("No standard Stock Entry Type exists for {0}.").format(purpose))
	doc.from_warehouse = from_warehouse if need_source else None
	doc.to_warehouse = to_warehouse if need_target else None
	seen_serials = set()
	for row in items:
		if not isinstance(row, dict):
			frappe.throw(_("Invalid item row."))
		item = _get_item(row.get("item_code"))
		uom = str(row.get("uom") or item.stock_uom)
		factor = _conversion_factor(item, uom)
		try:
			qty = flt(row.get("qty"))
		except (TypeError, ValueError):
			frappe.throw(_("Invalid quantity for item {0}.").format(frappe.bold(item.name)))
		if not math.isfinite(qty) or qty <= 0 or qty > 1000000000:
			frappe.throw(_("Enter a positive quantity for item {0}.").format(frappe.bold(item.name)))

		source = (row.get("s_warehouse") or doc.from_warehouse) if need_source else None
		target = (row.get("t_warehouse") or doc.to_warehouse) if need_target else None
		if need_source:
			_check_warehouse(source, company)
		if need_target:
			_check_warehouse(target, company)
		if source and target and source == target:
			frappe.throw(_("Source and target warehouses must be different."))

		barcode = str(row.get("barcode") or "").strip()
		if barcode:
			matched_barcode = next((b for b in item.barcodes if b.barcode == barcode), None)
			if not matched_barcode:
				frappe.throw(_("Barcode does not belong to item {0}.").format(item.name))
			if matched_barcode.uom and matched_barcode.uom != uom:
				frappe.throw(_("Barcode UOM does not match item row UOM."))

		batch_no = str(row.get("batch_no") or "").strip()
		if batch_no and (not item.has_batch_no or frappe.db.get_value("Batch", batch_no, "item") != item.name):
			frappe.throw(_("Batch {0} does not belong to item {1}.").format(batch_no, item.name))
		serials = [value.strip() for value in str(row.get("serial_no") or "").splitlines() if value.strip()]
		if serials and not item.has_serial_no:
			frappe.throw(_("Item {0} does not use serial numbers.").format(item.name))
		for serial in serials:
			if serial in seen_serials or frappe.db.get_value("Serial No", serial, "item_code") != item.name:
				frappe.throw(_("Serial No {0} is duplicate or does not belong to item {1}.").format(serial, item.name))
			seen_serials.add(serial)

		doc.append("items", {
			"item_code": item.name, "qty": qty, "uom": uom,
			"stock_uom": item.stock_uom, "conversion_factor": factor,
			"s_warehouse": source, "t_warehouse": target,
			"barcode": barcode or None, "batch_no": batch_no or None,
			"serial_no": "\n".join(serials) or None,
			"use_serial_batch_fields": 1 if item.has_serial_no or item.has_batch_no else 0,
		})
	doc.insert()
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}
