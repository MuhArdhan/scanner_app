"""QZ Tray signing for sealed mother boxes.

Shares site keys; authorization checks box status and user permissions.
Never relies on Purchase Receipt records.
"""
from pathlib import Path
import re

import frappe
from frappe import _
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from scanner_app.scanner_app.box_packing import _box, _require_stock_role


def _files():
	base = Path(frappe.get_site_path("private", "qz_signing"))
	return base / "digital-certificate.txt", base / "private-key.pem"


@frappe.whitelist()
def certificate(box_name):
	box = _box(box_name)
	if box.status != "Sealed":
		frappe.throw(_("Seal the box before printing."))
	return _certificate()


def _certificate():
	cert, _key_path = _files()
	try:
		return cert.read_text(encoding="ascii")
	except (OSError, UnicodeError):
		frappe.throw(_("QZ Tray certificate is not configured on the server."))


@frappe.whitelist(methods=["POST"])
def sign(box_name, request):
	box = _box(box_name)
	if box.status != "Sealed":
		frappe.throw(_("Seal the box before printing."))
	return _sign(request)


@frappe.whitelist()
def connection_certificate():
	"""Authenticated printer discovery before a box exists (no private key returned)."""
	_require_stock_role()
	return _certificate()


@frappe.whitelist(methods=["POST"])
def connection_sign(request):
	# Stock operators are trusted QZ clients; a digest cannot disclose the QZ method.
	# Never expose this endpoint to guests. Keep PC QZ origin approval enabled.
	_require_stock_role()
	return _sign(request)


def _sign(request):
	if not isinstance(request, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", request):
		frappe.throw(_("Invalid QZ Tray signature request format."))
	_cert_path, key_path = _files()
	try:
		private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
	except (OSError, ValueError, TypeError):
		frappe.throw(_("QZ Tray private key is missing or invalid."))
	if not isinstance(private_key, rsa.RSAPrivateKey):
		frappe.throw(_("QZ Tray private key must be an RSA key."))
	import base64
	signature = private_key.sign(request.encode("utf-8"), padding.PKCS1v15(), hashes.SHA512())
	return base64.b64encode(signature).decode("ascii")
