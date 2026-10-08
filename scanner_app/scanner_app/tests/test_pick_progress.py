import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scanner_app.scanner_app import pick_list_scan as api


class PickProgressTests(unittest.TestCase):
	def setUp(self):
		self.row = SimpleNamespace(name="row-1", idx=1, item_code="ITEM-1", warehouse="GUIDE-RACK",
			serial_no=None, batch_no=None, meta=SimpleNamespace(has_field=lambda f: False))
		self.doc = SimpleNamespace(name="PL-1", company="ROPI", locations=[self.row],
			modified="v1", docstatus=0, save=Mock(), submit=Mock())
		self.guide = [{"name": "row-1", "item_code": "ITEM-1", "warehouse": "GUIDE-RACK",
			"stock_qty": 24, "conversion_factor": 12, "uom": "Pack"}]
		self.stack = ExitStack()
		self.addCleanup(self.stack.close)
		self.stack.enter_context(patch.object(api.frappe, "has_permission", return_value=True))
		self.stack.enter_context(patch.object(api.frappe, "db", SimpleNamespace(get_value=lambda *a, **kw:
			SimpleNamespace(modified=self.doc.modified, docstatus=self.doc.docstatus))))
		self.stack.enter_context(patch.object(api.frappe, "throw", side_effect=ValueError))
		self.stack.enter_context(patch.object(api, "_", side_effect=lambda t: t))
		self.draft = self.stack.enter_context(patch.object(api, "_draft", return_value=self.doc))
		self.stack.enter_context(patch.object(api, "_guide", return_value=self.guide))
		self.stack.enter_context(patch.object(api, "verified_rack", side_effect=lambda code, company: code))
		self.stack.enter_context(patch.object(api, "_get_item", return_value=SimpleNamespace(
			has_batch_no=True, has_serial_no=False, stock_uom="Pcs")))
		self.stack.enter_context(patch.object(api, "resolve_item", side_effect=lambda code, company:
			{"item_code": "ITEM-1", "batch_no": "B1", "qr_value": code}))
		self.stock = self.stack.enter_context(patch.object(api, "assert_source_stock"))
		self.history = self.stack.enter_context(patch.object(api, "record_history"))
		self.stack.enter_context(patch.object(api, "draft_payload", side_effect=lambda doc:
			{"picking_status": doc.custom_picking_status, "scans": json.loads(doc.custom_scanner_pick_state)}))

	def scan(self, code="QR-1"):
		return {"row_name": "row-1", "code": code, "qty": 1, "source_rack_code": "ACTUAL-RACK"}

	def test_partial_save_writes_native_quantities_and_canonical_scan_state(self):
		result = api.save_progress("PL-1", "v1", [{**self.scan(), "batch_no": "FORGED", "qr_value": "FORGED"}])
		self.assertEqual(result["picking_status"], "Partially Picked")
		self.assertEqual(result["scans"][0]["batch_no"], "B1")
		self.assertEqual(result["scans"][0]["qr_value"], "QR-1")
		self.assertEqual(self.row.picked_qty, 12)
		self.assertEqual(self.row.warehouse, "ACTUAL-RACK")
		self.assertEqual(self.doc.parent_warehouse, "ACTUAL-RACK")
		self.assertEqual(self.doc.pick_manually, 1)
		self.doc.save.assert_called_once()
		self.doc.submit.assert_not_called()
		self.history.assert_not_called()
		self.stock.assert_called_once_with("ITEM-1", "ACTUAL-RACK", "ROPI", 12, "B1", None)

	def test_complete_save_still_draft_and_undo_resets_status(self):
		result = api.save_progress("PL-1", "v1", [self.scan(), self.scan("QR-2")])
		self.assertEqual(result["picking_status"], "Picked")
		self.assertEqual(self.doc.docstatus, 0)
		result = api.save_progress("PL-1", "v1", [])
		self.assertEqual(result["picking_status"], "Not Picked")
		self.assertEqual(self.row.picked_qty, 0)
		self.assertIsNone(self.row.batch_no)
		self.assertEqual(result["scans"], [])

	def test_partial_submit_rejected_and_complete_submit_keeps_picked_status(self):
		with self.assertRaises(ValueError):
			api.submit_draft("PL-1", "v1", [self.scan()])
		self.doc.submit.assert_not_called()
		api.submit_draft("PL-1", "v1", [self.scan(), self.scan("QR-2")])
		self.assertEqual(self.doc.custom_picking_status, "Picked")
		self.doc.submit.assert_called_once()
		self.history.assert_called_once()

	def test_stale_revision_cannot_overwrite_another_device(self):
		with self.assertRaises(ValueError):
			api.save_progress("PL-1", "old", [self.scan()])
		self.draft.assert_not_called()
		self.doc.save.assert_not_called()

	def test_duplicate_qr_and_missing_stock_do_not_save(self):
		with self.assertRaises(ValueError):
			api.save_progress("PL-1", "v1", [self.scan(), self.scan()])
		self.doc.save.assert_not_called()
		self.stock.side_effect = ValueError("Batch stock missing")
		with self.assertRaises(ValueError):
			api.save_progress("PL-1", "v1", [self.scan()])
		self.doc.save.assert_not_called()

	def test_each_row_must_be_complete_not_just_total_quantity(self):
		second = SimpleNamespace(name="row-2", idx=2, item_code="ITEM-1", warehouse="", serial_no=None, batch_no=None, meta=self.row.meta)
		self.doc.locations.append(second)
		self.guide.append({**self.guide[0], "name": "row-2"})
		result = api.save_progress("PL-1", "v1", [self.scan(), self.scan("QR-2")])
		self.assertEqual(result["picking_status"], "Partially Picked")
		self.assertEqual(second.picked_qty, 0)

	def test_customer_context_handles_multiple_sales_orders(self):
		doc = SimpleNamespace(customer=None, locations=[SimpleNamespace(sales_order="SO-1"), SimpleNamespace(sales_order="SO-2")])
		with patch.object(api.frappe, "get_list", return_value=[
			SimpleNamespace(customer="C1", customer_name="Toko A"),
			SimpleNamespace(customer="C2", customer_name="Toko B")]):
			context = api.customer_context(doc)
			self.assertEqual([row["customer_name"] for row in context["customers"]], ["Toko A", "Toko B"])
			self.assertEqual(context["sales_orders"], ["SO-1", "SO-2"])
