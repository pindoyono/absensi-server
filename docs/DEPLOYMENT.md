# Panduan Deployment Server — Linux

Dokumen ini untuk deploy server absensi ke server Linux produksi (sudah diuji alurnya di sandbox: migration Alembic, seluruh endpoint, dan logika anti-duplikasi berjalan benar di PostgreSQL asli).

Dua opsi deployment disediakan: **Docker Compose** (direkomendasikan, lebih mudah dikelola) atau **systemd manual** (kalau tidak mau pakai Docker).

---

## Prasyarat

- Server Linux (Ubuntu 22.04/24.04 direkomendasikan), akses root/sudo
- Domain/subdomain yang sudah diarahkan ke IP server (misal `absensi.smkxxx.sch.id`)
- Akun Google Cloud Console untuk setup OAuth Client ID (lihat bagian 3)

---

## Opsi A — Deployment dengan Docker Compose (direkomendasikan)

### A.1 Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# logout & login ulang supaya grup docker aktif
```

### A.2 Clone project & konfigurasi

```bash
git clone https://github.com/pindoyono/absensi-server.git
cd absensi-server

cp .env.example .env
nano .env   # isi semua nilai, lihat panduan tiap variabel di bagian 2 & 3
```

### A.3 Generate key enkripsi wajah (WAJIB, jangan pakai default)

```bash
docker compose run --rm api python -c "from app.services.crypto import generate_new_key; print(generate_new_key())"
```

Salin hasilnya ke `FACE_ENCRYPTION_KEY` di `.env`. **Simpan juga salinan key ini di tempat terpisah** (password manager sekolah) — kalau key ini hilang dari server, semua data wajah tersimpan tidak bisa didekripsi lagi dan seluruh siswa harus enrollment ulang.

### A.4 Jalankan

```bash
docker compose up -d
docker compose logs -f api   # cek log, pastikan tidak ada error startup
```

Database (`schema.sql`) otomatis dijalankan saat container Postgres pertama kali dibuat (lewat `docker-entrypoint-initdb.d`). Untuk migration berikutnya, gunakan Alembic (bagian 5).

### A.5 Cek server hidup

```bash
curl http://localhost:8000/health
# harus balas: {"status":"ok"}
```

---

## Opsi B — Deployment manual dengan systemd (tanpa Docker)

```bash
# 1. Install PostgreSQL & Python
sudo apt update && sudo apt install -y postgresql python3-venv python3-pip nginx

# 2. Buat database
sudo -u postgres psql -c "CREATE USER absensi_user WITH PASSWORD 'GANTI_PASSWORD_AMAN';"
sudo -u postgres psql -c "CREATE DATABASE absensi OWNER absensi_user;"

# 3. Clone project ke /opt
sudo mkdir -p /opt/absensi-server
sudo git clone https://github.com/pindoyono/absensi-server.git /opt/absensi-server
cd /opt/absensi-server

# 4. Virtual environment
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

# 5. Konfigurasi
sudo cp .env.example .env
sudo nano .env   # isi DATABASE_URL, GOOGLE_CLIENT_ID, JWT_SECRET, FACE_ENCRYPTION_KEY

# 6. Jalankan migration
sudo ./venv/bin/alembic upgrade head

# 7. Buat user khusus untuk service (jangan jalankan sebagai root)
sudo useradd -r -s /bin/false absensi
sudo chown -R absensi:absensi /opt/absensi-server

# 8. Pasang service systemd
sudo cp deploy/absensi-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now absensi-server
sudo systemctl status absensi-server
```

---

## 2. Variabel `.env` — Penjelasan Lengkap

| Variabel | Keterangan |
|---|---|
| `DATABASE_URL` | Connection string Postgres, format `postgresql://user:pass@host:5432/dbname` |
| `ALLOWED_EMAIL_DOMAIN` | Domain email Google Workspace sekolah (misal `smkxxx.sch.id`) — hanya akun domain ini yang bisa login dashboard |
| `GOOGLE_CLIENT_ID` | Dari Google Cloud Console, lihat bagian 3 |
| `JWT_SECRET` | String acak panjang untuk menandatangani JWT internal. Generate: `openssl rand -hex 32` |
| `FACE_ENCRYPTION_KEY` | Key enkripsi embedding wajah, lihat bagian A.3 |

