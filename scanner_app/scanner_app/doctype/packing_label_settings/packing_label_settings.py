from frappe.model.document import Document


class PackingLabelSettings(Document):
	def validate(self):
		import json
		from scanner_app.scanner_app.packing_layout import validate_layout
		self.layout_json = json.dumps(validate_layout(self.layout_json or {}))
