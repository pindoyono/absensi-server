# Dokumentasi Perubahan API & Skema (Update Terbaru)

Dokumen ini merangkum pembaruan struktur database, endpoint baru, dan penyesuaian client untuk Spektrum Keahlian serta relasi siswa.

---

## 1. Perubahan Skema Database

### 1.1 Tabel Baru: Spektrum Keahlian (Kepmendikbudristek No. 244/M/2024)
Struktur normalisasi 3 level hierarki:
- **`bidang_keahlian`**: Level 1 (mis. `Teknologi Informasi`, `Bisnis dan Manajemen`).
  - `id` (SERIAL PRIMARY KEY)
  - `nama` (VARCHAR(100), UNIQUE)
  - `kode` (VARCHAR(10), UNIQUE)
- **`program_keahlian`**: Level 2 (mis. `Pengembangan Perangkat Lunak dan Gim`).
  - `id` (SERIAL PRIMARY KEY)
  - `bidang_id` (INT REFERENCES bidang_keahlian ON DELETE CASCADE)
  - `nama` (VARCHAR(150))
  - `kode` (VARCHAR(10))
- **`konsentrasi_keahlian`**: Level 3 (mis. `Rekayasa Perangkat Lunak`).
  - `id` (SERIAL PRIMARY KEY)
  - `program_id` (INT REFERENCES program_keahlian ON DELETE CASCADE)
  - `nama` (VARCHAR(150))
  - `kode` (VARCHAR(10))
  - `durasi_tahun` (INT, default 3, pilihan 3 atau 4 tahun)

### 1.2 Penyesuaian Tabel `siswa`
- **Kolom baru**: `konsentrasi_id` (INT REFERENCES konsentrasi_keahlian(id), nullable).
- **Perubahan kolom**: `jurusan` diperbesar dari `VARCHAR(50)` menjadi `VARCHAR(150)` untuk menampung nama konsentrasi keahlian lengkap secara backward-compatible.

---

## 2. Endpoint Baru Spektrum Keahlian (`/spektrum`)

Semua endpoint membutuhkan header `Authorization: Bearer <JWT guru/admin>`.

### 2.1 Bidang Keahlian
- `GET /spektrum/bidang` — List semua bidang keahlian.
- `POST /spektrum/bidang` (Admin) — Tambah bidang (`nama`, `kode`).
- `PUT /spektrum/bidang/{id}` (Admin) — Edit bidang.
- `DELETE /spektrum/bidang/{id}` (Admin) — Hapus bidang.

### 2.2 Program Keahlian
- `GET /spektrum/program?bidang_id=...` — List program keahlian (bisa difilter berdasarkan bidang).
- `POST /spektrum/program` (Admin) — Tambah program (`bidang_id`, `nama`, `kode`).
- `PUT /spektrum/program/{id}` (Admin) — Edit program.
- `DELETE /spektrum/program/{id}` (Admin) — Hapus program.

### 2.3 Konsentrasi Keahlian
- `GET /spektrum/konsentrasi?program_id=...&bidang_id=...` — List konsentrasi keahlian.
- `POST /spektrum/konsentrasi` (Admin) — Tambah konsentrasi (`program_id`, `nama`, `kode`, `durasi_tahun`).
- `PUT /spektrum/konsentrasi/{id}` (Admin) — Edit konsentrasi.
- `DELETE /spektrum/konsentrasi/{id}` (Admin) — Hapus konsentrasi.

### 2.4 Tree Struktur Lengkap (Cascading)
- `GET /spektrum/tree` — Mengembalikan struktur hierarki lengkap `Bidang -> Program -> Konsentrasi` dalam format JSON, sangat berguna untuk mengisi dropdown/pencarian di sisi client.

---

## 3. Penyesuaian Endpoint Siswa (`/siswa`)

- `POST /siswa` dan `PUT /siswa/{id}` sekarang mendukung field opsional `konsentrasi_id` (integer) selain `jurusan`.
- Client disarankan mengirim `konsentrasi_id` yang dipilih dari data spektrum agar relasi database tetap ternormalisasi.
