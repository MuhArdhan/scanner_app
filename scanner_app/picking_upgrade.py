"""Scanner-owned Pick List fields and Desk progress indicator."""

import frappe


FIELD_SPECS = [
	{
		"dt": "Pick List", "fieldname": "custom_picking_status", "label": "Picking Status",
		"fieldtype": "Select", "options": "Not Picked\nPartially Picked\nPicked",
		"default": "Not Picked", "read_only": 1, "no_copy": 1,
		"insert_after": "status", "in_list_view": 1, "in_standard_filter": 1,
		"module": "Scanner App",
		"description": "Picking progress saved by Scanner App. Separate from the native document status.",
	},
	{
		"dt": "Pick List", "fieldname": "custom_scanner_pick_state", "label": "Scanner Pick State",
		"fieldtype": "Long Text", "read_only": 1, "hidden": 1, "no_copy": 1,
		"insert_after": "custom_picking_status", "module": "Scanner App",
	},
]

PL_STATUS_SCRIPT = """// scanner_app — Pick List picking progress in the form header.
(function () {
    const colors = {"Not Picked": "gray", "Partially Picked": "orange", "Picked": "green"};
    frappe.ui.form.on("Pick List", {
        refresh(frm) {
            if (!["Stock User", "Stock Manager", "System Manager"].some(role => frappe.user.has_role(role))) return;
            const toolbar = frm.toolbar;
            if (!toolbar || typeof toolbar.set_indicator !== "function") return;
            if (!toolbar.__scanner_picking_indicator) {
                const original = toolbar.set_indicator;
                toolbar.set_indicator = function () {
                    original.apply(this, arguments);
                    const doc = frm.doc;
                    if (frm.is_new() || doc.__unsaved || doc.docstatus === 2) return;
                    if (doc.docstatus === 1 && doc.status !== "Open") return;
                    const status = doc.custom_picking_status;
                    if (colors[status]) frm.page.set_indicator(__(status), colors[status]);
                };
                toolbar.__scanner_picking_indicator = true;
            }
            toolbar.set_indicator();
        },
        custom_picking_status(frm) {
            if (frm.toolbar) frm.toolbar.set_indicator();
        }
    });
})();
"""


def apply():
	# Adopt the existing fields in place: never delete their stored scan data.
	for spec in FIELD_SPECS:
		name = frappe.db.get_value("Custom Field", {"dt": spec["dt"], "fieldname": spec["fieldname"]}, "name")
		if name:
			field = frappe.get_doc("Custom Field", name)
			if any(field.get(key) != value for key, value in spec.items()):
				field.update(spec)
				field.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Custom Field", **spec}).insert(ignore_permissions=True)

	name = "scanner-app-pick-list-indicator"
	values = {"dt": "Pick List", "view": "Form", "enabled": 1, "script": PL_STATUS_SCRIPT, "module": "Scanner App"}
	if frappe.db.exists("Client Script", name):
		script = frappe.get_doc("Client Script", name)
		if any(script.get(key) != value for key, value in values.items()):
			script.update(values)
			script.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": "Client Script", "name": name, **values}).insert(ignore_permissions=True)

	# Retire only our previous installation, leaving other warehouse scripts alone.
	legacy = "warehouse-app-w38-pick-list-indicator"
	if frappe.db.exists("Client Script", legacy):
		script = frappe.get_doc("Client Script", legacy)
		if script.dt == "Pick List" and "warehouse_app W38" in (script.script or ""):
			frappe.delete_doc("Client Script", legacy, ignore_permissions=True)
	frappe.clear_cache(doctype="Pick List")
