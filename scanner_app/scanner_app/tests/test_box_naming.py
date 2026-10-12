import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class BoxNamingTests(unittest.TestCase):
	def setUp(self):
		self.now = Mock(return_value=datetime(2026, 10, 9, 12))
		self.counters = {}
		def next_number(key, digits):
			self.counters[key] = self.counters.get(key, 0) + 1
			return str(self.counters[key])
		self.series = Mock(side_effect=next_number)
		self.guard = Mock()
		modules = {
			"frappe": types.ModuleType("frappe"),
			"frappe.model.document": types.SimpleNamespace(Document=object),
			"frappe.model.naming": types.SimpleNamespace(getseries=self.series),
			"frappe.utils": types.SimpleNamespace(now_datetime=self.now),
			"scanner_app.scanner_app.box_packing": types.SimpleNamespace(require_internal=self.guard),
		}
		path = Path(__file__).resolve().parents[1] / "doctype/warehouse_box_qr/warehouse_box_qr.py"
		spec = importlib.util.spec_from_file_location("box_naming_under_test", path)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, modules):
			spec.loader.exec_module(module)
		self.controller = module.WarehouseBoxQR

	def create_name(self):
		box = self.controller()
		box.autoname()
		return box.name

	def test_daily_sequence_has_requested_format_without_padding(self):
		self.assertEqual(self.create_name(), "BOX-0910261")
		self.assertEqual(self.create_name(), "BOX-0910262")
		for _ in range(8):
			last = self.create_name()
		self.assertEqual(last, "BOX-09102610")
		self.series.assert_called_with("BOX-091026", 1)

	def test_new_date_starts_at_one(self):
		self.assertEqual(self.create_name(), "BOX-0910261")
		self.now.return_value = datetime(2026, 10, 10, 0)
		self.assertEqual(self.create_name(), "BOX-1010261")

	def test_internal_guard_runs_before_allocating(self):
		self.guard.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			self.create_name()
		self.series.assert_not_called()
