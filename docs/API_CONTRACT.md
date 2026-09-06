# Kontrak API — Panduan Integrasi Client (Windows & Android)

Dokumen ini adalah referensi wajib untuk mengembangkan client Windows (PyQt) dan Android (Kotlin). Semua endpoint di bawah sudah diuji berjalan (lihat catatan verifikasi di tiap bagian). Base URL contoh: `https://absensi.smkxxx.sch.id`.

Dokumentasi interaktif lengkap (coba langsung tiap endpoint) tersedia di `/docs` setelah server jalan.

---

## 1. Autentikasi

Ada **2 jenis autentikasi berbeda** di sistem ini — jangan tertukar:

| Jenis | Dipakai oleh | Cara |
|---|---|---|
| **JWT guru** (Bearer token) | Dashboard web guru piket/admin | Login Google SSO → dapat token → header `Authorization: Bearer <token>` |
| **API key device** | Client Windows/Android (kiosk) | Didapat sekali saat registrasi device → header `X-Device-Api-Key: <key>` |

Client kiosk (Windows/Android) **tidak pernah login sebagai guru** — device punya identitasnya sendiri lewat API key, terpisah dari akun manusia.

### Keputusan keamanan: HMAC `X-Signature` tidak diimplementasikan (Opsi A — status quo)

**Konteks:** PRD observability/degradasi offline-first §5.3 mencatat bahwa client kiosk
mengirim header `X-Signature`/`X-Timestamp` (HMAC), tetapi server tidak pernah
memverifikasinya. Item ini adalah keputusan yang belum diambil.

**Keputusan (2026-08-30): Opsi A — autentikasi cukup API Key saja.**

Alasan:
1. **Transport sudah terproteksi.** Seluruh trafik berjalan di HTTPS (TLS), sehingga
   API key tidak terekspos di jaringan.
2. **API key sudah disimpan sebagai hash.** Server hanya menyimpan `SHA-256(api_key)`
   di kolom `device.api_key_hash` — kebocoran database tidak membocorkan key mentah.
3. **Skema signing client tidak terdokumentasi di repo ini.** Client mengirim
   `X-Signature` dari `_add_auth_headers` (lihat `PRD_JADWAL_OVERRIDE_DEVICE.md` §6.3),
   tetapi string yang di-sign, format timestamp, dan key-nya hanya ada di repo
   `client-windows`. Menerapkan verifikasi dengan skema yang salah akan menolak
   semua device produksi.
4. **Rotasi key tersedia.** Jika key dicurigai bocor, admin bisa
   `POST /device/{device_id}/regenerate-key` — key lama langsung hangus.

Konsekuensi:
- Header `X-Signature` dan `X-Timestamp` yang dikirim client **diabaikan** oleh server
  (tidak diverifikasi, tidak ditolak). Client boleh terus mengirimnya tanpa efek.
- Jika di masa depan dibutuhkan verifikasi HMAC, skema signing harus disepakati dulu
  antara repo client dan server, lalu verifikasi diterapkan bertahap (tolak hanya
  jika header ada tapi tidak valid).

### 1.1 Registrasi device (dilakukan admin, sekali per device)

```
POST /device/register
Authorization: Bearer <JWT admin>
Content-Type: application/json

{
  "device_id": "gerbang-utama-01",
  "nama_lokasi": "Gerbang Utama",
  "platform": "windows"
}
```

Response (**api_key hanya tampil sekali di sini** — simpan di konfigurasi lokal device, misal file config terenkripsi atau Android Keystore):

```json
{
  "device_id": "gerbang-utama-01",
  "api_key": "bWPQ6zMvkPZrutPiOGRogQp2auVGrWo2JBlRz8p5vSs",
  "face_encryption_key": "s6wnLcVDT-5on-ZSWvd9QZcrmLJ1PnYtjFXQZG_lWSw=",
  "peringatan": "Simpan api_key ini sekarang — tidak akan ditampilkan lagi.",
  "claim": {
    "token": "V1StGXR8_Z5jdHi6B-myT...",
    "expires_at": "2026-09-06T08:00:00+08:00",
    "payload": "{\"v\":1,\"server\":\"https://absen.smkn2malinau.sch.id\",\"token\":\"V1StGXR8_Z5jdHi6B-myT...\"}"
  }
}
```

- `face_encryption_key` (Fernet key server, sama dengan yang dipakai `/embeddings/sync`)
  ikut dikirim di sini supaya client auto-isi tanpa distribusi manual
  (`docs/PRD_DUKUNGAN_CLIENT_ANDROID.md` R-P1-1). Field ekstra — client lama abaikan.
  **Server meng-audit-log tiap panggilan** karena endpoint ini membocorkan kunci enkripsi.

✅ Sudah diuji: register device → dapat api_key → dipakai untuk sync, berhasil end-to-end.

### 1.1a Provisioning via QR (opsional — alih-alih salin api_key manual)

