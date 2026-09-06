-- ============================================================
-- Skema Database — Sistem Absensi Face Recognition
-- PostgreSQL 14+
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- Guru / Admin / Wali kelas (login via Google Workspace SSO)
-- ------------------------------------------------------------
CREATE TABLE guru (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,     -- harus domain Workspace sekolah
    role VARCHAR(20) NOT NULL DEFAULT 'guru_piket',
        -- admin | guru_piket | wali_kelas | kepala_sekolah
    kelas_diampu VARCHAR(20),               -- diisi kalau role = wali_kelas
    aktif BOOLEAN DEFAULT true,
    dibuat_pada TIMESTAMP DEFAULT now()
);

-- ------------------------------------------------------------
-- Siswa
-- ------------------------------------------------------------
CREATE TABLE siswa (
    id SERIAL PRIMARY KEY,
    nis VARCHAR(20) UNIQUE NOT NULL,
    nama VARCHAR(100) NOT NULL,
    kelas VARCHAR(20) NOT NULL,
    jurusan VARCHAR(150) DEFAULT 'Teknik Elektronika',
    konsentrasi_id INT REFERENCES konsentrasi_keahlian(id),
    enrolled BOOLEAN DEFAULT false,
    tanggal_enrollment DATE,
    enrolled_oleh INT REFERENCES guru(id),
    aktif BOOLEAN DEFAULT true,             -- false kalau siswa pindah/lulus
    dibuat_pada TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_siswa_kelas ON siswa(kelas);
CREATE INDEX idx_siswa_enrolled ON siswa(enrolled) WHERE enrolled = false;

-- ------------------------------------------------------------
-- Spektrum Keahlian (Kepmendikbudristek No. 244/M/2024)
-- Normalisasi 3 level: Bidang -> Program -> Konsentrasi
-- ------------------------------------------------------------
CREATE TABLE bidang_keahlian (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(100) UNIQUE NOT NULL,
    kode VARCHAR(10) UNIQUE NOT NULL,
    dibuat_pada TIMESTAMP DEFAULT now()
);

CREATE TABLE program_keahlian (
    id SERIAL PRIMARY KEY,
    bidang_id INT NOT NULL REFERENCES bidang_keahlian(id) ON DELETE CASCADE,
    nama VARCHAR(150) NOT NULL,
    kode VARCHAR(10) NOT NULL,
    dibuat_pada TIMESTAMP DEFAULT now(),
    UNIQUE (bidang_id, nama)
);

CREATE TABLE konsentrasi_keahlian (
    id SERIAL PRIMARY KEY,
    program_id INT NOT NULL REFERENCES program_keahlian(id) ON DELETE CASCADE,
    nama VARCHAR(150) NOT NULL,
    kode VARCHAR(10) NOT NULL,
    durasi_tahun INT DEFAULT 3,
    dibuat_pada TIMESTAMP DEFAULT now(),
    UNIQUE (program_id, nama)
);

-- ------------------------------------------------------------
-- Face embedding (terenkripsi), terpisah dari tabel siswa
-- ------------------------------------------------------------
CREATE TABLE face_embedding (
    id SERIAL PRIMARY KEY,
    siswa_id INT UNIQUE NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    embedding_encrypted BYTEA NOT NULL,     -- dienkripsi via pgcrypto sebelum insert
    model_version VARCHAR(20) NOT NULL,     -- misal 'minifasnet-v1', 'arcface-r100'
    dibuat_pada TIMESTAMP DEFAULT now(),
    diperbarui_pada TIMESTAMP DEFAULT now()
);

-- ------------------------------------------------------------
-- Device terdaftar (Windows / Android)
-- ------------------------------------------------------------
CREATE TABLE device (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) UNIQUE NOT NULL,  -- id unik yang di-generate saat setup device
    nama_lokasi VARCHAR(100),               -- 'Gerbang utama', 'Gerbang belakang'
    platform VARCHAR(20),                   -- 'windows' | 'android'
    api_key_hash VARCHAR(200) NOT NULL,     -- untuk autentikasi device ke server
    claim_token VARCHAR(64),                -- token QR provisioning sekali-pakai (POST /device/claim)
    claim_token_expires TIMESTAMP,
    last_seen_at TIMESTAMP,
    aktif BOOLEAN DEFAULT true,
    dibuat_pada TIMESTAMP DEFAULT now()
);
-- catatan: kolom lain (raw_api_key, geofencing, health) ditambah lewat migrasi Alembic.

