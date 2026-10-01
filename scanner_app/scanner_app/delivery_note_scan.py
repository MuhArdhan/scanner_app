import frappe
from frappe import _


@frappe.whitelist(methods=["POST"])
def mark_stop_visited(delivery_note: str):
	"""Mark the stop linked to a scanned Delivery Note as visited."""
	delivery_note = str(delivery_note or "").strip()
	if not delivery_note:
		frappe.throw(_("Scan or enter a Delivery Note ID."))

	if not frappe.db.exists("Delivery Note", delivery_note):
		frappe.throw(_("Delivery Note {0} was not found.").format(frappe.bold(delivery_note)))

	note = frappe.get_doc("Delivery Note", delivery_note)
	note.check_permission("read")
	if note.docstatus != 1:
		frappe.throw(_("Only submitted Delivery Notes can be scanned."))
	if not note.delivery_trip:
		frappe.throw(_("This Delivery Note is not assigned to a Delivery Trip."))

	trip = frappe.get_doc("Delivery Trip", note.delivery_trip)
	trip.check_permission("write")
	if trip.docstatus == 0:
		frappe.throw(_("Delivery Trip {0} has not been submitted yet.").format(frappe.bold(trip.name)))
	if trip.docstatus == 2:
		frappe.throw(_("Delivery Trip {0} is cancelled.").format(frappe.bold(trip.name)))

	matching_stops = [stop for stop in trip.delivery_stops if stop.delivery_note == note.name]
	if not matching_stops:
		frappe.throw(_("No stop for this Delivery Note was found in Delivery Trip {0}.").format(frappe.bold(trip.name)))
	if len(matching_stops) > 1:
		frappe.throw(_("This Delivery Note appears more than once in Delivery Trip {0}.").format(frappe.bold(trip.name)))

	stop = matching_stops[0]
	already_visited = bool(stop.visited)
	if not already_visited:
		stop.visited = 1
		trip.save()

	trip_status = frappe.db.get_value("Delivery Trip", trip.name, "status") or trip.status
	return {
		"delivery_note": note.name,
		"trip": trip.name,
		"customer": stop.customer or "",
		"trip_status": trip_status,
		"already_visited": already_visited,
	}
