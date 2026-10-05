"""Native Get Items From sources for the Stock Entry scanner."""

import json
import math

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_stock_entry as from_invoice
from erpnext.manufacturing.doctype.bom.bom import get_bom_items
from erpnext.stock.doctype.material_request.material_request import make_stock_entry as from_request
from erpnext.stock.doctype.stock_entry.stock_entry import get_expired_batch_items, make_stock_in_entry


SOURCE_TYPES = ("Material Request", "BOM", "Purchase Invoice", "Transit Entry", "Expired Batches")

INWARD_PURPOSES = {
	"Subcontracting Inward Order — Receive from Customer": "Receive from Customer",
	"Subcontracting Inward Order — Return Raw Material to Customer": "Return Raw Material to Customer",
	"Subcontracting Inward Order — Subcontracting Delivery": "Subcontracting Delivery",
	"Subcontracting Inward Order — Subcontracting Return": "Subcontracting Return",
}
INWARD_SOURCE_TYPES = tuple(INWARD_PURPOSES)
SOURCE_PURPOSES = {
	"Material Receipt": ("Material Request", "Purchase Invoice"),
	"Material Issue": ("Material Request", "BOM", "Expired Batches"),
	"Material Transfer": ("Material Request", "BOM", "Transit Entry"),
	"Material Transfer for Manufacture": ("Work Order", "Job Card", "BOM"),
	"Material Consumption for Manufacture": ("Work Order", "BOM"),
	"Manufacture": ("Work Order", "BOM"),
	"Repack": ("BOM",),
	"Send to Subcontractor": ("Purchase Order", "Subcontracting Order"),
	"Disassemble": ("Work Order", "Source Stock Entry", "BOM"),
	"Receive from Customer": ("Subcontracting Inward Order — Receive from Customer",),
	"Return Raw Material to Customer": ("Subcontracting Inward Order — Return Raw Material to Customer",),
	"Subcontracting Delivery": ("Subcontracting Inward Order — Subcontracting Delivery",),
	"Subcontracting Return": ("Subcontracting Inward Order — Subcontracting Return",),
}
SOURCE_DOCTYPES = {
	"Transit Entry": "Stock Entry",
	"Source Stock Entry": "Stock Entry",
	"Work Order": "Work Order",
	"Job Card": "Job Card",
	"Purchase Order": "Purchase Order",
	"Subcontracting Order": "Subcontracting Order",
	**{source_type: "Subcontracting Inward Order" for source_type in INWARD_SOURCE_TYPES},
}


def allowed_sources(purpose):
	return list(SOURCE_PURPOSES.get(purpose, ()))


def all_source_types():
	return list(dict.fromkeys(source for sources in SOURCE_PURPOSES.values() for source in sources))


def source_purposes(source_type):
	return [purpose for purpose, sources in SOURCE_PURPOSES.items() if source_type in sources]


def default_source_purpose(source_type):
	if source_type in ("BOM", "Work Order"):
		return "Manufacture"
	purposes = source_purposes(source_type)
	return purposes[0] if len(purposes) == 1 else None


def source_options(value):
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid source options."))
	if value is None:
		value = {}
	if not isinstance(value, dict):
		frappe.throw(_("Invalid source options."))
	qty_value = value.get("qty", 1)
	qty = None if qty_value in (None, "") else flt(qty_value)
	if qty is not None and (not math.isfinite(qty) or qty <= 0 or qty > 1000000):
		frappe.throw(_("Quantity must be positive and at most 1,000,000."))
	return {
		"qty": qty,
		"fetch_exploded": 1 if str(value.get("fetch_exploded", 1)) not in ("0", "false", "False") else 0,
		"source_stock_entry": str(value.get("source_stock_entry") or "").strip(),
	}


def _source_doctype(source_type):
	return SOURCE_DOCTYPES.get(source_type, source_type)


def _as_document(value):
	if isinstance(value, dict):
		return frappe.get_doc(dict(value))
	return value if hasattr(value, "doctype") and hasattr(value, "as_dict") else frappe.get_doc(value)