-- ------------------------------------------------------------
-- Jadwal standar (mengikuti kurikulum, Senin-Jumat)
-- ------------------------------------------------------------
CREATE TABLE jadwal_standar (
    id SERIAL PRIMARY KEY,
    hari VARCHAR(10) NOT NULL CHECK (hari IN ('SENIN','SELASA','RABU','KAMIS','JUMAT')),
    kelas VARCHAR(20),                      -- NULL = berlaku semua kelas
    jam_masuk TIME NOT NULL,
    jam_pulang TIME NOT NULL,
    UNIQUE (hari, kelas)
);

-- ------------------------------------------------------------
-- Override jadwal oleh guru piket / device kiosk (tanggal tertentu)
-- ------------------------------------------------------------
CREATE TABLE jadwal_override (
    id SERIAL PRIMARY KEY,
    tanggal DATE NOT NULL,
    kelas VARCHAR(20),                      -- NULL = berlaku semua kelas
    jam_masuk TIME,
    jam_pulang TIME,
    alasan TEXT,
    dibuat_oleh INT REFERENCES guru(id),    -- NULL kalau dibuat device kiosk
    dibuat_pada TIMESTAMP DEFAULT now(),
    client_id VARCHAR(36) UNIQUE,           -- UUID idempotency key dari device kiosk
    device_id VARCHAR(50),                  -- device_id sumber (bukan FK, device bisa dihapus)
    sumber VARCHAR(10) NOT NULL DEFAULT 'guru'  -- 'guru' | 'device'
);

CREATE INDEX idx_jadwal_override_tanggal ON jadwal_override(tanggal);
CREATE INDEX ix_jadwal_override_client_id ON jadwal_override(client_id);

-- ------------------------------------------------------------
-- Absensi — inti sistem. Maksimal 2 baris per (siswa, tanggal).
-- ------------------------------------------------------------
CREATE TABLE absensi (
    record_id UUID PRIMARY KEY,             -- dibuat di CLIENT saat capture, bukan server
    siswa_id INT NOT NULL REFERENCES siswa(id),
    tanggal DATE NOT NULL,
    type VARCHAR(10) NOT NULL CHECK (type IN ('MASUK','PULANG')),

    jam_aktual TIMESTAMP NOT NULL,
    status_kehadiran_otomatis VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
        -- NORMAL | TERLAMBAT | PULANG_CEPAT
    status_kehadiran_final VARCHAR(20),     -- NULL = belum diverifikasi guru piket
        -- NORMAL | TERLAMBAT | PULANG_CEPAT | IZIN | SAKIT
    catatan TEXT,

    lokasi_mock BOOLEAN NOT NULL DEFAULT false,
        -- client menandai lokasi mock (fake GPS) saat record dibuat.
        -- Server TIDAK menolak record ini — hanya menyimpan tandanya;
        -- record muncul di /absensi/perlu-verifikasi untuk ditinjau guru piket.

    device_id VARCHAR(50) REFERENCES device(device_id),
    approved_by INT REFERENCES guru(id),
    approved_at TIMESTAMP,

    synced_at TIMESTAMP DEFAULT now(),      -- kapan server menerima record ini

    -- Jaring pengaman utama: 1 siswa hanya boleh 1x MASUK dan 1x PULANG per tanggal
    UNIQUE (siswa_id, tanggal, type)
);

CREATE INDEX idx_absensi_tanggal ON absensi(tanggal);
CREATE INDEX idx_absensi_perlu_verifikasi
    ON absensi(tanggal)
    WHERE status_kehadiran_final IS NULL AND status_kehadiran_otomatis != 'NORMAL';

-- ------------------------------------------------------------
-- Dispensasi — izin di muka dari guru piket sebelum siswa absen pulang
-- (misal: siswa izin pulang cepat karena sakit/kegiatan)
-- ------------------------------------------------------------
CREATE TABLE dispensasi (
    id SERIAL PRIMARY KEY,
    siswa_id INT NOT NULL REFERENCES siswa(id),
    tanggal DATE NOT NULL,
    jenis VARCHAR(20) NOT NULL CHECK (jenis IN ('PULANG_CEPAT')),
    kategori VARCHAR(20) NOT NULL DEFAULT 'IZIN',
        -- IZIN | SAKIT | DISPENSASI_KEGIATAN | LAINNYA
    alasan TEXT,
    dibuat_oleh INT NOT NULL REFERENCES guru(id),
    dibuat_pada TIMESTAMP DEFAULT now(),
    UNIQUE (siswa_id, tanggal, jenis)
);

-- ------------------------------------------------------------
-- Log sinkronisasi per device (opsional, untuk audit/troubleshooting)
-- ------------------------------------------------------------
CREATE TABLE sync_log (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) REFERENCES device(device_id),
    jumlah_record INT,
    berhasil INT,
    duplikat_ditolak INT,
    gagal INT,
    dijalankan_pada TIMESTAMP DEFAULT now()
);
