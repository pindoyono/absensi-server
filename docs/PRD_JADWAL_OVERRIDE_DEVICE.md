# PRD: Endpoint `POST /jadwal/override` untuk Device Kiosk (Offline-First)

**Status:** Draft untuk implementasi
**Tanggal:** 2026-08-29
**Penulis:** Tim Client Windows
**Kaitan:** Client `client-windows` fitur "Override Jadwal Lokal" (Opsi C, offline-first)

---

## 1. Latar Belakang & Masalah

Client Windows (kiosk) sudah mengimplementasikan fitur **Override Jadwal Lokal**:
admin dapat membuat override jadwal bertanggal di device saat offline, yang langsung
berlaku untuk absensi siswa (tanpa menunggu server). Saat device online, override
tersebut di-push ke server via `POST /jadwal/override` agar tersebar ke semua device
dan menjadi sumber kebenaran pusat.

**Masalah saat ini:** Endpoint `POST /jadwal/override` di server **sudah ada**, tapi
hanya menerima autentikasi **JWT guru** (`require_role("admin", "guru_piket")`).
Client kiosk mengirim request dengan **Device API Key** (`X-Device-Api-Key` +
`X-Device-Id`), sehingga server membalas **HTTP 403 Forbidden**.

Dampak: override lokal di device berfungsi untuk absensi (offline-first aman), tapi
tidak pernah tersinkron ke server → status di panel admin selamanya "✗ server menolak".

**Tujuan PRD ini:** mengizinkan device kiosk mengirim override jadwal ke server
dengan autentikasi Device API Key, tanpa mengorbankan keamanan (device tidak boleh
sembarangan membuat/mengubah jadwal tanpa batasan).

---

## 2. Analisis Kondisi Server Saat Ini

### 2.1 Endpoint terkait (`app/routers/jadwal.py`)

- `POST /jadwal/override` → auth: `require_role("admin", "guru_piket")` (JWT guru)
- `GET /jadwal/override` → auth: `get_current_guru` (JWT guru)
- `PUT /jadwal/override/{id}` → auth: `require_role("admin", "guru_piket")`
- `DELETE /jadwal/override/{id}` → auth: `require_role("admin", "guru_piket")`
- `GET /jadwal/efektif` → auth: `get_guru_or_device` (JWT **atau** Device API Key)

### 2.2 Model (`app/models.py`)

```python
class JadwalOverride(Base):
    __tablename__ = "jadwal_override"
    id = Column(Integer, primary_key=True)
    tanggal = Column(Date, nullable=False)
    kelas = Column(String(20))
    jam_masuk = Column(Time)
    jam_pulang = Column(Time)
    alasan = Column(Text)
    dibuat_oleh = Column(Integer, ForeignKey("guru.id"))  # NULL untuk device
    dibuat_pada = Column(DateTime, server_default=func.now())
```

Tidak ada kolom `client_id` / `device_id` / `sumber`.

### 2.3 Auth helper (`app/auth.py`)

`get_guru_or_device` sudah mendukung **dua** jenis auth (JWT guru + Device API Key)
dan mengembalikan `Guru | Device`. Ini pola yang harus dipakai untuk endpoint device.

---

## 3. Tujuan Produk

1. Device kiosk dapat mengirim override jadwal ke server saat online.
2. Server menerima override dari device **tanpa** JWT guru.
3. Mencegah duplikasi: device mengirim `client_id` (UUID) sebagai **idempotency key**.
4. Override dari device tercatat sebagai berasal dari device (bukan guru).
5. Override dari device **tetap bisa diedit/dihapus** oleh admin lewat dashboard web.
6. Tidak mengubah perilaku endpoint yang sudah ada untuk JWT guru.

---

## 4. Kebutuhan Fungsional

| ID   | Kebutuhan                                                                                                                                                  |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-1 | `POST /jadwal/override` menerima auth Device API Key (`X-Device-Api-Key` + `X-Device-Id`)                                                                  |
| FR-2 | Device API Key divalidasi via `verify_api_key` (sama seperti `get_guru_or_device`)                                                                         |
| FR-3 | Request body wajib berisi: `tanggal`, `jam_masuk`, `jam_pulang`                                                                                            |
| FR-4 | Request body opsional: `kelas`, `alasan`, `client_id`                                                                                                      |
| FR-5 | `client_id` dipakai sebagai idempotency key — bila sudah ada override dengan `client_id` sama, kembalikan record existing (HTTP 200), jangan buat duplikat |
| FR-6 | Override dari device disimpan dengan `dibuat_oleh = NULL` dan `sumber = 'device'` (kolom baru)                                                             |
| FR-7 | Endpoint tetap menerima JWT guru (backward-compatible) dengan perilaku seperti sekarang                                                                    |
| FR-8 | Validasi: `tanggal` tidak boleh di masa lalu > 0 hari (opsional, lihat FR-9)                                                                               |
| FR-9 | Validasi: `jam_masuk` < `jam_pulang` (seperti endpoint guru)                                                                                               |