def _check_source(source_type, source_name, company, purpose):
	if source_type not in allowed_sources(purpose):
		frappe.throw(_("This source is not available for the selected Stock Entry purpose."))
	if source_type == "Expired Batches":
		if not frappe.has_permission("Batch", "read"):
			frappe.throw(_("You do not have permission to read batches."), frappe.PermissionError)
		return None
	if not source_name:
		frappe.throw(_("Select a source document."))
	source = frappe.get_doc(_source_doctype(source_type), source_name)
	source.check_permission("read")
	if source_type == "BOM":
		if not source.is_active or source.docstatus != 1:
			frappe.throw(_("Select an active, submitted BOM."))
		if source.company and source.company != company:
			frappe.throw(_("Select a BOM for this company."))
		return source
	if (source.company and source.company != company) or source.docstatus != 1:
		frappe.throw(_("Select a submitted source document for this company."))
	if source_type == "Material Request":
		request_type = {
			"Material Receipt": "Customer Provided",
			"Material Issue": "Material Issue",
			"Material Transfer": "Material Transfer",
		}[purpose]
		if source.material_request_type != request_type or source.status in ("Transferred", "Issued", "Cancelled", "Stopped"):
			frappe.throw(_("This Material Request is not available for the selected purpose."))
		if source.work_order or source.job_card:
			frappe.throw(_("Use the Work Order or Job Card source for manufacturing requests."))
	elif source_type == "Transit Entry":
		if source.purpose != "Material Transfer" or not source.add_to_transit or flt(source.per_transferred) >= 100:
			frappe.throw(_("Select an open Transit Entry."))
	elif source_type == "Work Order":
		if source.status in ("Stopped", "Cancelled"):
			frappe.throw(_("Select an open Work Order."))
	elif source_type == "Job Card":
		if source.status in ("Completed", "Cancelled"):
			frappe.throw(_("Select an open Job Card."))
	elif source_type == "Source Stock Entry":
		if source.purpose != "Manufacture":
			frappe.throw(_("Disassembly source must be a submitted Manufacture Stock Entry."))
	elif source_type == "Purchase Order":
		if not source.is_subcontracted or source.status in ("Completed", "Cancelled", "Closed"):
			frappe.throw(_("Select an open subcontracted Purchase Order."))
	elif source_type == "Subcontracting Order":
		if source.status in ("Completed", "Cancelled", "Closed"):
			frappe.throw(_("Select an open Subcontracting Order."))
	return source


def list_source_names(source_type, company=None, purpose=None, query=""):
	if source_type not in all_source_types() or (purpose and source_type not in allowed_sources(purpose)):
		frappe.throw(_("This source is not available for the selected Stock Entry purpose."))
	if source_type == "Expired Batches":
		return []
	doctype = _source_doctype(source_type)
	filters = {"docstatus": 1}
	if company and source_type != "BOM":
		filters["company"] = company
	if source_type == "Material Request":
		request_types = {
			"Material Receipt": "Customer Provided",
			"Material Issue": "Material Issue",
			"Material Transfer": "Material Transfer",
		}
		filters["material_request_type"] = request_types[purpose] if purpose else ["in", list(request_types.values())]
		filters["status"] = ["not in", ["Transferred", "Issued", "Cancelled", "Stopped"]]
	elif source_type == "BOM":
		filters["is_active"] = 1
	elif source_type == "Transit Entry":
		filters.update({"purpose": "Material Transfer", "add_to_transit": 1, "per_transferred": ["<", 100]})
	elif source_type == "Work Order":
		filters["status"] = ["not in", ["Stopped", "Cancelled"]]
	elif source_type == "Job Card":
		filters["status"] = ["not in", ["Completed", "Cancelled"]]
	elif source_type == "Source Stock Entry":
		filters["purpose"] = "Manufacture"
	elif source_type == "Purchase Order":
		filters.update({"is_subcontracted": 1, "status": ["not in", ["Completed", "Cancelled", "Closed"]]})
	elif source_type == "Subcontracting Order":
		filters["status"] = ["not in", ["Completed", "Cancelled", "Closed"]]
	query = str(query or "").strip()[:100]
	if query:
		filters["name"] = ["like", f"%{query}%"]
	return frappe.get_list(doctype, filters=filters, pluck="name", order_by="modified desc", limit_page_length=30)


def source_context(source_type, source_name, company=None, purpose=None):
	"""Use the selected document for company and any purpose it fixes."""
	if source_type == "Expired Batches":
		return company, "Material Issue"
	if source_type not in SOURCE_TYPES + tuple(SOURCE_DOCTYPES) or (source_type != "Expired Batches" and not source_name):
		frappe.throw(_("Select a source document."))
	if source_type in INWARD_SOURCE_TYPES:
		purpose = INWARD_PURPOSES[source_type]
	elif source_type == "Job Card":
		purpose = "Material Transfer for Manufacture"
	elif source_type == "Source Stock Entry":
		purpose = "Disassemble"
	elif source_type in ("Purchase Order", "Subcontracting Order"):
		purpose = "Send to Subcontractor"
	elif source_type == "Purchase Invoice":
		purpose = "Material Receipt"
	elif source_type == "Material Request":
		source = frappe.get_doc("Material Request", source_name)
		source.check_permission("read")
		purpose = {"Customer Provided": "Material Receipt", "Material Issue": "Material Issue", "Material Transfer": "Material Transfer"}.get(source.material_request_type)
	elif source_type in ("BOM", "Work Order"):
		if purpose not in source_purposes(source_type):
			purpose = default_source_purpose(source_type)
		if purpose not in source_purposes(source_type):
			frappe.throw(_("Choose a compatible Stock Entry purpose for this source."))
	source = frappe.get_doc(_source_doctype(source_type), source_name)
	source.check_permission("read")
	if source_type == "Transit Entry":
		purpose = "Material Transfer"
	return getattr(source, "company", None) or company, purpose


