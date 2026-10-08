# Alur scan rak di Scanner App

Semua Stock Entry yang tersedia di `/scanner/` memverifikasi rak sesuai peran
baris dokumennya. QR boleh berisi `warehouse_name` seperti `GBJ-R01-S01-B01`
atau ID Warehouse lengkap. Scanner mencari Warehouse aktif pada perusahaan
transaksi dan tetap memeriksa izin pengguna.

| Kegiatan | Urutan |
| --- | --- |
| Pick List | Rak asal → barang |
| Material Issue, Material Consumption for Manufacture, Return Raw Material to Customer, Subcontracting Delivery | Rak asal → barang |
| Material Receipt, Receive from Customer, Subcontracting Return | Barang → rak tujuan |
| Material Transfer, Material Transfer for Manufacture, Send to Subcontractor | Rak asal → barang → rak tujuan |
| Manufacture, Repack | Bahan: rak asal → barang; hasil: barang → rak tujuan |
| Disassemble | Barang yang dibongkar: rak asal → barang; hasil pembongkaran: barang → rak tujuan |

Pada Stock Entry, gudang yang sudah diisi dokumen sumber dipakai untuk mencocokkan scan; field
baris yang kosong diisi dari rak hasil scan. Panduan mendukung gudang berbeda
per baris. Dropdown gudang disembunyikan saat Get Items From aktif.

Pada Pick List, warehouse awal draft hanya menjadi referensi. Rak asal boleh
berbeda; warehouse tiap baris diganti dengan rak yang benar-benar discan saat
submit. Stok item/batch/serial diperiksa di rak hasil scan.
Kolom Warehouse di header juga mengikuti rak hasil scan
jika semua baris memakai satu rak; jika beberapa rak, header dikosongkan dan
warehouse disimpan pada masing-masing baris. Satu baris tetap
menggunakan satu rak dan satu batch; batalkan scan baris tersebut terlebih
dahulu untuk mengganti rak ketika jumlahnya baru sebagian terpenuhi.

Scan barang dalam satu kelompok harus memiliki pasangan rak yang sesuai.
Selesaikan scan rak tujuan sebelum berpindah ke kelompok dengan tujuan lain
atau ke baris yang hanya membutuhkan rak asal. Judul popup kamera mengikuti
tahap scan. Submit memeriksa ulang rak tiap baris di server.

Saat mengambil barang, scanner memeriksa stok item dan batch pada **rak asal
yang discan**, bukan total stok seluruh gudang. Scan ditolak sebelum jumlah
bertambah bila batch tidak ada di rak tersebut atau total scan dalam Stock UOM
melebihi stok fisik. Serial No juga dicocokkan dengan rak asalnya. Pemeriksaan
stok dilakukan lagi ketika submit. Baris penerimaan/hasil yang hanya memiliki
rak tujuan tidak memerlukan stok sebelumnya pada rak tujuan.

Delivery Note di scanner merupakan scan dokumen untuk menandai stop Delivery
Trip sebagai visited, sehingga tidak meminta scan rak.

## Picking Status dan progres Pick List

Pick List memiliki field tambahan **Picking Status** pada Desk dan daftar
scanner: **Not Picked**, **Partially Picked**, atau **Picked**. Status dihitung
dari jumlah masing-masing baris, tanpa kategori kering/beku atau perubahan Item
Master. Status native Draft/Open/Completed tidak diganti.

Setiap scan barang dan pembatalan scan otomatis disimpan ke server. Reload,
ganti dokumen, atau buka dari perangkat lain memuat scan tersimpan beserta
perlindungan QR duplikat. Gunakan **Muat ulang progres** jika dokumen sudah
berubah di perangkat lain. Penyimpanan memeriksa revision `modified` di bawah
row lock, sehingga dua perangkat tidak saling menimpa diam-diam.

Progres sebagian maupun lengkap tetap **Draft** sampai operator menekan Submit.
Submit hanya diperbolehkan ketika seluruh jumlah terpenuhi dan validasi
rak/stok/batch/serial berhasil. Draft yang dikelola scanner memakai native
`pick_manually=1` agar ERPNext tidak menghitung ulang lokasi/baris hasil scan.

Field `custom_picking_status` dan state tersembunyi `custom_scanner_pick_state`
dimiliki scanner_app (`picking_upgrade.apply`, after_install/after_migrate).
Status ini diperbarui oleh scanner; sinkronisasi otomatis dari perubahan Picked
Qty langsung di Desk belum diterapkan. Daftar scanner menampilkan customer dan
Picking Status; customer juga dicari dari Sales Order yang bisa dibaca pengguna.

