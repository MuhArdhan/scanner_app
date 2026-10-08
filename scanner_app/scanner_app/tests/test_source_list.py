import unittest
from unittest.mock import patch

import frappe
from scanner_app.scanner_app.stock_entry_source import source_list_detail


class SourceListTests(unittest.TestCase):
	def document(self, request_type, rows, **values):
		return frappe._dict(name="MR-1", material_request_type=request_type, company="ROPI",
			status="Pending", transaction_date="2026-10-08", items=[frappe._dict(row) for row in rows],
			check_permission=lambda permission: None, **values)

	def test_transfer_preserves_multiple_destinations_without_item_summary(self):
		doc = self.document("Material Transfer", [
			{"warehouse": "T1", "from_warehouse": "S"},
			{"warehouse": "T2", "from_warehouse": "S"},
		])
		data = source_list_detail(doc, "Material Request")
		self.assertEqual(data["group_label"], "Tujuan: T1, T2")
		self.assertEqual(data["source_warehouses"], ["S"])
		self.assertEqual(data["target_warehouses"], ["T1", "T2"])
		self.assertNotIn("item_summary", data)

	def test_material_issue_warehouse_is_source_not_destination(self):
		data = source_list_detail(self.document("Material Issue", [{"warehouse": "S"}]), "Material Request")
		self.assertEqual(data["group_label"], "Asal: S")
		self.assertEqual(data["target_warehouses"], [])

	def test_customer_name_lookup_respects_read_permissions(self):
		doc = self.document("Customer Provided", [{"warehouse": "T"}], customer="C1")
		with patch.object(frappe, "has_permission", return_value=False), patch.object(frappe, "get_list") as lookup:
			self.assertEqual(source_list_detail(doc, "Material Request")["group_label"], "C1")
			lookup.assert_not_called()
		with patch.object(frappe, "has_permission", return_value=True), patch.object(frappe, "get_list", return_value=[frappe._dict(customer_name="Toko A")]):
			self.assertEqual(source_list_detail(doc, "Material Request")["group_label"], "Toko A")
