# PRD: Dukungan Server untuk Client Android (Kiosk)

**Status:** P0 + sebagian P1 **sudah diimplementasi** di branch `feat/dukungan-client-android`
**Tanggal:** 2026-09-04
**Penulis:** Tim Client Android
**Kaitan:** `client-android` — port kiosk dari `client-windows`, sudah menambah
sync offline-first, auth berbasis role, enrollment dari kiosk, dan ML Kit face crop.

### Status implementasi (branch `feat/dukungan-client-android`)

| Req | Status | Berkas |
|---|---|---|
| R-P0-1 perluas `status_kehadiran_otomatis` | ✅ selesai | `app/schemas.py` |
| R-P0-2 `POST /device/{id}/health` | ✅ sudah ada di server (branch device-health) | `app/routers/device.py`, kolom `device.*_jam_lalu`, migrasi `0006_health_device`. Client Android kompatibel apa adanya. |
| R-P1-1 `face_encryption_key` di register | ✅ selesai | `app/routers/device.py` |
| R-P1-2 `GET /auth/roster` | ✅ selesai | `app/routers/login.py` |
| R-P1-4 enroll device-auth | ✅ selesai | `app/routers/siswa.py` (+ `siswa.enrolled_device_id`, migrasi `0007_dukungan_client_android`) |
| `LoginResponse.email` | ✅ selesai | `app/schemas.py`, `app/routers/login.py` |
| R-P1-3 password terpusat (Opsi B) | ⏸️ ditunda — pakai Opsi A (password lokal per device) | — |
| R-P2-* | ⏳ belum | — |

> **Catatan integrasi (2026-09-04):** device-health (R-P0-2) sudah lebih dulu
> diimplementasi di `main` lewat branch device-health — memakai **kolom pada tabel
> `device`** (`jadwal_jam_lalu`, `dispensasi_jam_lalu`, `health_dilaporkan_pada`) +
> endpoint `POST /device/{id}/health` + dashboard `GET /device/status-kesehatan`.
> Rancangan awal PRD ini (tabel `device_health` append-only terpisah) **dibatalkan**
> supaya tidak ada dua sistem paralel. Body health dari client Android adalah
> superset — server mengabaikan field yang tidak dipakainya, bukan menolak batch.

Test: `tests/test_dukungan_client_android.py` — `pytest` hijau.
Migrasi Alembic `0007_dukungan_client_android` (non-destruktif, hanya
`siswa.enrolled_device_id`): `alembic upgrade head`.

---

## 1. Ringkasan

Client Android sudah selesai diselaraskan dengan kontrak server saat ini
(`/absensi/sync`, `/embeddings/sync`, `/jadwal/efektif`, `/dispensasi/aktif`,
`/jadwal/override`, `/device/register`, `/auth/login/google`) dan sudah bisa:

- absensi wajah offline-first + sync (idempoten via `record_id`);
- login Panel Admin berbasis **role** (`admin` / `guru_piket` / `siswa`): online = Google,
  offline = email/NIS + password (hash lokal);
- enrollment wajah dari kiosk terhadap `siswa_id` server;
- kalibrasi ambang match + Fernet key + status kesegaran data.

Dokumen ini merinci **perubahan server** yang dibutuhkan agar semua alur di atas
berjalan penuh (bukan sekadar "tidak error"), diurut prioritas **P0 → P2**.

---

## 2. Analisis Gap (client ↔ server saat ini)

