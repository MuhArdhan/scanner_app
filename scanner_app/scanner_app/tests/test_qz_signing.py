import types
import unittest
from unittest.mock import patch

from scanner_app.scanner_app.tests.test_box_packing import frappe_mock
from scanner_app.scanner_app import qz_signing


class QzSigningTests(unittest.TestCase):
	def setUp(self):
		frappe_mock.get_roles.return_value = ['Stock User']

	def test_connection_discovery_requires_stock_role(self):
		frappe_mock.get_roles.return_value = ['Guest']
		with patch.object(qz_signing, '_certificate') as certificate, patch.object(qz_signing, '_sign') as sign:
			with self.assertRaises(PermissionError):
				qz_signing.connection_certificate()
			with self.assertRaises(PermissionError):
				qz_signing.connection_sign('a' * 64)
			certificate.assert_not_called()
			sign.assert_not_called()

	def test_discovery_works_before_a_box_exists(self):
		with patch.object(qz_signing, '_certificate', return_value='PUBLIC CERT'), patch.object(qz_signing, '_sign', return_value='SIGNATURE'), patch.object(qz_signing, '_box') as box:
			self.assertEqual(qz_signing.connection_certificate(), 'PUBLIC CERT')
			self.assertEqual(qz_signing.connection_sign('a' * 64), 'SIGNATURE')
			box.assert_not_called()

	def test_box_print_signing_still_requires_sealed_box(self):
		with patch.object(qz_signing, '_box', return_value=types.SimpleNamespace(status='Open')):
			with self.assertRaises(ValueError):
				qz_signing.certificate('BOX-1')
			with self.assertRaises(ValueError):
				qz_signing.sign('BOX-1', 'a' * 64)

	def test_invalid_signing_request_does_not_read_private_key(self):
		with patch.object(qz_signing, '_files') as files:
			with self.assertRaises(ValueError):
				qz_signing.connection_sign('invalid')
			files.assert_not_called()
