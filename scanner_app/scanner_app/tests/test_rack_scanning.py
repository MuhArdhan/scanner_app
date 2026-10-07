"""Regression checks for rack verification before native document submission."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scanner_app.scanner_app import pick_list_scan, stock_entry_scan


class RackScanningTests(unittest.TestCase):
	def test_rack_qr_must_match_document_warehouse(self):
		full_name = "GBJ-R02-S02-B02 - ROPI"
		with (
			patch.object(stock_entry_scan, "_check_warehouse") as check,
			patch.object(stock_entry_scan.frappe, "db", SimpleNamespace(exists=lambda *args: False)),
			patch.object(stock_entry_scan.frappe, "get_list", return_value=[SimpleNamespace(name=full_name)]),
			patch.object(stock_entry_scan.frappe, "throw", side_effect=ValueError),
			patch.object(stock_entry_scan, "_", side_effect=lambda text: text),
		):
			self.assertEqual(stock_entry_scan.verified_rack("GBJ-R02-S02-B02", "ROPI", full_name), full_name)
			with self.assertRaises(ValueError):
				stock_entry_scan.verified_rack("GBJ-R02-S02-B02", "ROPI", "GBJ-R01-S01-B01 - ROPI")
			with self.assertRaises(ValueError):
				stock_entry_scan.verified_rack("", "ROPI")
			check.assert_called_with(full_name, "ROPI")

	def test_lookup_item_resolves_rack_qr_without_company_suffix(self):
		with (
			patch.object(stock_entry_scan, "_find_product_label", return_value=None),
			patch.object(stock_entry_scan, "scan_barcode", return_value={}),
			patch.object(stock_entry_scan, "_rack_warehouse_name", return_value="GBJ-R01-S01-B01 - ROPI") as resolve,
		):
			self.assertEqual(stock_entry_scan.resolve_item("GBJ-R01-S01-B01", "ROPI"), {
				"warehouse": "GBJ-R01-S01-B01 - ROPI",
			})
			resolve.assert_called_once_with("GBJ-R01-S01-B01", "ROPI")

	def test_pick_list_fills_blank_warehouse_from_rack_scan(self):
		row = SimpleNamespace(
			name="row-1", idx=1, item_code="ITEM-1", warehouse="", serial_no=None, batch_no=None,
			meta=SimpleNamespace(has_field=lambda field: False),
		)
		doc = SimpleNamespace(
			name="PL-001", company="ROPI", locations=[row], docstatus=0,
			submit=Mock(),
		)
		guide = [{"name": "row-1", "item_code": "ITEM-1", "warehouse": "", "batch_no": "",
			"stock_qty": 1, "conversion_factor": 1}]
		with (
			patch.object(pick_list_scan.frappe, "has_permission", return_value=True),
			patch.object(pick_list_scan.frappe, "db", SimpleNamespace(get_value=lambda *args, **kwargs: SimpleNamespace(modified="v1", docstatus=0))),
			patch.object(pick_list_scan, "_draft", return_value=doc),
			patch.object(pick_list_scan, "_guide", return_value=guide),
			patch.object(pick_list_scan, "_get_item", return_value=SimpleNamespace(has_batch_no=False, has_serial_no=False)),
			patch.object(pick_list_scan, "resolve_item", return_value={"item_code": "ITEM-1"}),
			patch.object(stock_entry_scan, "_rack_warehouse_name", side_effect=lambda code, company: code),
			patch.object(stock_entry_scan.frappe, "throw", side_effect=ValueError),
			patch.object(stock_entry_scan, "_", side_effect=lambda text: text),
		):
			result = pick_list_scan.submit_draft("PL-001", "v1", [
				{"row_name": "row-1", "code": "BARCODE-1", "qty": 1, "source_rack_code": "GBJ-R02-S02-B02"},
			])
			self.assertEqual(result["name"], "PL-001")
			self.assertEqual(row.warehouse, "GBJ-R02-S02-B02")
			doc.submit.assert_called_once()
			doc.submit.reset_mock()
			guide[0]["warehouse"] = "GBJ-R01-S01-B01"
			with self.assertRaises(ValueError):
				pick_list_scan.submit_draft("PL-001", "v1", [
					{"row_name": "row-1", "code": "BARCODE-1", "qty": 1, "source_rack_code": "GBJ-R02-S02-B02"},
				])
			doc.submit.assert_not_called()

	def test_transfer_rejects_unscanned_target_before_writing(self):
		company = SimpleNamespace(check_permission=Mock())
		with (
			patch.object(stock_entry_scan, "_require_stock_entry_access"),
			patch.object(stock_entry_scan.frappe, "db", SimpleNamespace(exists=lambda *args, **kwargs: True)),
			patch.object(stock_entry_scan.frappe, "get_doc", return_value=company),
			patch.object(stock_entry_scan.frappe, "new_doc") as new_doc,
			patch.object(stock_entry_scan, "_get_item", return_value=SimpleNamespace(name="ITEM-1", stock_uom="Nos")),
			patch.object(stock_entry_scan, "_conversion_factor", return_value=1),
			patch.object(stock_entry_scan, "_rack_warehouse_name", side_effect=lambda code, company: code),
			patch.object(stock_entry_scan.frappe, "throw", side_effect=ValueError),
			patch.object(stock_entry_scan, "_", side_effect=lambda text: text),
		):
			doc = new_doc.return_value
			doc.from_warehouse = None
			doc.to_warehouse = None
			with self.assertRaises(ValueError):
				stock_entry_scan.submit_entry("Material Transfer", "ROPI", [{
					"item_code": "ITEM-1", "qty": 1, "uom": "Nos",
					"s_warehouse": "GBJ-R02-S02-B02", "t_warehouse": "GBJ-R03-S01-B01",
					"source_rack_code": "GBJ-R02-S02-B02",
				}])
			doc.insert.assert_not_called()
			doc.submit.assert_not_called()

	def test_get_items_from_does_not_replace_prefilled_source(self):
		doc = SimpleNamespace(from_warehouse="GBJ-R01-S01-B01", to_warehouse="", insert=Mock(), submit=Mock())
		with (
			patch.object(stock_entry_scan, "make_source_doc", return_value=doc),
			patch.object(stock_entry_scan.frappe, "throw", side_effect=ValueError),
			patch.object(stock_entry_scan, "_", side_effect=lambda text: text),
		):
			with self.assertRaises(ValueError):
				stock_entry_scan._submit_source_entry(
					"Material Transfer", "ROPI", [], "Material Request", "MR-001", {},
					"GBJ-R02-S02-B02", "",
				)
			doc.insert.assert_not_called()
			doc.submit.assert_not_called()

	def test_manual_transfer_uses_verified_racks_on_stock_entry_row(self):
		values = []
		doc = SimpleNamespace(
			name="STE-001", docstatus=1, stock_entry_type="Material Transfer",
			from_warehouse=None, to_warehouse=None, set_stock_entry_type=Mock(),
			append=lambda table, row: values.append(row), insert=Mock(), submit=Mock(),
		)
		item = SimpleNamespace(name="ITEM-1", stock_uom="Nos", has_serial_no=False, has_batch_no=False, barcodes=[])
		company = SimpleNamespace(check_permission=Mock())
		with (
			patch.object(stock_entry_scan, "_require_stock_entry_access"),
			patch.object(stock_entry_scan.frappe, "db", SimpleNamespace(exists=lambda *args, **kwargs: True)),
			patch.object(stock_entry_scan.frappe, "get_doc", return_value=company),
			patch.object(stock_entry_scan.frappe, "new_doc", return_value=doc),
			patch.object(stock_entry_scan, "_get_item", return_value=item),
			patch.object(stock_entry_scan, "_conversion_factor", return_value=1),
			patch.object(stock_entry_scan, "_rack_warehouse_name", side_effect=lambda code, company: code),
		):
			result = stock_entry_scan.submit_entry("Material Transfer", "ROPI", [{
				"item_code": "ITEM-1", "qty": 1, "uom": "Nos",
				"s_warehouse": "GBJ-R02-S02-B02", "t_warehouse": "GBJ-R03-S01-B01",
				"source_rack_code": "GBJ-R02-S02-B02", "target_rack_code": "GBJ-R03-S01-B01",
			}])
		self.assertEqual(result["name"], "STE-001")
		self.assertEqual(values[0]["s_warehouse"], "GBJ-R02-S02-B02")
		self.assertEqual(values[0]["t_warehouse"], "GBJ-R03-S01-B01")
		doc.insert.assert_called_once()
		doc.submit.assert_called_once()