| # | Perubahan / kebutuhan client | Kondisi server sekarang | Dampak | Prioritas |
|---|---|---|---|---|
| G1 | Kirim `status_kehadiran_otomatis` = kategori dispensasi (`IZIN`/`SAKIT`/…) untuk pulang cepat | `AbsensiRecordIn.status_kehadiran_otomatis` = `Literal["NORMAL","TERLAMBAT","PULANG_CEPAT"]` | **422 seluruh batch** kalau ada 1 record pulang-cepat-dispensasi | **P0** |
| G2 | `POST /device/{id}/health` tiap siklus sync (kesegaran data + heartbeat) | Endpoint tidak ada → 404 (di-swallow client) | Dashboard tak bisa pantau device; `last_seen_at` hanya ter-update saat sync data | **P0** |
| G3 | Auth Panel Admin offline pakai email + password | `Guru` tidak punya kolom password; login server = Google-only | Password disimpan **lokal di device** (hash PBKDF2). Perlu keputusan: biarkan lokal, atau server jadi sumber kebenaran | **P1** |
| G4 | Seed akun offline untuk **semua** guru piket/admin (bukan hanya yang pernah login Google di device itu) | Tak ada endpoint daftar guru untuk device | Guru yang belum pernah login Google di device X tidak bisa login offline di device X | **P1** |
| G5 | Auto-isi `FACE_ENCRYPTION_KEY` saat setup device | Key didistribusi manual (copy dari `.env`) | Salah ketik/lupa → semua wajah "tidak dikenali". Sudah ada mitigasi UI ("Tes Face Key") tapi rawan | **P1** |
| G6 | Push enrollment wajah dari kiosk ke server | `POST /siswa/{id}/enroll` hanya terima JWT guru | Enrollment dari kiosk hanya tersimpan lokal; hilang saat cache di-replace sync | **P1** |
| G7 | Tarik jadwal efektif semua kelas sekaligus | Hanya `GET /jadwal/efektif?kelas=X` (1 kelas/request) | Client loop N request tiap sync (11–12 kelas) | **P2** |
| G8 | Delta sync embedding yang benar (termasuk penghapusan) | `diperbarui_sejak` memfilter by `FaceEmbedding.diperbarui_pada`; siswa nonaktif tak muncul di hasil delta | Client tak tahu harus hapus siswa nonaktif kalau pakai delta → client terpaksa full-pull tiap sync | **P2** |
| G9 | Riwayat absensi per siswa (layar role `siswa`) | Tak ada endpoint device-auth untuk ini | Client tampilkan data lokal saja (cukup untuk sekarang) | **P2** |
| G10 | Observabilitas sync per device (untuk dashboard) | `SyncEventLog` dicatat client-side saja; server tak simpan | Admin tak bisa lihat device mana yang gagal sync dari dashboard | **P2** |

---

## 3. Requirements

### P0 — Blocking (harus, sebelum pilot)

#### R-P0-1 · Perluas `status_kehadiran_otomatis` pada intake absensi

**Masalah.** `app/schemas.py`:

```python
class AbsensiRecordIn(BaseModel):
    ...
    status_kehadiran_otomatis: Literal["NORMAL", "TERLAMBAT", "PULANG_CEPAT"] = "NORMAL"
```

Client (Android **dan** Windows) mengirim kategori dispensasi apa adanya saat
`BERHASIL_PULANG_CEPAT` dengan dispensasi aktif — mis. `"SAKIT"`, `"IZIN"`,
`"DISPENSASI_KEGIATAN"`, `"LAINNYA"`. Pydantic memvalidasi **seluruh body** sebelum
handler jalan → **1 record buruk = 422 untuk semua record di batch itu**.

**Perubahan.**

```python
STATUS_KEHADIRAN = Literal[
    "NORMAL", "TERLAMBAT", "PULANG_CEPAT",
    "IZIN", "SAKIT", "DISPENSASI_KEGIATAN", "LAINNYA",
]

class AbsensiRecordIn(BaseModel):
    ...
    status_kehadiran_otomatis: STATUS_KEHADIRAN = "NORMAL"
```

- Kolom DB `Absensi.status_kehadiran_otomatis` sudah `String(20)` → tidak perlu migrasi.
- Samakan juga daftar nilai dengan `ApprovalRequest.status_kehadiran_final`
  (`"NORMAL","TERLAMBAT","PULANG_CEPAT","IZIN","SAKIT"`) — pertimbangkan satu
  `Literal` bersama.