Alih-alih menyalin `device_id` + `api_key` ke kiosk, admin bisa menampilkan
**QR** dan kiosk memindainya. QR berisi string JSON `payload`
(`{v, server, token}`); `token` acak 256-bit, **sekali-pakai**, berumur
`TTL_MENIT` (default 60).

**Ambil / regenerasi QR** (dashboard) — selalu membuat token baru, menimpa yang lama:

```
GET /device/{device_id}/claim-qr
Authorization: Bearer <JWT admin / guru_piket>

→ { "device_id": "...", "token": "...", "expires_at": "...", "payload": "{...}" }
```

`POST /device/register` juga mengembalikan blok `claim` yang sama supaya QR
langsung bisa ditampilkan saat device dibuat.

**Kiosk menukar token** (tanpa auth — token itu sendiri buktinya):

```
POST /device/claim
Content-Type: application/json

{ "token": "V1StGXR8_Z5jdHi6B-myT..." }

→ {
    "server": "https://absen.smkn2malinau.sch.id",
    "device_id": "gerbang-utama-01",
    "nama_lokasi": "Gerbang Utama",
    "api_key": "bWPQ6zMvkPZ...",
    "face_encryption_key": "s6wnLcVDT-5on-..."
  }
```

Setelah berhasil, token **langsung hangus** (percobaan kedua → `404`). Token
kedaluwarsa / tidak dikenal → `404`; body tanpa token → `400`. Server
meng-audit-log tiap `claim-qr` dan `claim`.

### 1.1b Ubah metadata device (admin)

```
PATCH /device/{device_id}
Authorization: Bearer <JWT admin>
{ "nama_lokasi": "Gerbang Belakang" }        # atau/plus "platform": "windows" | "android"
```

Hanya field yang dikirim yang diubah. Tidak menyentuh `api_key`, geofencing,
atau status aktif. `nama_lokasi` kosong → `422`; `platform` selain
windows/android → `422`; device tak ada → `404`. Response = objek device
(sama seperti item `GET /device`). Audit-log. Nama baru ikut terkirim saat
kiosk provisioning ulang lewat QR (`POST /device/claim`).

### 1.2 Heartbeat / kesegaran cache device

```
POST /device/{device_id}/health
X-Device-Api-Key: <api_key device>          (device_id di path harus device terdaftar)
{ "jadwal_jam_lalu": 2.5, "dispensasi_jam_lalu": 1.0 }
```
`200 → {"status":"ok", "nama_lokasi": "Gerbang Belakang", "platform": "windows"}`.
Best-effort tiap siklus sync; server memperbarui `Device.last_seen_at` + kolom
kesegaran (dipantau dashboard `GET /device/status-kesehatan`). `nama_lokasi` &
`platform` di response = nilai TERKINI di server → kiosk memakainya untuk
menyegarkan metadata lokalnya tiap sync (admin bisa ubah via `PATCH /device/{id}`).
Client Android boleh mengirim field tambahan (`embedding_hari_lalu`, `pending_kirim`,
`app_version`) — diabaikan server, bukan error. (Fitur ini milik branch device-health;
lihat `PRD-observability-degradasi-offline-first`.)

### 1.3 Roster akun (seed login offline device)

```
GET /auth/roster[?termasuk_nonaktif=1]       (X-Device-Id + X-Device-Api-Key)
→ { "server_time": "...", "guru": [ {email, nama, role, aktif} ] }
```
Client memakai ini men-*seed* `akun_lokal` untuk login offline — role = sumber
kebenaran server. **Tidak** mengirim password/hash. PRD R-P1-2.

### 1.4 Geofencing per device

Membatasi kiosk agar hanya bisa dipakai absen di lokasi fisik tertentu.
**Fail-closed**: device yang BELUM diatur lokasinya (`lokasi_lat`/`lng` NULL)
dianggap TIDAK valid — admin wajib mengatur titik acuan dulu (bagian di
bawah) sebelum device itu bisa dipakai absen. Konsekuensinya: device
manapun yang belum pernah diatur lokasinya (termasuk device lama yang
sudah jalan sebelum fitur ini ada) akan berhenti menerima absensi begitu
kiosk-nya melakukan sync berikutnya, sampai admin mengatur lokasinya.

**Admin mengatur titik acuan** (dashboard web, klik pin di peta):

```
PUT /device/{device_id}/lokasi
Authorization: Bearer <JWT admin>
{ "lat": -3.4295, "lng": 116.4396, "radius_meter": 100 }
```

**Device menarik konfigurasi lokasinya sendiri** (device-auth, bukan admin)
untuk di-cache lokal — dipakai validasi jarak (Haversine) mandiri di client
saat offline, tanpa perlu round-trip ke `POST /lokasi/cek`:

```
GET /device/{device_id}/lokasi
X-Device-Api-Key: <api_key device>

→ { "lokasi_lat": -3.4295, "lokasi_lng": 116.4396, "radius_meter": 100 }
```

Semua field `null` kalau belum diatur admin. Client Android menarik ini
tiap siklus sync (best-effort, sama seperti `POST /lokasi/cek`) dan
meng-cache hasilnya — lihat `GeoOffline.kt` di client-android.

