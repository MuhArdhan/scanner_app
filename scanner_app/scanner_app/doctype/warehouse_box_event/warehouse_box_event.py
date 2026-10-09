import frappe
from frappe import _
from frappe.model.document import Document
from scanner_app.scanner_app.box_packing import require_internal

class WarehouseBoxEvent(Document):
	def before_insert(self):
		require_internal()

	def validate(self):
		require_internal()
		if not self.is_new():
			frappe.throw(_("Box events are immutable."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Box events cannot be deleted."), frappe.PermissionError)

	def before_rename(self, *args, **kwargs):
		frappe.throw(_("Box events cannot be renamed."), frappe.PermissionError)
