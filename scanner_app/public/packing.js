/* Single 60x40 mm at 203 dpi (8 dots/mm). No stock or child-QR generation. */

((root) => {
  /**
   * Encodes string into ZPL Hex format (_HH) for UTF-8 support (^FH).
   */
  const encodeHexZpl = (value) => {
    const text = String(value ?? '');
    return Array.from(new TextEncoder().encode(text))
      .map((byte) => '_' + byte.toString(16).padStart(2, '0'))
      .join('');
  };

  /**
   * Formats date string 'YYYY-MM-DD' into 'DD-MM-YY'.
   */
  const formatShortDate = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''));
    return match ? `${match[3]}-${match[2]}-${match[1].slice(-2)}` : '-';
  };

  /**
   * Prepares the content dictionary from box data.
   */
  const content = (box) => {
    const isMixedReceipt = box.receipt_dates?.length > 1;
    const receiptValue = box.receipt_unknown
      ? '-'
      : isMixedReceipt
      ? 'MIXED'
      : formatShortDate(box.receipt_date);

    const expiryValue = box.expiry_unknown
      ? '-'
      : formatShortDate(box.earliest_expiry);

    return {
      name: box.item_name || '-',
      sku: `SKU : ${box.item_code || '-'}`,
      qty: `ISI : ${box.total_qty || 0} ${box.label_uom || '-'}`,
      receipt: `RCP : ${receiptValue}`,
      expiry: `EXP : ${expiryValue}`,
      id: box.box_id || 'BELUM DIBUAT',
    };
  };

  // Estimate occupancy of proportional printer font 0, not characters per line.
  // This changes only following-field positions; ^FB still wraps the original name.
  // Ratios are deterministic on desktop/mobile, but printer font metrics may differ.
  const nameLineCount = (value, width = 225, fontWidth = 29) => {
    const clean = String(value ?? '').replace(/[\r\n]/g, ' ');
    let estimatedWidth = 0;
    for (const char of clean) {
      let ratio = 0.56;
      if (/\s/.test(char)) ratio = 0.28;
      else if (/[ilI.,'!:;|]/.test(char)) ratio = 0.28;
      else if (/[frt()\[\]]/.test(char)) ratio = 0.38;
      else if (/[MWmw@%]/.test(char)) ratio = 0.95;
      else if (/[A-Z]/.test(char)) ratio = 0.72;
      else if (char.codePointAt(0) > 127) ratio = 1;
      estimatedWidth += fontWidth * ratio;
    }
    // One-dot bold overlay and a small safety margin near the wrap boundary.
    return estimatedWidth + 5 <= width ? 1 : 2;
  };

  /**
   * Generates the ZPL string matching the reference layout image.
   */
  const zpl = (box) => {
    // 1. Validation
    const isValidQr = /^BOX:BOX-[A-Za-z0-9-]+$/.test(box.qr_payload);
    if (box.status !== 'Sealed' || !isValidQr || !box.total_qty) {
      throw new Error('Seal a nonempty box before printing');
    }

    /**
     * Internal helper to create bold text using 1-dot overprint overlay.
     */
    const renderField = (x, y, text, size = 23, width = 230, lines = 1, align = 'L') => {
      const cleanText = String(text ?? '').replace(/[\r\n]/g, ' ');
      const hexData = encodeHexZpl(cleanText);
      const fontHeight = size;
      const fontWidth = Math.max(1, size - 3);

      const buildCommand = (posX) =>
        `^FO${posX},${y}^A0N,${fontHeight},${fontWidth}^FB${width},${lines},0,${align}^FH_^FD${hexData}^FS`;

      // Overprint 1 dot to the right for extra bold effect (matching the image font)
      return `${buildCommand(x)}\n${buildCommand(x + 1)}`;
    };

    const labelText = content(box);
    // Follow estimated name height while retaining the original two-line ^FB.
    const skuY = 70 + 32 * nameLineCount(labelText.name) + 13;

    // Dynamic Font Size for Box ID to fit inside the 200-dot QR column width
    const rawIdLength = String(box.box_id).length;
    const calculatedSize = Math.floor(200 / rawIdLength) + 4;
    const idFontSize = Math.min(26, Math.max(14, calculatedSize));

    // =========================================================================
    // EXACT ZPL LAYOUT MATCHING THE IMAGE (480 x 320 dots / 60 x 40 mm)
    // =========================================================================
    const zplCommands = [
      '^XA',
      '^CI28',
      '^PW480',
      '^LL320',
      '^LH0,0',
      '^LS0',

      // --- 1. SISI KIRI: QR CODE & BOX ID ---
      // QR Code (Magnification 7) - 20 dots lower, approximately 17% larger.
      `^FO35,70^BQN,2,9^FH_^FDQA,${encodeHexZpl(box.qr_payload)}^FS`,

      // Box ID di Bawah QR Code (Center Aligned)
      renderField(25, 265, box.box_id, idFontSize, 200, 1, 'C'),

      // --- 2. SISI KANAN: DETAIL PRODUK ---
      // Format: renderField( X, Y, Teks, Font, Width, Lines, Align )
      renderField(250, 70, labelText.name, 32, 225, 2, 'L'),
      renderField(250, skuY,       labelText.sku,     24, 225, 1, 'L'),
      renderField(250, skuY + 40,  labelText.qty,     24, 225, 1, 'L'),
      renderField(250, skuY + 80,  labelText.receipt, 24, 225, 1, 'L'),
      renderField(250, skuY + 120, labelText.expiry,  24, 225, 1, 'L'),

      '^XZ\n',
    ];

    return zplCommands.join('\n');
  };

  const PackingLabel = { zpl, content };
  root.PackingLabel = PackingLabel;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = PackingLabel;
  }
})(typeof window !== 'undefined' ? window : globalThis);
