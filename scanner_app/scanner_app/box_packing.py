"""Physical grouping only: no stock or Product QR writes, no manual commits.

Lock order for every mutation: box -> Product QR Serial -> membership. Current
locking reads avoid stale repeatable-read snapshots. The unique serial membership
index is the final defense against cross-box races. All events share the transaction.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
import re
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

BOX = "Warehouse Box QR"
CHILD = "Warehouse Box Child"
EVENT = "Warehouse Box Event"
SERIAL = "Product QR Serial"
_internal = ContextVar("scanner_box_mutation", default=False)


@frappe.whitelist(methods=["POST"])
def validate_scan(qr_payload):
	"""Validate a pending child without allocating any box or membership."""
	_require_stock_role()
	serial, item, expiry = _serial(qr_payload)
	if frappe.db.get_value(CHILD, {"product_qr_serial": serial.name}, "name", for_update=True):
		frappe.throw(_("This Product QR is already packed."))
	return {"product_qr_serial": serial.name, "qr_payload": serial.qr_payload,
		"item_code": serial.item_code, "item_name": item.item_name,
		"batch_no": serial.batch_no, "expiry_date": expiry}


@frappe.whitelist(methods=["POST"])
def finish_packing(qr_payloads, request_key):
	"""Allocate a sealed mother only after all pending scans are revalidated."""
	_require_stock_role()
	if not frappe.has_permission(BOX, "create"):
		frappe.throw(_("No permission to create boxes."), frappe.PermissionError)
	if not isinstance(request_key, str) or not re.fullmatch(r"[a-f0-9-]{36}", request_key):
		frappe.throw(_("Invalid packing request."))
	if isinstance(qr_payloads, str):
		qr_payloads = json.loads(qr_payloads)
	if not isinstance(qr_payloads, list) or not 1 <= len(qr_payloads) <= 1000:
		frappe.throw(_("Scan between 1 and 1000 products before finishing."))
	if any(not isinstance(p, str) for p in qr_payloads) or len(set(qr_payloads)) != len(qr_payloads):
		frappe.throw(_("Duplicate or invalid Product QR."))
	# Stable serial lock ordering also serializes retries of the same pending list.
	resolved = [_serial(p) for p in sorted(qr_payloads)]
	existing = frappe.db.get_value(BOX, {"request_key": request_key}, "name", for_update=True)
	if existing:
		box = _box(existing)
		if box.owner != frappe.session.user or {c.product_qr_serial for c in _children(box)} != {entry[0].name for entry in resolved}:
			frappe.throw(_("Packing request does not match the saved box."))
		return _snapshot(box)
	if len({entry[0].item_code for entry in resolved}) != 1:
		frappe.throw(_("Only one Item per box; mixed batches are allowed."))
	for serial, item, expiry in resolved:
		if frappe.db.get_value(CHILD, {"product_qr_serial": serial.name}, "name", for_update=True):
			frappe.throw(_("A scanned product is already packed. Review the pending list."))
	with internal_mutation():
		serial, item, expiry = resolved[0]
		box = frappe.get_doc({"doctype": BOX, "status": "Open", "request_key": request_key,
			"item_code": serial.item_code, "item_name": item.item_name}).insert()
		_event(box, "Create")
		for serial, child_item, expiry in resolved:
			frappe.get_doc({"doctype": CHILD, "box_qr": box.name,
				"product_qr_serial": serial.name, "item_code": serial.item_code,
				"batch_no": serial.batch_no, "expiry_date": expiry,
				"scanned_by": frappe.session.user, "scanned_at": now_datetime()}).insert(ignore_permissions=True)
			box.total_qty = (box.total_qty or 0) + 1
			_event(box, "Add", serial.name)
		_refresh(box)
		box.status, box.sealed_at = "Sealed", now_datetime()
		box.save(ignore_permissions=True)
		_event(box, "Seal")
	return _snapshot(box, True)


@contextmanager
def internal_mutation():
	token = _internal.set(True)
	try:
		yield
	finally:
		_internal.reset(token)


def require_internal():
	if not _internal.get():
		frappe.throw(_("Use Packing Box actions to change boxes."), frappe.PermissionError)


def _require_stock_role():
	if not set(frappe.get_roles()) & {"Stock User", "Stock Manager", "System Manager"}:
		frappe.throw(_("Stock role required."), frappe.PermissionError)


def _name(value):
	value = str(value or "").strip()
	if value.startswith("BOX:"):
		value = value[4:]
	if not re.fullmatch(r"BOX-[A-Za-z0-9-]{1,100}", value):
		frappe.throw(_("Scan a valid BOX QR or enter its Box ID."))
	return value


def _box(name, lock=False):
	_require_stock_role()
	box = frappe.get_doc(BOX, _name(name), for_update=lock)
	box.check_permission("read")
	if lock:
		box.check_permission("write")
	return box


def _editable(box):
	if box.status not in ("Open", "Opened"):
		frappe.throw(_("Reopen the sealed box before changing contents."))


def _children(box, lock=False):
	# Authorized by the parent, no arbitrary child query exposed to clients.
	return frappe.db.sql(
		"SELECT name, product_qr_serial, item_code, batch_no, expiry_date, scanned_at "
		"FROM `tabWarehouse Box Child` WHERE box_qr=%s ORDER BY name" +
		(" FOR UPDATE" if lock else ""), (box.name,), as_dict=True)


def summary(children):
	batches = Counter(c.batch_no or "NOBATCH" for c in children)
	dates = [str(c.expiry_date) for c in children if c.expiry_date]
	unknown = len(children) - len(dates)
	return {"total_qty": len(children), "batch_counts": dict(sorted(batches.items())),
		"batches_summary": ", ".join(f"{b} ({n})" for b, n in sorted(batches.items())),
		"earliest_expiry": min(dates) if dates else None,
		"expiry_unknown": unknown, "mixed_batches": len(batches) > 1}


def _receipt_dates(children):
	"""RCP is the source PR posting date, never the date of packing."""
	if not children:
		return {"receipt_date": None, "receipt_dates": [], "receipt_unknown": 0}
	mapped = {}
	if frappe.db.table_exists("Purchase Receipt QR Label"):
		rows = frappe.get_all("Purchase Receipt QR Label",
			filters={"product_qr_serial": ("in", [c.product_qr_serial for c in children])},
			fields=["product_qr_serial", "purchase_receipt"], limit_page_length=0)
		receipts = {}
		for row in rows:
			if row.purchase_receipt not in receipts:
				pr = frappe.get_doc("Purchase Receipt", row.purchase_receipt)
				receipts[row.purchase_receipt] = str(pr.posting_date) if pr.docstatus == 1 and pr.has_permission("read") and pr.posting_date else None
			if receipts[row.purchase_receipt]:
				mapped[row.product_qr_serial] = receipts[row.purchase_receipt]
	dates = sorted(set(mapped.values()))
	unknown = sum(c.product_qr_serial not in mapped for c in children)
	return {"receipt_date": dates[0] if len(dates) == 1 and not unknown else None,
		"receipt_dates": dates, "receipt_unknown": unknown}


def _snapshot(box, lock=False):
	children = _children(box, lock)
	for c in children:
		frappe.get_doc(SERIAL, c.product_qr_serial).check_permission("read")
		frappe.get_doc("Item", c.item_code).check_permission("read")
		if c.batch_no:
			frappe.get_doc("Batch", c.batch_no).check_permission("read")
	return {"name": box.name, "box_id": box.name, "qr_payload": box.qr_payload,
		"status": box.status, "item_code": box.item_code, "item_name": box.item_name,
		"modified": str(box.modified), "children": children, **summary(children), **_receipt_dates(children)}


def _refresh(box):
	children = _children(box, True)
	data = summary(children)
	for key in ("total_qty", "batches_summary", "earliest_expiry"):
		setattr(box, key, data[key])
	if not children:
		box.item_code = box.item_name = None
	box.save(ignore_permissions=True)


def _event(box, action, serial=None):
	frappe.get_doc({"doctype": EVENT, "box_qr": box.name, "action": action,
		"product_serial": serial, "actor": frappe.session.user,
		"occurred_at": now_datetime(), "item_code_snapshot": box.item_code,
		"count_after": box.total_qty, "status_after": box.status}).insert(ignore_permissions=True)


@frappe.whitelist(methods=["GET"])
def list_boxes(start=0):
	_require_stock_role()
	start = int(start)
	if start < 0:
		frappe.throw(_("Invalid page."))
	return frappe.get_list(BOX, fields=["name", "status", "item_code", "total_qty"],
		order_by="creation desc", start=start, page_length=20)


@frappe.whitelist(methods=["POST"])
def create_box():
	_require_stock_role()
	frappe.throw(_("Scan products first, then use Finish Packing to create a box."))


@frappe.whitelist(methods=["GET"])
def read_box(name):
	return _snapshot(_box(name))


def _serial(qr_payload):
	# Exact payload lookup; never split hyphens or accept an Item barcode.
	if not isinstance(qr_payload, str) or not 1 <= len(qr_payload) <= 500:
		frappe.throw(_("Scan a registered Product QR."))
	name = frappe.db.get_value(SERIAL, {"qr_payload": qr_payload}, "name", for_update=True)
	if not name:
		frappe.throw(_("Product QR not registered."))
	serial = frappe.get_doc(SERIAL, name, for_update=True)
	serial.check_permission("read")
	item = frappe.get_doc("Item", serial.item_code)
	item.check_permission("read")
	if item.disabled:
		frappe.throw(_("Item is disabled."))
	expiry = None
	if serial.batch_no:
		batch = frappe.get_doc("Batch", serial.batch_no)
		batch.check_permission("read")
		if batch.item != serial.item_code:
			frappe.throw(_("Batch does not belong to this Item."))
		expiry = batch.expiry_date
	return serial, item, expiry


@frappe.whitelist(methods=["POST"])
def add_child(box_name, qr_payload):
	box = _box(box_name, True)
	_editable(box)
	serial, item, expiry = _serial(qr_payload)
	if box.item_code and box.item_code != serial.item_code:
		frappe.throw(_("Only one Item per box; mixed batches are allowed."))
	if frappe.db.sql("SELECT name FROM `tabWarehouse Box Child` WHERE product_qr_serial=%s FOR UPDATE", (serial.name,)):
		frappe.throw(_("This Product QR is already packed. Reload the box if a previous request timed out."))
	with internal_mutation():
		box.item_code, box.item_name = serial.item_code, item.item_name
		frappe.get_doc({"doctype": CHILD, "box_qr": box.name,
			"product_qr_serial": serial.name, "item_code": serial.item_code,
			"batch_no": serial.batch_no, "expiry_date": expiry,
			"scanned_by": frappe.session.user, "scanned_at": now_datetime()}).insert(ignore_permissions=True)
		_refresh(box)
		_event(box, "Add", serial.name)
	return _snapshot(box, True)


@frappe.whitelist(methods=["POST"])
def remove_child(box_name, product_qr_serial):
	box = _box(box_name, True)
	_editable(box)
	serial = frappe.get_doc(SERIAL, product_qr_serial, for_update=True)
	serial.check_permission("read")
	name = frappe.db.get_value(CHILD, {"box_qr": box.name,
		"product_qr_serial": serial.name}, "name", for_update=True)
	if not name:
		frappe.throw(_("Child not found in this box."))
	with internal_mutation():
		frappe.delete_doc(CHILD, name, ignore_permissions=True)
		_refresh(box)
		_event(box, "Remove", serial.name)
	return _snapshot(box, True)


@frappe.whitelist(methods=["POST"])
def seal_box(box_name):
	box = _box(box_name, True)
	if box.status != "Sealed":
		_editable(box)
		with internal_mutation():
			_refresh(box)
			if not box.total_qty:
				frappe.throw(_("Cannot seal an empty box."))
			box.status, box.sealed_at = "Sealed", now_datetime()
			box.save(ignore_permissions=True)
			_event(box, "Seal")
	return _snapshot(box, True)


@frappe.whitelist(methods=["POST"])
def reopen_box(box_name):
	box = _box(box_name, True)
	if box.status == "Sealed":
		with internal_mutation():
			box.status, box.sealed_at = "Opened", None
			box.save(ignore_permissions=True)
			_event(box, "Reopen")
	return _snapshot(box, True)


@frappe.whitelist(methods=["GET"])
def print_data(box_name):
	box = _box(box_name)
	if box.status != "Sealed":
		frappe.throw(_("Seal the box before printing."))
	return _snapshot(box)
