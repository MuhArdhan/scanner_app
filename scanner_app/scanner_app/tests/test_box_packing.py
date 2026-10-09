import unittest
from unittest.mock import Mock, patch
import types
import sys

class FrappeMock:
	def __init__(self):
		self.PermissionError = PermissionError
		self.session = types.SimpleNamespace(user="test@example.com")
		self.db = Mock()
		self.whitelist = lambda **kw: lambda fn: fn
		self._ = lambda text: text
		self.throw = lambda text, exc=ValueError: (_ for _ in ()).throw(exc(text))
		self.get_roles = Mock(return_value=["Stock User"])
		self.get_doc = Mock()
		self.get_all = Mock(return_value=[])
		self.delete_doc = Mock()
		self.has_permission = Mock(return_value=True)
		self.get_list = Mock(return_value=[])

frappe_mock = FrappeMock()
sys.modules['frappe'] = frappe_mock
sys.modules['frappe.utils'] = types.SimpleNamespace(now_datetime=lambda: "2026-10-09 12:00:00")

from scanner_app.scanner_app import box_packing

class BoxPackingTests(unittest.TestCase):
	def setUp(self):
		frappe_mock.get_roles.return_value = ["Stock User"]
		frappe_mock.get_doc.reset_mock()
		frappe_mock.get_all.reset_mock()
		frappe_mock.db.get_value.reset_mock()
		frappe_mock.db.sql.reset_mock()
		frappe_mock.db.sql.side_effect = None
		frappe_mock.db.sql.return_value = []
		
		self.box = types.SimpleNamespace(
			name="BOX-1", box_id="BOX-1", status="Open", item_code=None, item_name=None,
			total_qty=0, batches_summary=None, earliest_expiry=None, notes=None, qr_payload="BOX:BOX-1", modified="1",
			check_permission=Mock(), save=Mock()
		)
		
	def test_require_internal_blocks_direct_calls(self):
		with self.assertRaises(PermissionError):
			box_packing.require_internal()
		with box_packing.internal_mutation():
			box_packing.require_internal()

	def test_receipt_date_comes_from_submitted_source_receipt(self):
		children = [types.SimpleNamespace(product_qr_serial="PQR-1"), types.SimpleNamespace(product_qr_serial="PQR-2")]
		rows = [types.SimpleNamespace(product_qr_serial=c.product_qr_serial, purchase_receipt="PR-1") for c in children]
		pr = types.SimpleNamespace(docstatus=1, posting_date="2026-10-25", has_permission=Mock(return_value=True))
		with patch.object(frappe_mock.db, "table_exists", return_value=True), patch.object(frappe_mock, "get_all", return_value=rows), patch.object(frappe_mock, "get_doc", return_value=pr):
			data = box_packing._receipt_dates(children)
		self.assertEqual(data["receipt_date"], "2026-10-25")
		self.assertEqual(data["receipt_unknown"], 0)

	def test_receipt_metadata_unreadable_is_unknown_not_disclosed(self):
		children = [types.SimpleNamespace(product_qr_serial="PQR-1")]
		rows = [types.SimpleNamespace(product_qr_serial="PQR-1", purchase_receipt="PR-1")]
		pr = types.SimpleNamespace(docstatus=1, posting_date="2026-10-25", has_permission=Mock(return_value=False))
		with patch.object(frappe_mock.db, "table_exists", return_value=True), patch.object(frappe_mock, "get_all", return_value=rows), patch.object(frappe_mock, "get_doc", return_value=pr):
			data = box_packing._receipt_dates(children)
		self.assertIsNone(data["receipt_date"])
		self.assertEqual(data["receipt_unknown"], 1)

	def test_without_receipt_mapping_rcp_is_unknown(self):
		with patch.object(frappe_mock.db, "table_exists", return_value=False):
			data = box_packing._receipt_dates([types.SimpleNamespace(product_qr_serial="PQR-1")])
		self.assertIsNone(data["receipt_date"])
		self.assertEqual(data["receipt_unknown"], 1)
			
	def test_create_box(self):
		with self.assertRaisesRegex(ValueError, "Scan products first"):
			box_packing.create_box()
		frappe_mock.get_doc.assert_not_called()

	def test_scan_only_validates_without_creating_box(self):
		serial = types.SimpleNamespace(name="PQR-1", qr_payload="QR-1", item_code="I-1", batch_no="B-1")
		with patch.object(box_packing, "_serial", return_value=(serial, types.SimpleNamespace(item_name="Bread"), "2027-01-01")):
			frappe_mock.db.get_value.side_effect = None
			frappe_mock.db.get_value.return_value = None
			result = box_packing.validate_scan("QR-1")
			self.assertEqual(result["product_qr_serial"], "PQR-1")
			frappe_mock.get_doc.assert_not_called()

	def test_finish_rejects_empty_duplicate_and_mixed_item_before_creation(self):
		key = "12345678-1234-1234-1234-123456789abc"
		for values in ([], ["QR-1", "QR-1"]):
			with self.assertRaises(ValueError):
				box_packing.finish_packing(values, key)
		serial1 = types.SimpleNamespace(name="PQR-1", item_code="I-1")
		serial2 = types.SimpleNamespace(name="PQR-2", item_code="I-2")
		frappe_mock.db.get_value.side_effect = None
		frappe_mock.db.get_value.return_value = None
		with patch.object(box_packing, "_serial", side_effect=[(serial1, None, None), (serial2, None, None)]):
			with self.assertRaisesRegex(ValueError, "Only one Item"):
				box_packing.finish_packing(["QR-1", "QR-2"], key)
		frappe_mock.get_doc.assert_not_called()

	def test_finish_retry_returns_existing_box(self):
		key = "12345678-1234-1234-1234-123456789abc"
		self.box.owner = frappe_mock.session.user
		serial = types.SimpleNamespace(name="PQR-1", item_code="I-1")
		frappe_mock.db.get_value.side_effect = None
		frappe_mock.db.get_value.return_value = self.box.name
		with patch.object(box_packing, "_serial", return_value=(serial, None, None)), patch.object(box_packing, "_box", return_value=self.box), patch.object(box_packing, "_children", return_value=[types.SimpleNamespace(product_qr_serial="PQR-1")]), patch.object(box_packing, "_snapshot", return_value={"name": self.box.name}):
			self.assertEqual(box_packing.finish_packing(["QR-1"], key)["name"], self.box.name)
		frappe_mock.get_doc.assert_not_called()

	def test_finish_allocates_once_and_seals_mixed_batches(self):
		key = "12345678-1234-1234-1234-123456789abc"
		item = types.SimpleNamespace(item_name="Bread")
		serials = [types.SimpleNamespace(name=f"PQR-{i}", item_code="I-1", batch_no=f"B-{i}") for i in (1, 2)]
		frappe_mock.db.get_value.side_effect = None
		frappe_mock.db.get_value.return_value = None
		created = []
		def get_doc(values):
			created.append(values)
			return types.SimpleNamespace(insert=Mock(return_value=self.box if values["doctype"] == box_packing.BOX else None))
		frappe_mock.get_doc.side_effect = get_doc
		with patch.object(box_packing, "_serial", side_effect=[(s, item, "2027-01-01") for s in serials]), patch.object(box_packing, "_refresh"), patch.object(box_packing, "_snapshot", return_value={"status": "Sealed"}):
			result = box_packing.finish_packing(["QR-2", "QR-1"], key)
		self.assertEqual(result["status"], "Sealed")
		self.assertEqual(self.box.status, "Sealed")
		self.assertEqual(len([d for d in created if d["doctype"] == box_packing.BOX]), 1)
		children = [d for d in created if d["doctype"] == box_packing.CHILD]
		self.assertEqual({d["batch_no"] for d in children}, {"B-1", "B-2"})
		self.assertEqual([d["action"] for d in created if d["doctype"] == box_packing.EVENT], ["Create", "Add", "Add", "Seal"])
		
	def test_add_child_verifies_box_status_and_item(self):
		def db_get_value(doctype, filters, fieldname, **kwargs):
			if doctype == box_packing.SERIAL: return "S001"
			if doctype == box_packing.CHILD: return None
		frappe_mock.db.get_value.side_effect = db_get_value
		
		def get_doc(doctype, name=None, *args, **kwargs):
			if isinstance(doctype, dict):
				doc = types.SimpleNamespace(**doctype)
				doc.insert = Mock()
				return doc
			elif doctype == box_packing.SERIAL:
				return types.SimpleNamespace(item_code="I-1", batch_no="B-1", name="S001", check_permission=Mock())
			elif doctype == box_packing.BOX:
				return self.box
			elif doctype == "Item":
				return types.SimpleNamespace(item_name="Item 1", disabled=0, check_permission=Mock())
			elif doctype == "Batch":
				return types.SimpleNamespace(item="I-1", expiry_date="2027-10-09", check_permission=Mock())
		frappe_mock.get_doc.side_effect = get_doc
		
		def sql_mock(query, args=(), **kwargs):
			if "product_qr_serial=%s" in query:
				return []
			elif "box_qr=%s" in query:
				return [types.SimpleNamespace(batch_no="B-1", expiry_date="2027-10-09", product_qr_serial="S001", item_code="I-1", name="C-1", scanned_at="2026-10-09")]
			return []
		frappe_mock.db.sql.side_effect = sql_mock
		
		box_packing.add_child("BOX-1", "I-1-B-1-S001")
		self.assertEqual(self.box.item_code, "I-1")
		
		self.box.item_code = "I-2"
		with self.assertRaises(ValueError):
			box_packing.add_child("BOX-1", "I-1-B-1-S001")

if __name__ == '__main__':
	unittest.main()