- **Validasi silang** (opsional, di handler, per-record savepoint): kalau
  `status_kehadiran_otomatis in {IZIN,SAKIT,DISPENSASI_KEGIATAN,LAINNYA}` dan
  `type == "PULANG"`, cek ada `Dispensasi` untuk `(siswa_id, tanggal, "PULANG_CEPAT")`.
  Kalau tidak ada → tandai record `status="ditolak_kebijakan"` (bukan gagalkan batch).

**Acceptance.** `POST /absensi/sync` dengan batch berisi record
`{type:"PULANG", status_kehadiran_otomatis:"SAKIT"}` + record normal → HTTP 200,
record SAKIT `status="disimpan"` (jika ada dispensasi) atau `"ditolak_kebijakan"`,
record lain tetap diproses.

---

#### R-P0-2 · Endpoint `POST /device/{device_id}/health`

**Masalah.** Client memanggil ini tiap siklus sync (best-effort, error di-swallow).
Server tidak punya endpoint → 404. `last_seen_at` hanya ter-update saat ada
request data lain.

**Spesifikasi.**

```
POST /device/{device_id}/health
Auth : X-Device-Id + X-Device-Api-Key  (device_id di path HARUS == X-Device-Id)
Body :
{
  "jadwal_jam_lalu": 2.5,          // umur cache jadwal (jam) di device; null bila kosong
  "dispensasi_jam_lalu": 1.0,      // idem
  "embedding_hari_lalu": 0,        // opsional
  "app_version": "1.0.0",          // opsional
  "pending_kirim": 3,              // opsional: absensi lokal belum tersinkron
  "liveness": {                    // opsional: statistik agregat sejak health terakhir
    "total": 40, "lolos": 38, "rata_skor": 0.81
  }
}
Response 200:
{ "status": "ok", "server_time": "2026-09-04T08:00:00Z" }
Error: 401 (device tidak valid / device_id path ≠ header), 404 (device tidak terdaftar)
```

**Perubahan DB.** Tabel baru `device_health` (append-only, buat index by `device_id, dibuat_pada`):

