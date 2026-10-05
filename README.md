### Scanner App

Scanner for QRCode

PWA tersedia di `/scanner/`. Pilih **Stock Entry**, lalu pilih Material Receipt,
Material Issue, atau Material Transfer, perusahaan, dan gudang. Scan barcode Item,
nomor serial, nomor batch, atau kode gudang seperti pada scanner native ERPNext,
periksa jumlah, lalu pilih **Selesai · Submit Stock Entry**. Dokumen
Stock Entry langsung disubmit dan dapat dibuka dari tautan hasil. Halaman
Delivery Note lama tetap tersedia di `/scan-dn`.

Tombol di kanan atas mengganti tema terang/gelap dan menyimpan pilihan di browser.

Setiap scan barang menambah 1 pada UOM baris, seperti scanner native. Barcode
dengan UOM pada master Item memakai UOM tersebut. Kode Item biasa perlu
didaftarkan sebagai barcode jika ingin dipindai. Detail serial/batch yang
dibutuhkan harus terpindai sebelum submit dokumen.

Kamera terbuka dalam popup scan. Setelah menekan **Selesai**, pengguna kembali
ke daftar barang untuk meninjau jumlah dan submit. Input kode manual
tidak tersedia di alur Stock Entry.

Tombol **Get Items From** di bagian atas membuka modal untuk memilih Material
Request, BOM, Purchase Invoice, Transit Entry, atau Expired Batches sesuai hak
akses pengguna. Saat item diambil, jenis transaksi, perusahaan, dan gudang yang
tersedia pada dokumen sumber otomatis mengisi formulir Stock Entry. Jenis
transaksi dipilih di modal untuk BOM dan Purchase Invoice karena dokumen itu
dapat dipakai untuk beberapa jenis transaksi. Gudang yang terisi otomatis dapat
diganti; pilihan baru diterapkan ke baris hasil scan seperti pada formulir native.
Daftar sumber menjadi panduan: jumlah scan ditampilkan per item dan baris
tercentang setelah jumlahnya terpenuhi. Hasil scan memakai UOM dari baris sumber,
termasuk saat barcode item memiliki UOM lain. Stock Entry dari sumber baru dapat disubmit
setelah seluruh target scan cocok; field relasi dari mapper native ERPNext
tetap dibawa ke Stock Entry.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app scanner_app
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/scanner_app
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