**Kiosk melapor secara berkala** (bukan per-scan absensi — device tidak
berpindah antar scan wajah, dan minta fix GPS tiap scan terlalu lambat untuk
alur pengenalan wajah). Client Android memanggil ini lewat siklus sync
(`SyncService` step 7b), tiap ~15 menit + saat kiosk dibuka:

```
POST /device/{device_id}/lokasi/cek
X-Device-Api-Key: <api_key device>
{ "tersedia": true, "lat": -3.4294, "lng": 116.4397, "akurasi_meter": 8.2, "mock": false }

→ { "valid": true, "alasan": "dalam radius", "jarak_meter": 12.4, "dikonfigurasi": true }
```

`dikonfigurasi` beda dengan `valid`: murni menandai "admin sudah pasang titik acuan untuk device ini", lepas dari hasil cek jarak/mock/dsb saat ini. `false` hanya untuk kasus lokasi belum diatur sama sekali. Dipakai client untuk indikator ikon "lokasi sudah diatur atau belum" tanpa perlu string-matching ke `alasan`.

`tersedia: false` (izin lokasi ditolak / GPS mati) dan `mock: true` (OS
mendeteksi mock-location provider) SELALU menghasilkan `valid: false`,
terlepas dari koordinat yang dikirim.

**Kiosk-lah yang memblokir dirinya sendiri** berdasarkan `valid` di response
ini — server hanya mencatat hasilnya (kolom `lokasi_valid_terakhir` dkk pada
`GET /device`, ditampilkan di dashboard) untuk visibilitas admin, dan tidak
menolak `POST /absensi/sync` berdasarkan geofencing. Satu-satunya jejak
mock di jalur absensi: kalau kiosk sempat membuat record SEBELUM blokir
mock aktif, client mengirim `lokasi_mock: true` di record itu (lihat
bagian 2 `POST /absensi/sync`) — server menyimpan tanda itu dan record
ikut muncul di `GET /absensi/perlu-verifikasi`, tetap **tanpa menolak**.

**Fallback offline:** kalau `POST /lokasi/cek` gagal dihubungi (device
offline), client TIDAK cuma diam memakai status lama selamanya — dia
menghitung sendiri jarak ke titik acuan yang sudah di-cache (dari
`GET /lokasi` di atas) pakai Haversine lokal, dan itulah yang dipakai
memutuskan blokir/tidak sampai online lagi. Hasil offline ini ditandai
`"[offline]"` di teks alasan yang tersimpan lokal (tidak dikirim ke
server — server tidak pernah tahu kiosk sempat menghitung sendiri).
Kalau genuinely belum PERNAH online sama sekali (belum ada konfigurasi
ter-cache), fail-closed default tetap berlaku.

**Batas deteksi GPS palsu — penting untuk dipahami:** flag `mock` bergantung
pada `LocationCompat.isMock()` Android, yang andal mendeteksi pemakaian
fitur "Select mock location app" bawaan Developer Options. Ini BUKAN jaminan
mutlak — di device root dengan modul Xposed/Magisk yang secara spesifik
memalsukan lapisan lokasi sistem, flag ini bisa ikut dipalsukan, dan APK
yang dimodifikasi bisa melewati pengecekan ini sama sekali (pengecekan
berjalan di sisi client, di luar kendali server). Anggap ini pertahanan
lapis-pertama terhadap penyalahgunaan biasa, bukan bukti kriptografis
terhadap penyerang yang punya akses root ke device kiosk itu sendiri.

### 1.5 Login siswa (opsional, dashboard web, role tetap "siswa")

Siswa TIDAK login lewat NIS+password di dashboard web (itu jalur client
Android/offline, terpisah — lihat client-android). Kalau admin mengisi
`email` siswa lewat `POST`/`PUT /siswa`, siswa itu bisa login Google SSO
di dashboard web dengan `POST /auth/login/google` yang sama seperti guru:

```
POST /auth/login/google
{ "google_id_token": "<id_token dari Google Sign-In>" }
```

Server cek `Guru.email` dulu (perilaku lama, tidak berubah); kalau tidak
ketemu, baru cek `Siswa.email`. Response `role` jadi `"siswa"`:

```
→ { "access_token": "...", "email": "budi@sekolah.sch.id", "nama": "Budi", "role": "siswa" }
```

**Akses siswa sangat terbatas** — hanya dua endpoint self-service:
- `GET /siswa/saya` — profil sendiri
- `GET /siswa/saya/absensi` — riwayat absensi sendiri (siswa_id diambil dari
  token, BUKAN dari query param — siswa tidak bisa lihat data siswa lain)

Token siswa ditolak (401) di semua endpoint guru-only (`require_role`,
`get_current_guru`) walau `sub` (id numerik)-nya kebetulan sama dengan id
baris guru lain — dibedakan lewat klaim `"tipe"` di JWT (`"guru"` vs
`"siswa"`), bukan cuma `"role"`. Lihat `app/auth.py` kalau menambah
endpoint self-service siswa baru — pakai `get_current_siswa`, jangan
`get_current_guru`.