---

## 5. Kebutuhan Non-Fungsional

| ID    | Kebutuhan                                                                                                                                    |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-1 | Keamanan: device **hanya** boleh membuat override, tidak mengubah/menghapus override milik device lain atau guru (PUT/DELETE tetap JWT guru) |
| NFR-2 | Audit: setiap override dari device tercatat `device_id` sumbernya di DB                                                                      |
| NFR-3 | Idempotensi: retry dari client (tiap siklus sync) tidak menambah baris                                                                       |
| NFR-4 | Response time < 500ms (seperti endpoint lain)                                                                                                |
| NFR-5 | Tidak merusak kontrak API yang sudah dipakai dashboard web                                                                                   |

---

## 6. Desain Solusi

### 6.1 Perubahan Skema DB (`app/models.py` + Alembic migration)

Tambah kolom ke `JadwalOverride`:

```python
client_id = Column(String(36), unique=True, nullable=True, index=True)  # UUID idempotency key dari device
device_id = Column(String(50), nullable=True)  # device_id sumber (bukan FK, device bisa dihapus)
sumber = Column(String(10), nullable=False, default="guru")  # 'guru' | 'device'
```

Migration Alembic baru: `add client_id, device_id, sumber to jadwal_override`.

### 6.2 Endpoint Baru / Modifikasi (`app/routers/jadwal.py`)

Pisah handler menjadi dua dependency auth:

```python
class JadwalOverrideDeviceIn(BaseModel):
    tanggal: date
    jam_masuk: time
    jam_pulang: time
    kelas: Optional[str] = None
    alasan: Optional[str] = None
    client_id: Optional[str] = None  # UUID idempotency key

@router.post("/override")
def create_jadwal_override(
    body: JadwalOverrideDeviceIn,
    db: Session = Depends(get_db),
    auth: Guru | Device = Depends(get_guru_or_device),
):
    # Idempotensi: cek client_id
    if body.client_id:
        existing = db.query(JadwalOverride).filter(
            JadwalOverride.client_id == body.client_id
        ).first()
        if existing:
            return existing  # 200, tidak buat duplikat

    if body.jam_masuk >= body.jam_pulang:
        raise HTTPException(status_code=400, detail="jam_masuk harus < jam_pulang")

    is_device = isinstance(auth, Device)
    row = JadwalOverride(
        tanggal=body.tanggal,
        kelas=body.kelas,
        jam_masuk=body.jam_masuk,
        jam_pulang=body.jam_pulang,
        alasan=body.alasan,
        client_id=body.client_id,
        device_id=auth.device_id if is_device else None,
        sumber="device" if is_device else "guru",
        dibuat_oleh=None if is_device else auth.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
```

**Catatan:** `get_guru_or_device` mengembalikan `Guru | Device`. Cek tipe dengan
`isinstance(auth, Device)` untuk menentukan sumber.

### 6.3 Client (`client-windows`) — sudah siap

Client sudah mengirim:

```
POST /jadwal/override
X-Device-Id: <device_id>
X-Device-Api-Key: <api_key>
X-Signature / X-Timestamp: <HMAC>   # dari _add_auth_headers
Content-Type: application/json

{
  "tanggal": "2026-08-29",
  "jam_masuk": "09:00:00",
  "jam_pulang": "13:00:00",
  "kelas": "XI",
  "alasan": "Ujian sekolah",
  "client_id": "e010d98f-..."   # UUID idempotency key
}
```

Tidak perlu perubahan client. Setelah endpoint server diperbaiki, status di panel
admin akan berubah otomatis dari "✗ server menolak" → "✓ di server".

---

## 7. Alur (Sequence)

```
Device (offline)          Server                    Dashboard Web
     |                       |                            |
     |-- buat override ------| (simpan lokal)            |
     |                       |                            |
[online]                    |                            |
     |-- POST /jadwal/-------|                            |
     |   override            |                            |
     |   (Device API Key)    |-- cek client_id? ---------|
     |                       |   ada -> return 200       |
     |                       |   tidak -> insert         |
     |<-- 200 OK ------------|   (sumber='device')       |
     |                       |                            |
     |                       |<-- admin edit/delete -----|
     |                       |    (JWT guru, PUT/DELETE) |
```

