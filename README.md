# Server Absensi Face Recognition — Fase 1 (Server)

Server pusat (FastAPI + PostgreSQL) untuk sistem absensi offline-first
SMK, ±1000 siswa. **Fase 1 (server) sudah lengkap dan teruji** —
lihat `docs/DEPLOYMENT.md` untuk deploy ke Linux, dan
`docs/API_CONTRACT.md` sebagai panduan wajib sebelum mengembangkan
client Windows/Android.

Untuk detail perubahan terbaru terkait Spektrum Keahlian dan relasi
siswa, lihat `docs/SPEKTRUM_API_UPDATE.md`.

## Status Fase 1

✅ Semua endpoint direncanakan sudah diimplementasikan dan diuji
lewat HTTP asli (bukan cuma unit test) terhadap PostgreSQL nyata:
registrasi device, enrollment wajah, sync absensi dengan verifikasi
anti-duplikasi 2 lapis, jadwal standar & override, laporan/rekap,
autentikasi Google SSO + role-based access.

✅ 8 unit test (pytest) — mencakup skenario dedup, retry, enkripsi
embedding — semua lulus.

✅ Migration Alembic diuji jalan ke Postgres asli (bukan simulasi).

⏳ Belum: dashboard web untuk guru piket (di luar cakupan Fase 1 —
Fase 1 adalah API server saja, dashboard web adalah *consumer* dari
API ini, bisa dikembangkan terpisah memakai kontrak di
`docs/API_CONTRACT.md`).

## Struktur project

```
absensi-server/
├── schema.sql                   # skema database final
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── .env.example
├── alembic/                     # migration database
├── deploy/
│   ├── nginx.conf                # reverse proxy + HTTPS
│   └── absensi-server.service    # systemd (alternatif tanpa Docker)
├── docs/
│   ├── DEPLOYMENT.md             # panduan deploy lengkap ke Linux
│   └── API_CONTRACT.md           # WAJIB dibaca sebelum develop client
├── tests/                        # pytest — semua lulus
└── app/
    ├── main.py
    ├── config.py
    ├── database.py
    ├── models.py                 # ORM sesuai schema.sql
    ├── schemas.py                 # request/response Pydantic
    ├── auth.py                    # Google SSO + JWT + role-based access
    ├── services/
    │   └── crypto.py              # enkripsi embedding wajah (Fernet)
    └── routers/
        ├── login.py                # POST /auth/login/google
        ├── absensi.py               # sync absensi (anti-duplikasi)
        ├── siswa.py                 # CRUD, import CSV, enrollment
        ├── jadwal.py                # jadwal standar & override
        ├── laporan.py               # rekap kehadiran
        ├── device.py                # kelola device kiosk
        ├── embeddings.py            # sync cache embedding ke client
        └── spektrum.py              # CRUD spektrum keahlian (bidang/program/konsentrasi)
```

## Quickstart lokal (development)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env — minimal DATABASE_URL, FACE_ENCRYPTION_KEY (generate sendiri, lihat bawah)

# generate face encryption key baru untuk development:
python -c "from app.services.crypto import generate_new_key; print(generate_new_key())"

alembic upgrade head
uvicorn app.main:app --reload
```

Buka `http://localhost:8000/docs` untuk dokumentasi interaktif.

Untuk deployment production lengkap (Docker/systemd, HTTPS, Google
OAuth, backup), ikuti **`docs/DEPLOYMENT.md`**.

## Menjalankan test

```bash
pytest tests/ -v
```

## Langkah selanjutnya

1. Deploy server ini ke Linux mengikuti `docs/DEPLOYMENT.md`
2. Buat akun guru `admin` pertama secara manual di database (`INSERT INTO guru ...`)
3. Bagikan `docs/API_CONTRACT.md` ke tim/AI yang mengerjakan client Windows & Android
4. Mulai Fase 2 (Client Windows) — lihat `prompt-pengembangan-roadmap.md`