---

## 3. Setup Google OAuth (Login SSO Guru)

1. Buka [Google Cloud Console](https://console.cloud.google.com/) → buat project baru (atau pakai project Workspace sekolah yang sudah ada).
2. Menu **APIs & Services → OAuth consent screen** → pilih **Internal** (kalau organisasi Workspace) atau **External** dengan restriksi domain.
3. Menu **Credentials → Create Credentials → OAuth Client ID** → tipe **Web application**.
4. Tambahkan **Authorized JavaScript origins**: `https://absensi.smkxxx.sch.id` (domain dashboard).
5. Salin **Client ID** yang dihasilkan → masukkan ke `GOOGLE_CLIENT_ID` di `.env`.
6. Dashboard web (yang akan dibangun terpisah, lihat `docs/API_CONTRACT.md`) memakai Client ID ini untuk tombol "Login dengan Google".

---

## 4. Setup HTTPS (Nginx + Let's Encrypt)

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/absensi
sudo nano /etc/nginx/sites-available/absensi   # ganti server_name sesuai domain sekolah
sudo ln -s /etc/nginx/sites-available/absensi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d absensi.smkxxx.sch.id
```

Certbot otomatis menambahkan blok `server { listen 443 ... }` dan redirect HTTP→HTTPS ke file konfigurasi.

**Kenapa HTTPS wajib, bukan opsional:** endpoint `/absensi/sync` dan `/embeddings/sync` mengirim data siswa (termasuk embedding wajah terenkripsi) melalui jaringan. Tanpa HTTPS, walau embedding-nya sendiri terenkripsi, data lain (NIS, nama, jam absen) masih terbaca siapa saja yang menyadap jaringan.

---

## 5. Migration Database (Alembic)

Untuk perubahan skema di masa depan, jangan edit `schema.sql` lalu jalankan manual — gunakan Alembic supaya riwayat perubahan tercatat dan bisa di-rollback:

```bash
# Setelah mengubah app/models.py, generate migration baru:
alembic revision --autogenerate -m "deskripsi perubahan"

# Review file yang dihasilkan di alembic/versions/ sebelum apply
alembic upgrade head

# Kalau perlu rollback:
alembic downgrade -1
```

Migration awal (`0001_skema_awal.py`) menjalankan `schema.sql` apa adanya, sudah diuji dan menghasilkan 8 tabel dengan benar di Postgres.

---

## 6. Backup Database

Backup harian minimal untuk `absensi` database — ini data absensi 1000 siswa, jangan sampai tidak ada backup:

```bash
# Contoh cron harian jam 2 pagi
0 2 * * * pg_dump -U absensi_user absensi | gzip > /backup/absensi-$(date +\%F).sql.gz
```

Simpan backup di lokasi terpisah dari server utama (Google Drive sekolah yang sudah dipakai, atau storage terpisah) — kalau server rusak/hilang, backup di server yang sama tidak berguna.

---

## 7. Monitoring Dasar

```bash
# Docker
docker compose logs -f api
docker compose ps

# systemd
sudo journalctl -u absensi-server -f
sudo systemctl status absensi-server
```

Endpoint `/health` bisa dipakai untuk monitoring uptime sederhana (misal cron yang curl tiap 5 menit dan kirim notifikasi kalau gagal).

---

## 8. Checklist Sebelum Go-Live

- [ ] `.env` terisi lengkap, `FACE_ENCRYPTION_KEY` sudah diganti dari default (bukan yang ada di `.env.example`)
- [ ] HTTPS aktif dan sertifikat valid
- [ ] Google OAuth Client ID sudah didaftarkan dengan domain dashboard yang benar
- [ ] Migration Alembic sudah dijalankan (`alembic upgrade head`)
- [ ] Minimal 1 akun guru dengan role `admin` sudah di-insert manual ke tabel `guru` (lihat `docs/API_CONTRACT.md` bagian login)
- [ ] Backup database terjadwal aktif
- [ ] Test end-to-end: login Google → create siswa → register device → sync absensi → cek anti-duplikasi (skenario sudah dicontohkan di `docs/API_CONTRACT.md`)