```sql
CREATE TABLE device_health (
    id                  SERIAL PRIMARY KEY,
    device_id           VARCHAR(50) NOT NULL,
    jadwal_jam_lalu     DOUBLE PRECISION,
    dispensasi_jam_lalu DOUBLE PRECISION,
    embedding_hari_lalu INTEGER,
    pending_kirim       INTEGER,
    app_version         VARCHAR(20),
    liveness_json       JSONB,
    dibuat_pada         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Handler juga meng-`update Device.last_seen_at = now()`.

**Dashboard (menyusul, bukan bagian PRD ini).** Kartu "Kesehatan Device" — hijau
kalau semua device health < ambang, kuning kalau ada yang basi.

**Acceptance.** `POST /device/kiosk-01/health` dengan header device valid → 200,
1 baris `device_health` bertambah, `Device.last_seen_at` ter-update.

---

### P1 — Penting (untuk operasional lapangan)

#### R-P1-1 · Distribusi `FACE_ENCRYPTION_KEY` saat registrasi device

**Masalah.** Key Fernet (`settings.face_encryption_key`) sekarang di-copy manual
admin ke tiap device. Salah 1 karakter → seluruh embedding server tak bisa
didekripsi di device itu → semua siswa "tidak dikenali".

**Perubahan.** `POST /device/register` menambah `face_encryption_key` di response
(hanya lewat HTTPS, seperti `api_key` yang "tampil sekali"):

```python
return {
    "device_id": body.device_id,
    "api_key": raw_key,
    "face_encryption_key": settings.face_encryption_key,   # BARU
    "peringatan": "Simpan api_key ini sekarang — tidak akan ditampilkan lagi.",
}
```

- Client Android sudah punya field `FACE_ENCRYPTION_KEY` (BuildConfig / Setup Device /
  Panel Admin) → tinggal auto-isi dari response ini.
- **Catatan keamanan.** Key ini sama untuk semua device (ia adalah kunci enkripsi
  DB, bukan per-device). Mengirimnya per-registrasi = trade-off yang dapat diterima
  (registrasi butuh JWT admin + HTTPS + domain sekolah). **Wajib**: audit-log
  setiap `register` (siapa, device apa, kapan) — endpoint ini membocorkan key.
- Alternatif lebih ketat (P2): key **per-device** (`Device.face_key_hash`/wrapped),
  server re-encrypt embedding saat serve ke device tsb. Jauh lebih mahal — **tidak
  disarankan untuk fase ini**.

**Acceptance.** Response `POST /device/register` memuat `face_encryption_key` yang
identik dengan `.env` server; ter-catat di audit log.

---

#### R-P1-2 · `GET /auth/roster` — daftar akun untuk seed offline device

**Masalah.** Client Android meng-*seed* `akun_lokal` (untuk login offline) **hanya**
dari akun yang pernah login Google di device itu. Guru piket yang belum pernah
menyentuh device X tidak bisa login offline di device X.

**Spesifikasi.**

```
GET /auth/roster
Auth : X-Device-Id + X-Device-Api-Key   (device-auth; read-only)
Response 200:
{
  "server_time": "2026-09-04T08:00:00Z",
  "guru": [
    { "email": "budi@smkn2malinau.sch.id", "nama": "Budi", "role": "admin", "aktif": true },
    { "email": "sri@smkn2malinau.sch.id",  "nama": "Sri",  "role": "guru_piket", "aktif": true }
  ]
}
```

- Hanya `Guru.aktif = true`; sertakan yang nonaktif dengan `"aktif": false` **hanya**
  bila client kirim `?termasuk_nonaktif=1` (agar device bisa mencabut akses lokal).
- **Tidak** mengirim password/hash (lihat R-P1-3).
- Client menarik roster tiap siklus sync → `akun_lokal` selalu mencerminkan
  `Guru.role` server (role = sumber kebenaran server, sesuai keputusan tim).
- Rate-limit ringan; response kecil (< 5 KB untuk sekolah normal).

**Acceptance.** Device memanggil `GET /auth/roster` dengan device-auth → 200 +
seluruh guru aktif. Setelah sync, admin baru yang ditambah di dashboard bisa
login offline (setelah set password lokal) di device mana pun.

---

#### R-P1-3 · (Keputusan) Sumber kebenaran password login offline

Dua opsi. **Rekomendasi: Opsi A untuk fase ini.**

**Opsi A — Password lokal per device (status quo client).**
- Password **tidak** ada di server. Admin/guru men-set password di tiap device saat
  pertama login offline (client sudah handle: flow "Buat Password Offline").
- Kelebihan: tidak ada perubahan server; hash tidak pernah lewat jaringan.
- Kekurangan: password bisa beda antar device; reset = per device.
- Server hanya perlu R-P1-2 (roster) agar akun-nya ter-seed.

**Opsi B — Password terpusat (fase berikutnya).**
- Tambah `Guru.password_hash`, `Guru.password_salt` (PBKDF2-HMAC-SHA256, ≥120k iter).
- `POST /auth/login/password` `{email, password}` → `LoginResponse` (JWT + role).
- `GET /auth/roster` menyertakan `password_hash` + `password_salt` + `password_iter`
  **hanya** untuk device-auth (bukan dashboard) → device verifikasi offline dengan
  algoritma sama.
- Endpoint admin: `POST /guru/{id}/set-password`, `POST /auth/change-password` (self).
- Kelebihan: 1 password, reset terpusat, konsisten dgn dashboard.
- Kekurangan: hash tersebar ke semua device (mitigasi: SQLCipher di device + PBKDF2
  mahal + rotasi saat guru nonaktif).

Client Android sudah kompatibel dengan **keduanya** (PBKDF2 params dibuat cocok:
`PBKDF2WithHmacSHA256`, 120000 iterasi, key 256-bit, salt 16 byte). Bila Opsi B
dipilih, cukup sesuaikan `AuthRepository.loginPassword` untuk juga menerima hash
dari roster.

---

#### R-P1-4 · Enrollment wajah dari kiosk (device-auth)

**Masalah.** `POST /siswa/{id}/enroll` = `require_role("admin","guru_piket")` (JWT).
Kiosk (device-auth) hanya bisa enroll **lokal** → hilang saat `replace` cache sync.

**Spesifikasi.** Perluas endpoint agar menerima device-auth **atau** JWT guru:

```
POST /siswa/{siswa_id}/enroll
Auth : get_guru_or_device
Body : { "embedding": [float, ...], "model_version": "arcface-local" }   (tak berubah)
Perilaku device-auth:
  - siswa_id harus milik siswa aktif;
  - simpan/replace FaceEmbedding (sama seperti guru);
  - siswa.enrolled = true; siswa.tanggal_enrollment = today;
  - siswa.enrolled_oleh = NULL; catat kolom baru siswa.enrolled_device_id = <X-Device-Id>;