---

## 2. Alur Enrollment Wajah

**Penting — keputusan desain:** embedding wajah dihitung **di sisi client** (memakai engine MiniFASNet yang sama dipakai untuk matching harian), server hanya menyimpan hasilnya. Ini supaya model yang dipakai untuk enrollment dan untuk absen harian selalu konsisten.

```
POST /siswa/{siswa_id}/enroll
Authorization: Bearer <JWT admin/guru_piket>   ── ATAU ──   X-Device-Id + X-Device-Api-Key
Content-Type: application/json

{
  "embedding": [0.123, -0.456, ...],   // vector dari engine, minimal 64 nilai
  "model_version": "arcface-android-v1"
}
```

Menerima **device-auth** juga (PRD R-P1-4) — enrollment dari kiosk langsung naik ke
server. Response menyertakan `"sumber": "guru" | "device"`; untuk device,
`siswa.enrolled_device_id` diisi & `enrolled_oleh` = NULL.

Alur di client saat proses enrollment (lihat detail lengkap di dokumen arsitektur bagian 10.2):
1. Ambil 3-5 foto wajah dari sudut berbeda
2. Cek kualitas tiap foto (pencahayaan, wajah tidak terpotong) — di client, sebelum dikirim
3. Generate embedding dari foto-foto tsb (di client)
4. Kirim embedding ke endpoint di atas
5. **Uji langsung**: minta siswa scan di kiosk yang sama, pastikan berhasil dikenali sebelum dianggap selesai

✅ Sudah diuji: endpoint enroll berhasil menyimpan embedding terenkripsi dan set `enrolled=true`.

---

## 3. Sync Embedding ke Cache Lokal Client

Client menarik embedding semua siswa (untuk matching offline) lewat:

```
GET /embeddings/sync?diperbarui_sejak=2026-08-20T00:00:00
X-Device-Id: gerbang-utama-01
X-Device-Api-Key: <api_key device>
```

Response:

```json
{
  "server_time": "2026-08-23T10:00:00",
  "jumlah": 3,
  "data": [
    {
      "siswa_id": 1,
      "nis": "22001",
      "nama": "Ahmad Fauzan",
      "kelas": "XI Elektronika",
      "kelas_id": 4,
      "aktif": true,
      "embedding_encrypted": "gAAAAABm...(hex string)",
      "model_version": "minifasnet-v1",
      "diperbarui_pada": "2026-08-20T08:00:00"
    }
  ]
}
```

> **Normalisasi kelas (migrasi 0012):** server kini menyimpan rombel di tabel
> `kelas` (`siswa.kelas_id` FK). **Kontrak ke client TIDAK berubah** — field
> `kelas` di sini & di `GET /siswa` tetap berisi **nama** kelas (di-compute dari
> relasi). `kelas_id` ditambahkan sebagai info opsional; client boleh
> mengabaikannya. `GET /jadwal/efektif?kelas=<nama>` & `POST /jadwal/override`
> dengan body `{"kelas": "<nama>"}` tetap diterima (server resolve nama→id;
> nama tak dikenal diperlakukan sebagai jadwal sekolah-wide, bukan error).

**Cara pakai di client:**
- Simpan `embedding_encrypted` (hex string) apa adanya ke SQLite lokal (kolom BLOB, decode dari hex dulu).
- **Jangan didekripsi di client dengan key yang sama seperti server** — client seharusnya punya mekanisme dekripsi sendiri yang konsisten (lihat catatan keamanan di bagian 7).
- Panggil endpoint ini secara periodik (misal tiap kali online, atau tiap beberapa jam) dengan `diperbarui_sejak` = waktu sync terakhir, supaya tidak menarik ulang semua data tiap kali.
- Simpan `server_time` dari response sebagai acuan `diperbarui_sejak` untuk sync berikutnya (bukan waktu lokal device, untuk menghindari drift jam).
- **Field `aktif` (PRD_EMBEDDING_SYNC):** jika `aktif == false`, client **wajib menghapus** data siswa dari cache lokal (`siswa_cache` dan `embedding_cache`) berdasarkan `siswa_id` — siswa tersebut sudah dinonaktifkan/dihapus di server dan tidak boleh bisa absen lagi. Jika `aktif == true`, lakukan upsert seperti biasa.

---

## 3a. Retensi Data Wajah (Auto-Expire)

Data wajah (embedding) TIDAK disimpan selamanya. Server membatasi retensi
maksimum **~3 tahun 1 bulan sejak enrollment pertama** (siklus SMK 3 tahun
+ buffer 1 bulan) lewat endpoint yang dipanggil cron OS, bukan manual dari
dashboard:

```
POST /admin/retensi/bersihkan-wajah
X-Retensi-Secret: <RETENSI_CRON_SECRET dari .env>
```

Response:

```json
{
  "status": "ok",
  "dinonaktifkan": 2,
  "dihapus_permanen": 1,
  "siswa_id_dihapus_permanen": [42],
  "batas_umur_hari": 1125
}
```

**Alur dua fase** (aman dipanggil berulang, mis. cron harian):
1. Siswa **aktif** yang embedding-nya sudah lewat umur → dinonaktifkan (`aktif=False`), `FaceEmbedding.diperbarui_pada` di-bump. Efeknya SAMA seperti `DELETE /siswa/{id}` manual: kiosk menerima `aktif: false` di sync berikutnya dan menghapus cache lokalnya (bagian 3 di atas).
2. Siswa yang **sudah nonaktif** (dari fase 1, atau dinonaktifkan admin manual sebelumnya) DAN sudah melewati jeda propagasi 7 hari sejak `diperbarui_pada` → embedding dihapus **permanen** dari database server. Baris `siswa` dan riwayat `absensi` TIDAK ikut terhapus — tetap ada untuk laporan/arsip sekolah.

Jeda 7 hari di fase 2 penting: tanpa itu, kiosk yang sedang offline saat baris dihapus tidak akan pernah menerima sinyal `aktif=false` (barisnya sudah lenyap dari hasil JOIN di `GET /embeddings/sync`), sehingga cache lokalnya jadi yatim selamanya alih-alih terhapus bersih.

**Kalau fase 1 salah menonaktifkan siswa** (mis. siswa program 4 tahun — lihat `KonsentrasiKeahlian.durasi_tahun` — yang seharusnya belum kedaluwarsa tapi flat cutoff 3th1bln tidak membedakan durasi program), pakai:

```
POST /siswa/{siswa_id}/aktifkan
Authorization: Bearer <JWT admin>
```

Mengembalikan `aktif=True`. Kalau embedding-nya belum terlanjur dihapus permanen (masih dalam jeda 7 hari), siswa langsung bisa absen lagi setelah kiosk sync berikutnya (`embedding_tersedia: true`). Kalau sudah terlanjur dihapus, siswa perlu di-enroll ulang wajahnya (`embedding_tersedia: false`) — endpoint `POST /siswa/{id}/enroll` sekarang menerima lagi karena `aktif` sudah `True`.

**Hapus 1 record absensi** (koreksi kesalahan / bersihkan data uji):

```
DELETE /absensi/{record_id}
Authorization: Bearer <JWT admin>          (admin-only; guru piket cuma bisa approve)

→ { "status": "ok", "record_id": "..." }
```

Menghapus permanen. Setelah itu constraint `UNIQUE(siswa_id, tanggal, type)`
bebas lagi → siswa bisa absen ulang untuk slot itu. `404` kalau record tak
ada. Audit-log.

---

**Hapus PERMANEN siswa** (bersihkan data uji — tidak bisa di-undo):

```
DELETE /siswa/{siswa_id}/hard
Authorization: Bearer <JWT admin>

→ { "status": "ok", "siswa_id": 7, "terhapus": {"absensi": 12, "dispensasi": 1, "embedding": 1} }
```

Menghapus baris siswa + SEMUA `absensi`, `dispensasi`, `face_embedding`
miliknya. Beda dengan `DELETE /siswa/{id}` yang cuma menonaktifkan. Audit-log.

### Rekap kehadiran — `tanpa_keterangan_estimasi`

`GET /laporan/rekap` menghitung `tanpa_keterangan_estimasi = (hari sekolah dalam
rentang) − (jumlah record MASUK siswa)`. **Hari sekolah = SENIN–JUMAT**, dikurangi
tanggal yang ditandai libur lewat `JadwalOverride` sekolah-wide (jam kosong).
Akhir pekan & libur nasional (bila di-override) tidak lagi dihitung sebagai alpa.
Untuk libur yang tidak di-input sebagai override, angka masih over-estimate.

**Setup cron** (lihat `docs/DEPLOYMENT.md` bagian retensi): jalankan endpoint ini sekali sehari. Endpoint menolak (503) kalau `RETENSI_CRON_SECRET` belum diisi di `.env` — aman secara default, harus sengaja diaktifkan.

---

## 4. Sync Absensi — Endpoint Paling Kritis

```
POST /absensi/sync
X-Device-Api-Key: <api_key device>
Content-Type: application/json

{
  "records": [
    {
      "record_id": "c99b4ed1-a692-4cad-b304-d0a9b087ad83",
      "siswa_id": 1,
      "tanggal": "2026-08-23",
      "type": "MASUK",
      "jam_aktual": "2026-08-23T07:02:15+08:00",
      "status_kehadiran_otomatis": "NORMAL",
      "catatan": null,
      "device_id": "gerbang-utama-01",
      "lokasi_mock": false
    }
  ]
}
```