def make_source_doc(source_type, source_name, company, purpose, options=None):
	"""Build a fresh unsaved Stock Entry using the same source mappers as Desk."""
	options = source_options(options)
	source = _check_source(source_type, source_name, company, purpose)
	doc = frappe.new_doc("Stock Entry")
	doc.company = company
	doc.purpose = purpose
	doc.set_stock_entry_type()
	if source_type == "Material Request":
		doc = from_request(source_name, target_doc=frappe.as_json(doc.as_dict()))
	elif source_type == "Purchase Invoice":
		doc = from_invoice(source_name, target_doc=frappe.as_json(doc.as_dict()))
	elif source_type == "Transit Entry":
		doc = make_stock_in_entry(source_name, target_doc=frappe.as_json(doc.as_dict()))
	elif source_type == "BOM":
		qty = options["qty"] or 1
		if purpose in ("Disassemble", "Manufacture", "Repack", "Material Transfer for Manufacture", "Material Consumption for Manufacture"):
			doc.bom_no = source_name
			doc.from_bom = 1
			doc.use_multi_level_bom = options["fetch_exploded"]
			doc.fg_completed_qty = qty
			doc.posting_date = nowdate()
			doc.posting_time = nowtime()
			doc.get_items()
		else:
			for item in get_bom_items(source_name, company, qty, options["fetch_exploded"]):
				doc.append("items", {"item_code": item.item_code, "qty": item.qty, "uom": item.stock_uom,
					"stock_uom": item.stock_uom, "conversion_factor": item.conversion_factor or 1,
					"expense_account": item.expense_account, "project": item.project})
	elif source_type == "Work Order":
		from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

		qty = options["qty"] or (1 if purpose == "Disassemble" else None)
		doc = _as_document(make_stock_entry(
			source_name,
			purpose,
			qty,
			target_warehouse=None,
			source_stock_entry=options["source_stock_entry"] or None,
		))
	elif source_type == "Job Card":
		from erpnext.manufacturing.doctype.job_card.job_card import make_stock_entry

		doc = _as_document(make_stock_entry(source_name))
	elif source_type == "Source Stock Entry":
		doc.source_stock_entry = source_name
		doc.fg_completed_qty = options["qty"] or 1
		doc.get_items()
	elif source_type in ("Purchase Order", "Subcontracting Order"):
		from erpnext.stock.doctype.stock_entry.stock_entry import get_items_from_subcontract_order

		if source_type == "Purchase Order":
			doc.purchase_order = source_name
		else:
			doc.subcontracting_order = source_name
		doc = _as_document(get_items_from_subcontract_order(source_name, target_doc=frappe.as_json(doc.as_dict())))
	elif source_type in INWARD_SOURCE_TYPES:
		method = {
			"Subcontracting Inward Order — Receive from Customer": "make_stock_entry_inward",
			"Subcontracting Inward Order — Return Raw Material to Customer": "make_rm_return",
			"Subcontracting Inward Order — Subcontracting Delivery": "make_subcontracting_delivery",
			"Subcontracting Inward Order — Subcontracting Return": "make_subcontracting_return",
		}[source_type]
		doc = _as_document(getattr(source, method)())
	elif source_type == "Expired Batches":
		for row in get_expired_batch_items():
			warehouse = frappe.get_doc("Warehouse", row.warehouse)
			if warehouse.company == company and frappe.has_permission("Warehouse", "read", doc=warehouse):
				doc.append("items", {"item_code": row.item, "qty": row.qty, "uom": row.stock_uom,
					"stock_uom": row.stock_uom, "conversion_factor": 1,
					"s_warehouse": row.warehouse, "batch_no": row.batch_no,
					"use_serial_batch_fields": 1})
	if not doc.company:
		doc.company = company
	if doc.purpose != purpose or doc.company != company:
		frappe.throw(_("The source document maps to a different company or Stock Entry purpose."))

	rows = []
	for row in list(doc.items):
		if flt(row.qty) <= 0:
			continue
		item = frappe.get_doc("Item", row.item_code)
		item.check_permission("read")
		if not item.is_stock_item or item.disabled:
			continue
		if not row.uom:
			row.uom = item.stock_uom
		if not row.stock_uom:
			row.stock_uom = item.stock_uom
		if not row.conversion_factor:
			row.conversion_factor = next((flt(u.conversion_factor) for u in item.uoms if u.uom == row.uom), 1 if row.uom == item.stock_uom else 0)
		if flt(row.conversion_factor) <= 0:
			frappe.throw(_("Invalid UOM conversion in source item {0}.").format(item.name))
		rows.append(row)
	doc.set("items", rows)
	if not rows:
		frappe.throw(_("No stock items remain in this source document."))
	if len(rows) > 200:
		frappe.throw(_("This source has more than 200 item rows."))
	return doc


def guide_rows(doc):
	return [{
		"key": str(i), "item_code": row.item_code, "item_name": row.item_name or row.item_code,
		"qty": flt(row.qty), "uom": row.uom, "stock_qty": flt(row.qty) * flt(row.conversion_factor),
		"s_warehouse": row.s_warehouse or "", "t_warehouse": row.t_warehouse or "",
		"batch_no": row.batch_no or "",
		"is_finished_item": bool(row.is_finished_item),
		"secondary_item_type": row.secondary_item_type or "",
		"valuation_type": row.valuation_type or "",
	} for i, row in enumerate(doc.items)]
