"""Shared Packing Box label calibration. Printer connections remain device-local."""
import json
import math

import frappe
from frappe import _

DOCTYPE = "Packing Label Settings"
DEFAULTS = {
	"width_mm": 60, "height_mm": 40, "offset_x": 0, "offset_y": 0,
	"qr_x": 35, "qr_y": 70, "qr_scale": 9,
	"text_x": 250, "text_y": 70, "text_width": 225, "field_gap": 40,
	"id_x": 25, "id_y": 265, "id_width": 200,
}


def validate_layout(layout):
	if isinstance(layout, str):
		try:
			layout = json.loads(layout)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid label layout."))
	if not isinstance(layout, dict) or set(layout) - set(DEFAULTS):
		frappe.throw(_("Invalid label layout."))
	result = dict(DEFAULTS)
	for key, value in layout.items():
		if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
			frappe.throw(_("Layout values must be finite numbers."))
		if key.endswith("_mm"):
			low, high = 20, 150
		elif key.startswith("offset_"):
			low, high = -100, 100
		elif key == "qr_scale":
			low, high = 1, 10
		elif key in {"text_width", "id_width", "field_gap"}:
			low, high = 1, 1200
		else:
			low, high = 0, 1200
		if not low <= value <= high or (not key.endswith("_mm") and value != int(value)):
			frappe.throw(_("Label layout value out of range: {0}").format(key))
		result[key] = value
	width, height = round(result["width_mm"] * 8), round(result["height_mm"] * 8)
	for prefix in ("qr", "text", "id"):
		if not 0 <= result[prefix + "_x"] + result["offset_x"] < width or not 0 <= result[prefix + "_y"] + result["offset_y"] < height:
			frappe.throw(_("Label element starts outside the paper."))
	for prefix in ("text", "id"):
		if result[prefix + "_x"] + result["offset_x"] + result[prefix + "_width"] > width:
			frappe.throw(_("Text column extends outside the paper."))
	return result


@frappe.whitelist(methods=["GET"])
def get_layout():
	from scanner_app.scanner_app.box_packing import _require_stock_role
	_require_stock_role()
	doc = frappe.get_single(DOCTYPE)
	return {"layout": validate_layout(doc.layout_json or {}), "can_write": bool(frappe.has_permission(DOCTYPE, "write"))}


@frappe.whitelist(methods=["POST"])
def save_layout(layout):
	if not frappe.has_permission(DOCTYPE, "write"):
		frappe.throw(_("Only Stock Manager or System Manager can change the label layout."), frappe.PermissionError)
	doc = frappe.get_single(DOCTYPE)
	doc.layout_json = json.dumps(validate_layout(layout))
	doc.save()
	return {"layout": json.loads(doc.layout_json), "can_write": True}