**Aturan wajib di sisi client:**
- `record_id` dibuat DI CLIENT saat capture (pakai UUID v4), **bukan** ditunggu dari server. Ini yang membuat retry aman.
- Boleh kirim banyak record sekaligus dalam 1 array (batch) — penting untuk kasus device lama offline lalu online, ada banyak antrian record.
- Kirim ulang record yang gagal sync tanpa mengubah `record_id`-nya — server akan mengenali sebagai retry, bukan data baru.
- `jam_aktual` **wajib datetime penuh** (ISO 8601, `YYYY-MM-DDThh:mm:ss[±zz]`), bukan jam saja.
- `status_kehadiran_otomatis`: `NORMAL` | `TERLAMBAT` | `PULANG_CEPAT` | `IZIN` | `SAKIT`
  | `DISPENSASI_KEGIATAN` | `LAINNYA`. Untuk absen PULANG sebelum jam pulang, kirim
  kategori dispensasi (mis. `SAKIT`) — server cek ada `Dispensasi` aktif; kalau tidak,
  record itu `status="ditolak_kebijakan"` (batch lain tetap diproses). Nilai kategori
  ini dulu memicu **422 seluruh batch** — sekarang diterima (PRD R-P0-1).
- `lokasi_mock` (opsional, default `false`): kirim `true` kalau client mendeteksi
  lokasi perangkat berasal dari mock-location (fake GPS) saat record dibuat.
  Server **tidak menolak** record karena ini — record tetap `disimpan`, hanya
  ditandai `lokasi_mock=true` di DB dan otomatis ikut muncul di
  `GET /absensi/perlu-verifikasi` supaya guru piket meninjaunya. Client lama
  yang tak mengirim field ini tetap kompatibel. (Blokir kiosk saat mock
  terdeteksi tetap tanggung jawab client — lihat bagian 1.4.)

Response:

```json
{
  "total": 1,
  "disimpan": 1,
  "duplikat": 0,
  "gagal": 0,
  "hasil": [
    {"record_id": "c99b4ed1-...", "status": "disimpan", "pesan": null}
  ]
}
```

**Cara client menangani tiap status di `hasil`:**

| Status | Aksi di client |
|---|---|
| `disimpan` | Tandai record lokal `synced = true` |
| `duplikat_diabaikan` | Tandai juga `synced = true` — JANGAN retry lagi, ini bukan error |
| `gagal` | Biarkan `synced = false`, akan dicoba ulang di siklus sync berikutnya |
| `ditolak_kebijakan` | Jangan simpan lokal, jangan retry — absen ditolak server karena di luar jendela waktu (misal absen masuk jam 04:00 padahal baru buka 05:00, atau pulang cepat tanpa dispensasi). Tampilkan pesan ke siswa. |

✅ **Sudah diuji end-to-end lewat HTTP asli**: kirim MASUK pertama → `disimpan`. Kirim MASUK kedua untuk siswa & tanggal sama dengan `record_id` berbeda → otomatis `duplikat_diabaikan`. Ini membuktikan aturan "maksimal 2 record per hari" ditegakkan oleh server, bukan cuma diasumsikan benar dari sisi client.

---

## 5. Jadwal (untuk Menghitung Status Terlambat/Pulang Cepat)

```
GET /jadwal/efektif?kelas=XI%20Elektronika
Authorization: Bearer <JWT>   -- lihat catatan bagian 7 soal auth device vs guru
```

Response memberi jam masuk/pulang yang berlaku HARI INI (sudah menghitung override kalau ada):

```json
{"sumber": "standar", "jam_masuk": "07:00:00", "jam_pulang": "15:00:00"}
```

> Param `kelas` = **nama** rombel (tetap, walau server sudah normalisasi ke
> `kelas_id` — lihat bagian 3). Nama yang tak dikenal server → fallback jadwal
> sekolah-wide (bukan 404/500).

Client harus:
1. Tarik & cache jadwal ini secara berkala (idealnya tiap sync sukses), simpan ke SQLite lokal.
2. Saat offline, pakai jadwal yang di-cache terakhir untuk menghitung `status_kehadiran_otomatis` (`TERLAMBAT` kalau jam_aktual > jam_masuk + toleransi, dst).

---

## 5a. Override Jadwal dari Device Kiosk (Offline-First)

Endpoint `POST /jadwal/override` menerima **dua** jenis autentikasi (lihat PRD `docs/PRD_JADWAL_OVERRIDE_DEVICE.md`):

- **JWT guru** (`Authorization: Bearer <JWT>`, role `admin`/`guru_piket`) — `sumber='guru'`, `dibuat_oleh=guru.id`. Backward-compatible dengan dashboard web.
- **Device API Key** (`X-Device-Id` + `X-Device-Api-Key`) — `sumber='device'`, `dibuat_oleh=NULL`, `device_id` tercatat untuk audit. Device **hanya boleh POST** (create); `PUT`/`DELETE` tetap khusus JWT guru.

### 5a.1 Request dari Device

```
POST /jadwal/override
X-Device-Id: <device_id>
X-Device-Api-Key: <api_key>
Content-Type: application/json

{
  "tanggal": "2026-08-29",
  "jam_masuk": "09:00:00",
  "jam_pulang": "13:00:00",
  "kelas": "XI",
  "alasan": "Ujian sekolah",
  "client_id": "e010d98f-..."   # UUID idempotency key (opsional tapi disarankan)
}
```

