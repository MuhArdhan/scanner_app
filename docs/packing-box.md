# Packing Box — scan first

1. Open `/scanner/#packing` and scan registered Product QR labels (camera or keyboard Enter).
2. Review the pending product list, Item, number of unique children, and batch count. Remove mistaken scans locally.
3. Confirm **Selesai & Cetak QR Box**. Only now does `finish_packing` allocate the mother ID, insert memberships and audit events, seal the box, and return its snapshot.
4. Send one 60 × 40 mm mother label at 203 dpi (480 × 320 dots, QR on the left) directly from the phone browser to QZ Tray on the selected PC, then to its USB printer. Packing baru resets the local list, not a saved box.

Label layout: QR at left, full Box ID centered below it; product name, SKU, ISI (unique child count in pcs), RCP and EXP at right. Dates use DD-MM-YY. RCP is resolved from the submitted Purchase Receipt linked to each Product QR, not the packing date. Different source receipt dates print MIXED; missing/unreadable source receipts print `-`. EXP is the earliest Batch expiry when all child expiry dates are known; otherwise `-`. Batch detail remains in the application rather than printed on this layout.

One Product QR represents one physical unit. A box must contain one Item; mixed batches are permitted. Stock and original Product QR records are never changed.

## Pending data and concurrency

Pending scans are stored in browser localStorage, not a box or inventory reservation. Server validation during each scan does not allocate a mother. At finalization all payloads are revalidated and serials locked in stable order; a child already packed elsewhere causes the entire finalization to fail. Local counts are previews, not trusted inputs.

A unique `Warehouse Box QR.request_key` allows retries of the same finalization to return the saved box. Failed finalization preserves the pending list and key. Successful finalization clears the pending list before printing; print failure cannot create another box. Empty lists, repeated child payloads, and mixed Items are rejected before box insertion. `create_box` no longer creates empty boxes.

## Verification

Run:

```sh
python3 -m unittest scanner_app.scanner_app.tests.test_box_packing scanner_app.scanner_app.tests.test_qz_signing -v
node --test scanner_app/scanner_app/tests/scanner-routing.test.cjs scanner_app/tests/test_packing_zpl.js scanner_app/tests/packing-flow.test.cjs scanner_app/tests/remote-qz.test.cjs
```

Tests use mocked Frappe and browser APIs. Live concurrent-session verification, browser layout verification and physical QZ printing are still pending.

## Migration — 2026-10-09

Migrated `development.localhost` successfully after database backup `20261009_105509-development_localhost-database.sql.gz`. Cleared site cache. Read-only checks confirmed all three Warehouse Box tables belong to Scanner App, the `request_key` field exists, and `finish_packing` / `validate_scan` import successfully. No packing records or stock transactions were created during these checks.

## Direct HP → remote QZ Tray → USB printer

### Local desktop testing

Packing Box → Pengaturan printer → **PC ini — QZ Tray lokal** connects only to `localhost`. On an HTTP page it uses local WS (default 8182); on HTTPS it uses local WSS (default 8181). Run QZ Tray on the same computer as the browser, click Hubungkan & Cari Printer, then select BP-TR110. No LAN IP or phone certificate installation is needed for local HTTP testing. An HTTPS page cannot use insecure WS; local WSS still needs a trusted localhost certificate. Camera scanning requires a secure context (HTTPS or a browser-recognized localhost origin).

Local and remote printer settings are stored separately. Legacy settings without a mode remain remote, preserving the working phone configuration. New configurations default to local desktop. Switching modes closes a mismatched active QZ connection before connecting to the intended computer. The packing request UUID also supports browsers where `crypto.randomUUID` is unavailable, using cryptographic random bytes instead.

### Remote printing from a phone

Print Station, its page, queue API, job DocType and related tests were removed at the user's request. No database tables/print records are dropped by this code change. This direct transport introduces no new schema.

Configure the PC before using the phone:

1. Install/run QZ Tray and the printer driver, using 60 × 40 mm media at 203 dpi.
2. Use a fixed LAN IP or a hostname resolvable by the phone, e.g. `192.168.1.5` or `printer-pc.local`.
3. Configure QZ for remote clients and create a WSS TLS certificate whose SAN covers that exact IP/hostname. The default localhost certificate will not match a remote IP. For QZ 2.2+ on Windows, the official instructions use an elevated Command Prompt:

```bat
cd "%PROGRAMFILES%\QZ Tray"
qz-tray-console.exe certgen --hosts "localhost;localhost.qz.io;192.168.1.5"
```

Restart QZ after certificate generation. Copy the public TLS root certificate (`root-ca.crt`, QZ Advanced → Troubleshooting → Browse Shared Folder) to trusted phone devices and install/trust it according to the OS. A publicly/organizationally trusted TLS certificate is another option. Mobile browser compatibility and local-network access policies must be verified on the actual device; this implementation does not bypass TLS validation, recommend insecure browser flags, or silently downgrade to WS.

4. Allow only the chosen WSS TCP port (default 8181) through the PC firewall on the trusted LAN / private profile. Do not disable the firewall or expose QZ to the internet. Wi-Fi client isolation / guest networks can prevent access even on the same SSID. Keep QZ running and the computer awake; no browser Print Station page is required.
5. On the phone open Packing Box → **Pengaturan printer · QZ lokal / LAN**, choose **PC lain melalui LAN — WSS**, enter the PC IP/hostname without a URL/path, set its WSS port, then **Hubungkan & Cari Printer**. Select BP-TR110 from the printers installed on that PC. Settings are stored per browser/device, not on the server.
6. Scan products, review, then **Selesai & Cetak QR Box**. The sealed box is saved first; its authoritative snapshot is fetched and sent directly through QZ. If printing fails, the box remains saved. Reprint is explicit and asks the operator to inspect physical labels first.

Signing certificate/key files in `sites/<site>/private/qz_signing/` authorize QZ messages and are **different** from the PC's WSS TLS certificate. The server private key must never be copied to the phone. Discovery certificate/signing endpoints require Stock User/Stock Manager/System Manager; box-specific signing additionally requires a readable sealed box. These roles are trusted printing operators; QZ origin approval on the PC should remain enabled.

The existing local `/assets/warehouse_app/js/qz-tray.js` library is reused, without modifying warehouse_app. Remote transport uses only the configured WSS host/port with no localhost/WS fallback. Local mode uses loopback only and selects WS/WSS according to the page protocol. Neither mode automatically retries printing or uses a server queue. A connection targeting another PC/protocol is explicitly disconnected before switching. Only the selected printer is used, not the default printer.

QZ success means the print request was accepted, not proof that a label physically exited the printer. Network failure after sending can also mean the label was printed: inspect the printer before explicit reprint. There is no offline delivery/retry feature.

Local validation: 14 Python + 34 Node tests pass, including receipt-date permissions, 60 × 40 label content, discovery authorization, local HTTP WS / HTTPS WSS, preserved legacy remote settings, mode switching, exact remote WSS configuration, printer selection, and no automatic reprint on transport failure. Site cache was cleared on `development.localhost`; no new migration was run (no schema added). References: https://qz.io/docs/print-server and https://qz.io/docs/signing . PC/firewall/phone certificate configuration has not been changed automatically. The user confirmed mobile connectivity works; physical verification of this revised label layout and local desktop printing remains pending. No commit/push performed.