Response 200: { "status": "ok", "siswa_id": ..., "enrolled": true, "sumber": "device" }
Error: 401 (auth), 404 (siswa), 422 (embedding < 64 dim)
```

**Perubahan DB.** `ALTER TABLE siswa ADD COLUMN enrolled_device_id VARCHAR(50);`
(nullable, audit).

**Catatan.** Embedding dari device Android sudah lewat crop wajah ML Kit +
normalisasi ArcFace `(x-127.5)/128` — **model_version harus dicatat** supaya
dashboard bisa deteksi campuran versi model (enroll Windows vs Android bisa beda
framing). Pertimbangkan menormalkan `model_version` jadi mis. `"arcface-android-v1"`.

**Acceptance.** Kiosk online → enroll wajah → `GET /embeddings/sync` di device lain
mengembalikan embedding tsb; `siswa.enrolled_device_id` terisi.

---

### P2 — Peningkatan (boleh menyusul)

#### R-P2-1 · `GET /jadwal/efektif/semua` (bulk, device-auth)

```
GET /jadwal/efektif/semua        (device-auth; JWT guru juga boleh)
Response 200:
{
  "tanggal": "2026-09-04",
  "hari": "KAMIS",
  "jadwal": [
    { "kelas": null,        "sumber": "standar",  "jam_masuk": "07:00:00", "jam_pulang": "15:00:00" },
    { "kelas": "XI TKJ 1",  "sumber": "override", "jam_masuk": "07:00:00", "jam_pulang": "12:00:00", "alasan": "..." }
  ]
}
```

- Logika per-kelas identik `GET /jadwal/efektif` (override lokal-tanggal → standar).
- Kelas = semua `DISTINCT siswa.kelas` untuk siswa aktif + baris `kelas = null` (umum).
- Client Android akan pakai ini menggantikan loop N-request. `GET /jadwal/efektif?kelas=`
  tetap dipertahankan (backward-compat Windows).

#### R-P2-2 · Delta sync embedding + tombstone

Agar `?diperbarui_sejak=` aman dipakai (hemat bandwidth di sekolah 1000 siswa):

- Endpoint mengembalikan **juga** daftar penghapusan sejak `diperbarui_sejak`:
  ```json
  { "server_time": "...", "jumlah": 5, "data": [ ... ], "dihapus": [123, 456] }
  ```
- Butuh tabel tombstone `siswa_dihapus(siswa_id, dinonaktifkan_pada)` atau kolom
  `siswa.dinonaktifkan_pada` yang diisi saat `aktif` di-set false.
- Sampai ini ada, client Android **full-pull tiap sync** (sudah diterima untuk fase
  pilot; ~beberapa MB).

#### R-P2-3 · `GET /absensi/siswa/{nis}` (device-auth, riwayat siswa)

```
GET /absensi/siswa/{nis}?limit=60      (device-auth)
Response 200: { "nis": "...", "nama": "...", "records": [ {tanggal, type, jam_aktual, status_kehadiran_final|otomatis, disetujui} ] }
```

Untuk layar "Riwayat Absensi" role `siswa` di client. Prioritas rendah — client
sekarang tampilkan data lokal device.

#### R-P2-4 · Ingest `SyncEventLog` device → dashboard

`POST /device/{id}/sync-log` (device-auth) `{timestamp, status, batch_count,
success, duplicate, fail, error_message, duration_ms}` → tabel `device_sync_log`.
Untuk kartu "Sinkronisasi Device" di dashboard admin (device mana gagal, sejak kapan).

---

## 4. Role & Autentikasi — kesepakatan

| Aspek | Kesepakatan |
|---|---|
| Sumber kebenaran role | **Server** (`Guru.role`). Client tidak menentukan siapa admin. |
| Nilai role | `admin`, `guru_piket` (server). `siswa` = **client-only** (siswa bukan `Guru`); auth siswa lokal, tautan `siswa_id` dari `siswa_cache`. |
| Online | Google Sign-In → `/auth/login/google` → role. |
| Offline | email/NIS + password lokal (Opsi A) — akun ter-seed dari `/auth/register` (yang mendaftarkan device) + `/auth/roster` (R-P1-2). |
| Gating fitur | admin = semua; guru_piket = Sinkronisasi + Jadwal + Data Siswa + Daftar Wajah; siswa = riwayat sendiri. |

**Tidak ada perubahan** pada `/auth/login/google`, `get_current_guru`,
`get_guru_or_device`, `require_role`. `LoginResponse` sudah memuat `nama` + `role`
yang dibutuhkan client. **Saran kecil:** tambahkan `email` di `LoginResponse` agar
client tidak perlu decode ID token sendiri:

```python
class LoginResponse(BaseModel):
    access_token: str
    email: str        # BARU
    nama: str
    role: str
