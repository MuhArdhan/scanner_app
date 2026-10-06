"""UOM rules shared by manual scans and Get Items From rows."""

import frappe
from frappe import _
from frappe.utils import flt


def conversion_factor(item, uom):
	if uom == item.stock_uom:
		return 1
	factor = next((flt(row.conversion_factor) for row in item.uoms if row.uom == uom), 0)
	if factor <= 0:
		frappe.throw(_("UOM {0} has no conversion factor for item {1}.").format(uom, item.name))
	return factor


def default_inventory_uom(item):
	"""Prefer the current Item field, then older custom fields, then Stock UOM."""
	fields = (
		"custom_default_inventory_unit_of_measure",
		"custom_default_uom",
		"custom_default_uom_warehouse",
	)
	for field in fields:
		uom = item.get(field)
		if not uom:
			continue
		if uom == item.stock_uom or any(row.uom == uom and flt(row.conversion_factor) > 0 for row in item.uoms):
			return uom
		if field == fields[0]:
			frappe.throw(_("Default Inventory UOM {0} is invalid for item {1}.").format(uom, item.name))
	return item.stock_uom
