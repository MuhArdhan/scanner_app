import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from scanner_app.scanner_app import scan_history
from scanner_app.scanner_app.doctype.scanner_scan_history.scanner_scan_history import ScannerScanHistory


class ScanHistoryTests(unittest.TestCase):
	def test_history_uses_server_user_and_does_not_commit_independently(self):
		log = SimpleNamespace(name="LOG-1", flags=SimpleNamespace(), insert=Mock())
		doc = SimpleNamespace(doctype="Stock Entry", name="STE-1", company="ROPI")
		with (
			patch.object(scan_history, "now_datetime", return_value="2026-10-07 10:00:00"),
			patch.object(scan_history.frappe, "session", SimpleNamespace(user="operator@test")),
			patch.object(scan_history.frappe, "get_doc", return_value=log) as get_doc,
			patch.object(scan_history.frappe, "db", SimpleNamespace(commit=Mock())) as db,
		):
			scan_history.record_history(doc, "Material Transfer", [{"qr_values": ["QR-1"]}])
			values = get_doc.call_args.args[0]
			self.assertEqual(values["scanned_by"], "operator@test")
			self.assertEqual(values["reference_name"], "STE-1")
			self.assertEqual(json.loads(values["details"])[0]["qr_values"], ["QR-1"])
			self.assertTrue(log.flags.from_scanner)
			log.insert.assert_called_once_with(ignore_permissions=True)
			db.commit.assert_not_called()

	def test_stock_history_uses_validated_document_values(self):
		row = SimpleNamespace(item_code="ITEM-1", batch_no="B1", serial_no=None, qty=2,
			uom="Box", conversion_factor=12, stock_uom="Nos", s_warehouse="R1", t_warehouse="R2", barcode=None)
		doc = SimpleNamespace(items=[row], purpose="Material Transfer")
		with patch.object(scan_history, "record_history") as record:
			scan_history.record_stock_history(doc, [{"item_code": "FORGED", "qty": 999, "qr_values": ["QR-1"]}], "Material Request", "MR-1")
			details = record.call_args.args[2][0]
			self.assertEqual(details["item_code"], "ITEM-1")
			self.assertEqual(details["stock_qty"], 24)
			self.assertEqual(details["target_warehouse"], "R2")

	def test_operator_cannot_request_other_users_history(self):
		with (
			patch.object(scan_history.frappe, "session", SimpleNamespace(user="operator@test")),
			patch.object(scan_history.frappe, "get_roles", return_value=["Stock User"]),
			patch.object(scan_history.frappe, "get_all", return_value=[]) as get_all,
		):
			data = scan_history.get_history(scope="all", activity="Pick List")
			self.assertFalse(data["can_view_all"])
			self.assertEqual(get_all.call_args.kwargs["filters"], {"scanned_by": "operator@test", "reference_doctype": "Pick List"})

	def test_manager_pagination_and_document_permissions(self):
		rows = [frappe._dict(name=f"L{i}", reference_doctype="Stock Entry", reference_name=f"STE-{i}", details="[]") for i in range(21)]
		with (
			patch.object(scan_history.frappe, "session", SimpleNamespace(user="manager@test")),
			patch.object(scan_history.frappe, "get_roles", return_value=["System Manager"]),
			patch.object(scan_history.frappe, "get_all", return_value=rows) as get_all,
			patch.object(scan_history.frappe, "has_permission", side_effect=lambda *a, **kw: kw["doc"] != "STE-0"),
		):
			data = scan_history.get_history(scope="all", start=20, search="B1")
			self.assertEqual(get_all.call_args.kwargs["filters"], {})
			self.assertTrue(data["has_more"])
			self.assertEqual(data["next_start"], 40)
			self.assertEqual(len(data["rows"]), 19)
			self.assertNotIn("STE-0", [row.reference_name for row in data["rows"]])

	def test_history_rejects_edit_and_delete(self):
		with (
			patch.object(frappe, "throw", side_effect=ValueError),
			patch("scanner_app.scanner_app.doctype.scanner_scan_history.scanner_scan_history._", side_effect=lambda text: text),
		):
			with self.assertRaises(ValueError):
				ScannerScanHistory.validate(SimpleNamespace(is_new=lambda: False))
			with self.assertRaises(ValueError):
				ScannerScanHistory.on_trash(SimpleNamespace())