Daftar scanner memakai nama customer sebagai master yang dapat dibuka. Di
dalamnya ditampilkan Pick List, Picking Status, purpose, perusahaan, referensi
Sales Order dan tombol mulai/lanjutkan picking. Beberapa Pick
List untuk customer yang sama berada dalam satu kelompok. Pick List dengan
beberapa customer ditampilkan sebagai satu kelompok gabungan customer agar
dokumen tidak terduplikasi.

Client Script scanner_app menampilkan Picking Status pada badge header
Desk untuk Stock User/Stock Manager/System Manager. Pada fase picking, badge
adalah Not Picked (gray), Partially Picked (orange), atau Picked (green). Indikator
Not Saved, Cancelled, dan status pengiriman/transfer selanjutnya tetap native.
Field Status di database tidak diubah oleh script tampilan ini.

Migrasi mengadopsi field yang sudah terpasang tanpa menghapus data progres,
dan mengganti indikator lama warehouse_app dengan Client Script scanner_app.

## Daftar sumber Stock Entry

Daftar Get Items From pada Stock Entry juga menggunakan kelompok expandable.
Material Request dikelompokkan menurut customer (jika tersedia), gudang tujuan,
atau gudang asal untuk Material Issue. Detail menampilkan nomor, jenis,
status, perusahaan, tanggal, dan gudang asal/tujuan; tanpa ringkasan barang.
Pilih dokumen pada detail, lalu tekan Get Items. Untuk sumber lain, judul
kelompok mengikuti customer/supplier, gudang, atau jenis dokumen yang tersedia.

## Riwayat scan

Tombol **Riwayat scan** pada `/scanner/` menampilkan catatan server untuk
Stock Entry/Pick List yang berhasil disubmit dan Delivery Note yang berhasil
ditandai. Buka tiap catatan untuk melihat QR/barcode, item, batch/serial, jumlah,
rak asal/tujuan, pengguna, serta tautan dokumen. Pencarian mendukung nomor
dokumen, QR, item, batch, dan rak; tersedia filter aktivitas dan pagination.

Waktu adalah waktu pencatatan server saat transaksi selesai, bukan waktu setiap
pembacaan kamera. Scan yang dibatalkan atau gagal sebelum submit tidak dicatat.
Riwayat dimulai setelah fitur ini dipasang. Riwayat disimpan atomik bersama
transaksi dalam DocType **Scanner Scan History** dan tidak dapat diedit/dihapus
melalui Desk. Operator melihat riwayat sendiri; System Manager dapat memilih
semua pengguna. Akses baca dokumen terkait tetap diperiksa.

Saat deployment, jalankan `bench --site <site> migrate` untuk memasang DocType.

## Koreksi, status, dan pemulihan

- Popup menampilkan tahap aktif beserta rak panduan. Baris dengan jumlah lengkap
  baru ditandai siap submit setelah rak yang diperlukan terverifikasi.
- Stock Entry menyediakan pembatalan aksi scan terakhir (maksimal 30 aksi selama
  halaman terbuka), penggantian rak asal, dan scan ulang tujuan per baris.
  Pick List menyediakan pembatalan scan barang terakhir dan penggantian rak asal.
- Bunyi/getaran berhasil dan gagal berbeda, dan bisa dimatikan pada popup.
  Dukungan bergantung pada browser/perangkat.
- Sesi disimpan di browser per akun. Setelah reload, gunakan **Lanjutkan sesi**
  atau **Hapus sesi**. Pemulihan memeriksa ulang dokumen sumber/pick draft;
  sumber yang berubah atau tidak tersedia tidak dipulihkan. Undo Stock Entry
  tidak disimpan lintas reload; baris masih dapat dihapus atau tujuannya di-scan ulang.
- Jika koneksi terputus saat submit, periksa status dokumen di ERPNext sebelum
  mengirim ulang. Pemulihan sesi bukan mode submit offline.

Verifikasi otomatis:

```sh
node --test scanner_app/scanner_app/tests/rack-workflow.test.cjs
node --test scanner_app/scanner_app/tests/pick-indicator.test.cjs
python -m unittest scanner_app.scanner_app.tests.test_rack_scanning scanner_app.scanner_app.tests.test_scan_history scanner_app.scanner_app.tests.test_pick_progress -v
```

Tes frontend memakai simulasi DOM/API untuk alur multi-rak, koreksi, pemulihan,
dan putus koneksi. Uji kamera fisik, bunyi/getaran, serta submit stok nyata tetap
memerlukan walkthrough pada perangkat pengguna.
