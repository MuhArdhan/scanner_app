import frappe
from frappe.model.document import Document
from scanner_app.scanner_app.box_packing import require_internal


class WarehouseBoxChild(Document):
	def autoname(self):
		require_internal()
		self.name = f"BOXCH-{self.product_qr_serial}"

	def before_insert(self):
		require_internal()

	def validate(self):
		require_internal()

	def on_trash(self):
		require_internal()

	def before_rename(self, *args, **kwargs):
		frappe.throw("Box children cannot be renamed", frappe.PermissionError)