```

---

## 5. Ringkasan Perubahan API

| Endpoint | Jenis | Auth | Prioritas |
|---|---|---|---|
| `POST /absensi/sync` | **ubah** — perluas `Literal` `status_kehadiran_otomatis` | device (header key) | P0 |
| `POST /device/{id}/health` | **baru** | device | P0 |
| `POST /device/register` | **ubah** — response + `face_encryption_key` | JWT admin | P1 |
| `GET /auth/roster` | **baru** | device | P1 |
| `POST /siswa/{id}/enroll` | **ubah** — terima device-auth | JWT guru **atau** device | P1 |
| `POST /auth/login/password` | **baru** (opsional, Opsi B) | publik | P1/P2 |
| `GET /jadwal/efektif/semua` | **baru** | device / JWT | P2 |
| `GET /embeddings/sync` | **ubah** — tambah `dihapus[]` | device | P2 |
| `GET /absensi/siswa/{nis}` | **baru** | device | P2 |
| `POST /device/{id}/sync-log` | **baru** | device | P2 |
| `LoginResponse` | **ubah** — tambah `email` | — | P2 |

---

## 6. Migrasi Database (Alembic)

| Rev | Isi | Prioritas |
|---|---|---|
| `+device_health` | `CREATE TABLE device_health (...)` | P0 |
| `+siswa_enrolled_device` | `ALTER TABLE siswa ADD COLUMN enrolled_device_id VARCHAR(50)` | P1 |
| `+guru_password` *(Opsi B)* | `ALTER TABLE guru ADD COLUMN password_hash VARCHAR(255), password_salt VARCHAR(64), password_iter INTEGER DEFAULT 120000` | P1/P2 |
| `+siswa_tombstone` | `ALTER TABLE siswa ADD COLUMN dinonaktifkan_pada TIMESTAMPTZ` + trigger/handler isi saat `aktif`→false | P2 |
| `+device_sync_log` | `CREATE TABLE device_sync_log (...)` | P2 |

Tidak ada perubahan destruktif. `Absensi.status_kehadiran_otomatis` sudah `String(20)`.

---

## 7. Kompatibilitas Mundur (Client Windows)

- **R-P0-1** (perluas Literal): Windows juga kirim kategori dispensasi → perbaikan
  ini **memperbaiki Windows juga** (kemungkinan bug laten yang sama).
- **R-P0-2** (`/device/health`): Windows sudah memanggil `POST /device/{id}/health`
  (lihat `client-windows/app/api/client.py: lapor_kesehatan`). Endpoint ini
  menghentikan 404 di Windows.
- **R-P1-1** (`face_encryption_key` di register): Windows abaikan field ekstra di
  response (`DeviceRegisterResponse` toleran) — aman.
- **R-P1-4** (enroll device-auth): endpoint tetap terima JWT guru → dashboard &
  Windows-with-JWT tidak berubah.
- **R-P2-1** (`/jadwal/efektif/semua`): endpoint baru, tidak mengganggu
  `GET /jadwal/efektif?kelas=` lama.
- `LoginResponse` + `email`: penambahan field, klien lama abaikan.

---

## 8. Keamanan

1. `POST /device/{id}/health` & semua endpoint device-auth: `device_id` di path
   **wajib** sama dengan `X-Device-Id` terverifikasi; tolak kalau beda (cegah 1
   device melapor atas nama device lain).
2. `GET /auth/roster`: hanya device-auth, **tidak pernah** JWT-less publik, **tidak
   pernah** kirim hash ke dashboard. Log akses.
3. `POST /device/register` + `face_encryption_key`: HTTPS wajib; audit-log setiap
   panggilan (endpoint membocorkan kunci enkripsi DB). Pertimbangkan membatasi
   `register` ke IP sekolah / rate-limit ketat.
4. Enroll device-auth: rate-limit per device (mis. 60/menit) — cegah device
   kompromi menimpa embedding massal.
5. Rotasi: saat `Guru.aktif`→false atau device dinonaktifkan, client harus mencabut
   akses lokal pada sync berikutnya (roster `aktif:false` / device 401).
6. `face_encryption_key` di `.env` server saat ini contoh default
   (`s6wnLcVDT-...`) — **wajib diganti** dengan `Fernet.generate_key()` produksi
   sebelum pilot, dan **tidak boleh berubah** setelah ada embedding tersimpan.

---

## 9. Kriteria Penerimaan (E2E)

1. **Absensi dispensasi**: guru buat dispensasi SAKIT untuk siswa A hari ini →
   siswa A absen PULANG jam 10:00 (sebelum 15:00) di kiosk → sync → server terima
   `status="disimpan"`, `status_kehadiran_otomatis="SAKIT"`. Batch dengan record
   lain tetap sukses.
2. **Device health**: kiosk online 5 menit → minimal 1 baris `device_health`;
   `Device.last_seen_at` ≤ 2 menit lalu.
3. **Face key**: registrasi device baru via Google → APK auto-terisi
   `FACE_ENCRYPTION_KEY` → "Tes Face Key" di Panel Admin = `13/13 cocok`.
4. **Roster / login offline**: admin tambah guru piket baru di dashboard → kiosk
   sync → guru itu (belum pernah sentuh kiosk) bisa login offline setelah set
   password → hanya lihat 4 section yang diizinkan.
5. **Enroll kiosk**: kiosk enroll wajah siswa B online → device lain sync →
   siswa B dikenali; `siswa.enrolled_device_id` terisi.
6. **Regresi Windows**: `pytest` server hijau; alur sync + enroll + jadwal Windows
   tidak berubah.

---

## 10. Urutan Rollout yang Disarankan

1. **Sprint 1 (P0)** — R-P0-1 + R-P0-2 + migrasi `device_health`. Deploy. Client
   Android & Windows langsung berhenti 422/404.
2. **Sprint 2 (P1)** — R-P1-1 (face key di register) + R-P1-2 (`/auth/roster`) +
   R-P1-4 (enroll device-auth) + migrasi `enrolled_device_id`. Client Android
   rilis update yang auto-isi face key & seed roster.
3. **Sprint 3 (P2)** — `/jadwal/efektif/semua`, delta+tombstone embedding,
   `/absensi/siswa/{nis}`, ingest sync-log, `LoginResponse.email`.
4. **Opsi B (password terpusat)** — evaluasi setelah pilot; hanya jika reset
   password per-device jadi beban operasional.