- `tanggal`, `jam_masuk`, `jam_pulang` **wajib** untuk device.
- `client_id` dipakai sebagai **idempotency key**: request ulang dengan `client_id` sama mengembalikan record yang sudah ada (HTTP 200) tanpa membuat baris baru — aman untuk retry tiap siklus sync.
- `kelas` = **nama** rombel (opsional; kosong = berlaku semua kelas). Server
  resolve ke `kelas_id`; nama tak dikenal diperlakukan sebagai berlaku semua
  kelas. Dashboard boleh kirim `kelas_id` (int) langsung sebagai gantinya.
- Validasi: `jam_masuk` harus `<` `jam_pulang` (400 kalau melanggar).

Response (200 OK):

```json
{
  "id": 42,
  "tanggal": "2026-08-29",
  "kelas": "XI",
  "jam_masuk": "09:00:00",
  "jam_pulang": "13:00:00",
  "alasan": "Ujian sekolah",
  "dibuat_oleh": null,
  "dibuat_pada": "2026-08-29T10:00:00",
  "client_id": "e010d98f-...",
  "device_id": "<device_id>",
  "sumber": "device"
}
```

### 5a.2 Reset status push (pasca-deploy)

Override lokal di client yang statusnya sudah `ditolak` tidak di-retry (by design). Setelah server diperbaiki, admin jalankan sekali (lewat menu "Reset status push" di panel admin, atau script SQL):

```sql
UPDATE jadwal_override_lokal SET terkirim = 0, status_push = 'pending', pesan_push = NULL
WHERE status_push = 'ditolak';
```

---

## 5b. Dispensasi (Izin Pulang Cepat)

Dispensasi adalah **izin di muka** yang diberikan guru piket **sebelum** siswa absen pulang. Berbeda dengan `status_kehadiran_final` (approve sesudah absen), dispensasi memungkinkan siswa absen PULANG sebelum jam pulang standar.

### 5b.1 Buat / Update Dispensasi

```
POST /dispensasi
Authorization: Bearer <JWT admin atau guru_piket>
Content-Type: application/json

{
  "siswa_id": 1,
  "tanggal": "2026-08-25",
  "jenis": "PULANG_CEPAT",
  "kategori": "SAKIT",
  "alasan": "Demam tinggi, izin pulang ke rumah sakit"
}
```

Response (200 OK):

```json
{
  "id": 12,
  "siswa_id": 1,
  "tanggal": "2026-08-25",
  "jenis": "PULANG_CEPAT",
  "kategori": "SAKIT",
  "alasan": "Demam tinggi, izin pulang ke rumah sakit",
  "dibuat_oleh": 3
}
```

**Catatan:** `UNIQUE (siswa_id, tanggal, jenis)` — 1 siswa cuma bisa punya 1 dispensasi PULANG_CEPAT per hari. Kalau sudah ada, field-nya diupdate (upsert).

### 5b.2 Tarik Dispensasi Aktif (untuk Sync Client)

```
GET /dispensasi/aktif?tanggal=2026-08-25
Authorization: Bearer <JWT guru>
```

Response:

```json
[
  {
    "id": 12,
    "siswa_id": 1,
    "tanggal": "2026-08-25",
    "jenis": "PULANG_CEPAT",
    "kategori": "SAKIT",
    "alasan": "Demam tinggi, izin pulang ke rumah sakit",
    "dibuat_oleh": 3
  }
]
```

Client harus:
1. Panggil endpoint ini tiap siklus sync (mirip jadwal), simpan ke cache lokal `dispensasi_cache`.
2. Saat offline, cek cache lokal sebelum menolak absen PULANG sebelum jam pulang standar.

### 5b.3 Batalkan Dispensasi

```
DELETE /dispensasi/{dispensasi_id}
Authorization: Bearer <JWT admin atau guru_piket>
```

Response: `{"status": "dibatalkan"}`

---

## 5c. Manajemen Kelas (Rombel) — dashboard

Sejak migrasi `0012_kelas_normalisasi`, rombel adalah entitas nyata di tabel
`kelas`. Endpoint ini dipakai dashboard web (menu **Kelas**). Kiosk **tidak
perlu** memakainya — kontrak kiosk tetap berbasis nama kelas (lihat bagian 3).

| Endpoint | Auth | Fungsi |
|---|---|---|
| `GET /kelas` | JWT guru **atau** device | Daftar kelas `[{id, nama, tingkat, konsentrasi_id, wali_id, wali_nama, aktif, jumlah_siswa}]` |
| `POST /kelas` | admin | `{nama, tingkat?, konsentrasi_id?, wali_id?}` — 409 kalau `nama` sudah ada |
| `PUT /kelas/{id}` | admin | partial update (nama/tingkat/konsentrasi_id/wali_id/aktif) |
| `DELETE /kelas/{id}` | admin | **409** kalau masih ada siswa / jadwal yang mereferensikan |
| `GET /kelas/{id}/siswa` | JWT guru **atau** device | siswa di kelas itu `[{id, nis, nama, enrolled}]` |