---

## 8. Kasus Uji (Test Cases)

| TC    | Deskripsi                           | Input                                  | Ekspektasi                                                        |
| ----- | ----------------------------------- | -------------------------------------- | ----------------------------------------------------------------- |
| TC-1  | Device kirim override valid         | Device API Key + body lengkap          | 200, `sumber='device'`, `client_id` tersimpan                     |
| TC-2  | Device kirim ulang `client_id` sama | Device API Key + `client_id` existing  | 200, **tidak** ada baris baru                                     |
| TC-3  | Device tanpa `client_id`            | Device API Key                         | 200, baris baru (client_id NULL)                                  |
| TC-4  | Device dengan API Key salah         | X-Device-Api-Key invalid               | 401                                                               |
| TC-5  | Device dengan API Key non-aktif     | Device.aktif=False                     | 401                                                               |
| TC-6  | JWT guru kirim override             | Bearer token guru_piket                | 200, `sumber='guru'`, `dibuat_oleh=guru.id` (backward-compatible) |
| TC-7  | jam_masuk >= jam_pulang             | Device API Key                         | 400                                                               |
| TC-8  | Tanpa auth sama sekali              | -                                      | 401                                                               |
| TC-9  | Admin edit override dari device     | PUT /jadwal/override/{id} JWT admin    | 200, berubah                                                      |
| TC-10 | Admin hapus override dari device    | DELETE /jadwal/override/{id} JWT admin | 200, terhapus                                                     |

---

## 9. Risiko & Mitigasi

| Risiko                                  | Dampak               | Mitigasi                                                              |
| --------------------------------------- | -------------------- | --------------------------------------------------------------------- |
| Device sembarangan buat banyak override | Spam jadwal          | NFR-1: device hanya POST, tidak PUT/DELETE; admin tetap kontrol penuh |
| `client_id` collision antar device      | Override tertimpa    | UUID v4 (collision ~0); `client_id` unique index                      |
| Device dihapus dari server              | `device_id` dangling | `device_id` bukan FK, nullable — aman                                 |
| Breaking change dashboard web           | Regresi              | Handler JWT guru dipertahankan persis; hanya tambah branch device     |

---

## 10. Rencana Implementasi (Checklist)

- [ ] 1. Tambah kolom `client_id`, `device_id`, `sumber` ke `JadwalOverride` model
- [ ] 2. Buat Alembic migration untuk 3 kolom baru
- [ ] 3. Modifikasi `POST /jadwal/override` pakai `get_guru_or_device` + branch device/guru
- [ ] 4. Tambah logika idempotensi `client_id`
- [ ] 5. Tambah validasi `jam_masuk < jam_pulang`
- [ ] 6. Tulis test TC-1 s.d TC-10 (pytest, `tests/test_jadwal_override_device.py`)
- [ ] 7. Update `docs/API_CONTRACT.md` — tambah contoh request device
- [ ] 8. Deploy ke staging, verifikasi client Windows status berubah "✓ di server"

---

## 11. Definisi Selesai (DoD)

- [ ] Semua TC-1 s.d TC-10 lolos di CI
- [ ] Device Windows bisa push override → status panel admin "✓ di server"
- [ ] Dashboard web tetap bisa CRUD override seperti sebelumnya
- [ ] Migration Alembic tereksekusi tanpa data hilang di DB produksi
- [ ] Dokumentasi `API_CONTRACT.md` diperbarui

---

## 12. Catatan untuk Client

Client `client-windows` **tidak perlu diubah** untuk PRD ini. Setelah server
deploy perubahan di atas, sync worker akan otomatis push ulang override lokal
yang sebelumnya "✗ server menolak" (karena `terkirim` sudah ditandai 1, perlu
**reset flag** — lihat catatan di bawah).

**Aksi tambahan client (opsional, pasca-deploy server):**
Override yang statusnya sudah `ditolak` tidak akan di-retry (by design). Setelah
server fix, admin perlu hapus + buat ulang override lokal, ATAU jalankan script
reset:

```sql
UPDATE jadwal_override_lokal SET terkirim = 0, status_push = 'pending', pesan_push = NULL
WHERE status_push = 'ditolak';
```

Script ini bisa dijalankan sekali lewat menu "Reset status push" di panel admin
(opsional, tidak wajib untuk PRD server).
