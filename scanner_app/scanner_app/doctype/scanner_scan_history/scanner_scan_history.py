import frappe
from frappe import _
from frappe.model.document import Document


class ScannerScanHistory(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw(_("Scanner history cannot be edited."))
		if not self.flags.from_scanner:
			frappe.throw(_("Scanner history must be created by a scanner transaction."))

	def on_trash(self):
		frappe.throw(_("Scanner history cannot be deleted."))
