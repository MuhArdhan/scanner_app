import frappe
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import now_datetime
from scanner_app.scanner_app.box_packing import require_internal


class WarehouseBoxQR(Document):
	def autoname(self):
		require_internal()
		# A separate native counter per date, without zero-padding the sequence.
		prefix = "BOX-" + now_datetime().strftime("%d%m%y")
		self.name = prefix + getseries(prefix, 1)

	def before_insert(self):
		require_internal()
		self.status, self.total_qty = "Open", 0
		self.packed_by, self.packed_at = frappe.session.user, now_datetime()

	def before_validate(self):
		require_internal()
		self.box_id = self.name
		self.qr_payload = f"BOX:{self.name}"

	def validate(self):
		require_internal()

	def on_trash(self):
		frappe.throw("Boxes cannot be deleted", frappe.PermissionError)

	def before_rename(self, *args, **kwargs):
		frappe.throw("Boxes cannot be renamed", frappe.PermissionError)
