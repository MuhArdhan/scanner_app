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

Gudang yang sudah diisi dokumen sumber dipakai untuk mencocokkan scan; field
baris yang kosong diisi dari rak hasil scan. Panduan mendukung gudang berbeda
per baris. Dropdown gudang disembunyikan saat Get Items From aktif.

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
python -m unittest scanner_app.scanner_app.tests.test_rack_scanning scanner_app.scanner_app.tests.test_scan_history -v
```

Tes frontend memakai simulasi DOM/API untuk alur multi-rak, koreksi, pemulihan,
dan putus koneksi. Uji kamera fisik, bunyi/getaran, serta submit stok nyata tetap
memerlukan walkthrough pada perangkat pengguna.
