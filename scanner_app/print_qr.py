from io import BytesIO

import pyqrcode


def delivery_note_qr(value: str) -> str:
	"""Render a compact, square QR SVG containing a Delivery Note ID."""
	if not value:
		return ""

	qr = pyqrcode.create(str(value))
	with BytesIO() as output:
		qr.svg(output, scale=2, background="#ffffff", module_color="#000000")
		svg = output.getvalue().decode("utf-8")

	# Embed SVG directly so print CSS cannot stretch an image across the metadata column.
	return svg.split("?>", 1)[-1].strip()