**Perubahan endpoint existing:**
- `POST /siswa` & `PUT /siswa/{id}`: field `kelas` (string) **diganti** `kelas_id`
  (int, nullable). `SiswaOut` tetap punya `kelas` (nama) **plus** `kelas_id`.
- **`PATCH /siswa/{id}`** (baru, admin) `{"kelas_id": <int|null>}` — pindah rombel
  (drag-and-drop). 422 kalau `kelas_id` tidak ada.
- `GET /siswa`: menerima `?kelas=<nama>` (kompat, di-resolve) **dan** `?kelas_id=<int>`
  (`kelas_id=0` = siswa tanpa rombel).
- Import CSV `POST /siswa/import`: kolom `kelas` → **`kelas_id`** (ID rombel; kosong =
  tanpa rombel; ID tak dikenal → `baris_error`). Template `GET /siswa/template-csv`
  menyertakan baris komentar `# kelas_id <n> = <nama>` (baris `#` diabaikan saat import).
- `GET /guru`: field `kelas_diampu` **dihapus**, diganti `wali_kelas: [<nama>, ...]`
  (read-only, di-derive dari `kelas.wali_id`). Penetapan wali lewat `PUT /kelas/{id}`.

---

## 6. Skenario Error yang Harus Ditangani Client

| Kondisi | HTTP Status | Penanganan client |
|---|---|---|
| Device belum terdaftar/dinonaktifkan | 401 | Tampilkan pesan ke admin, hentikan sync sampai device didaftarkan ulang |
| API key device salah | 401 | Sama seperti di atas — jangan retry otomatis tanpa batas |
| Siswa tidak ditemukan (enroll ke siswa_id invalid) | 404 | Sinkronkan ulang data siswa dari server |
| Server tidak terjangkau (timeout/connection error) | — | Ini kondisi **offline normal**, bukan error aplikasi — simpan lokal, retry nanti sesuai desain offline-first |

---

## 7. Catatan Keamanan untuk Developer Client

- SQLite lokal **wajib dienkripsi** (SQLCipher) — device Windows/Android bisa hilang/dicuri, data 1000 siswa (termasuk embedding wajah) ada di dalamnya.
- API key device disimpan di **Windows Credential Manager** (Windows) atau **Android Keystore** (Android) — jangan hardcode di file config plain text.
- Endpoint `/embeddings/sync` mengirim embedding dalam bentuk `embedding_encrypted` (hasil enkripsi Fernet server) sebagai hex string. **Skema saat ini: client menyimpan bytes terenkripsi ini apa adanya di SQLite, TIDAK didekripsi di client.** Matching wajah di client dilakukan dengan membandingkan embedding hasil capture kamera (belum dienkripsi) terhadap — ini butuh keputusan desain tambahan sebelum implementasi client dimulai:
  - **Opsi A** (lebih sederhana): client juga menyimpan `FACE_ENCRYPTION_KEY` yang sama dengan server (didistribusikan lewat setup device yang aman), dekripsi saat perlu matching, held di memory saja (tidak ditulis ke disk plain).
  - **Opsi B** (lebih aman tapi lebih rumit): server expose endpoint matching (`POST /embeddings/match`) yang menerima embedding hasil capture dan mengembalikan siswa_id yang cocok — TAPI ini butuh koneksi internet, bertentangan dengan syarat "harus bisa matching offline".
  - **Rekomendasi**: pakai Opsi A untuk versi awal (offline-first tetap terpenuhi), key didistribusikan manual saat setup device oleh admin (bukan lewat API), dicatat sebagai keputusan yang perlu di-review ulang kalau nanti threat model berubah.

---

## 8. Ringkasan Alur Lengkap Client (Referensi Cepat)

```
Setup device (sekali):
  1. Admin register device → dapat api_key → simpan aman di device

Startup / berkala saat online:
  2. GET /jadwal/efektif → cache jadwal lokal
  3. GET /embeddings/sync?diperbarui_sejak=... → update cache embedding lokal
  4. GET /dispensasi/aktif?tanggal=hari-ini → update cache dispensasi lokal

Saat siswa scan wajah:
  4. Capture wajah → liveness check → cari embedding cocok dari cache lokal
  5. Cek status hari ini di SQLite lokal (BELUM_ABSEN/SUDAH_MASUK/SELESAI)
  6. Hitung status_kehadiran_otomatis dari jadwal ter-cache
  7. Generate record_id (UUID) → simpan ke SQLite lokal, synced=false
  8. Tampilkan feedback ke siswa (sesuai mockup UI kiosk)

Background sync worker (tiap 30-60 detik jika online):
  9. Ambil semua record synced=false dari SQLite
  10. POST /absensi/sync dengan batch record tsb
  11. Update status lokal sesuai hasil (disimpan/duplikat_diabaikan/gagal)
```
