"""skema awal

Revision ID: 0001
Revises:
Create Date: 2026-08-23 09:45:02.007465

SENGAJA membekukan isi SQL persis di file ini (bukan baca schema.sql
secara dinamis saat runtime) -- migration yang sudah dirilis TIDAK
BOLEH berubah lagi walau schema.sql berubah di kemudian hari, kalau
tidak, migration berikutnya (0002 dst) yang menambah tabel baru bisa
tabrakan dengan tabel yang sudah lebih dulu dibuat migration ini
(persis yang terjadi dengan tabel dispensasi sebelum fix ini).

schema.sql tetap jadi dokumentasi struktur TERKINI (dibaca manusia),
tapi migration di sini adalah snapshot HISTORIS -- keduanya boleh
berbeda seiring waktu, itu wajar, jangan disamakan lagi.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEMA_SQL_BEKU = """
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
    jurusan VARCHAR(50) DEFAULT 'Teknik Elektronika',
    enrolled BOOLEAN DEFAULT false,
    tanggal_enrollment DATE,
    enrolled_oleh INT REFERENCES guru(id),
    aktif BOOLEAN DEFAULT true,             -- false kalau siswa pindah/lulus
    dibuat_pada TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_siswa_kelas ON siswa(kelas);
CREATE INDEX idx_siswa_enrolled ON siswa(enrolled) WHERE enrolled = false;

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
    last_seen_at TIMESTAMP,
    aktif BOOLEAN DEFAULT true,
    dibuat_pada TIMESTAMP DEFAULT now()
);

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
-- Override jadwal oleh guru piket (tanggal tertentu)
-- ------------------------------------------------------------
CREATE TABLE jadwal_override (
    id SERIAL PRIMARY KEY,
    tanggal DATE NOT NULL,
    kelas VARCHAR(20),                      -- NULL = berlaku semua kelas
    jam_masuk TIME,
    jam_pulang TIME,
    alasan TEXT,
    dibuat_oleh INT REFERENCES guru(id),
    dibuat_pada TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_jadwal_override_tanggal ON jadwal_override(tanggal);

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
"""


def upgrade() -> None:
    for statement in _SCHEMA_SQL_BEKU.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def downgrade() -> None:
    tabel = [
        "sync_log", "absensi", "jadwal_override", "jadwal_standar",
        "device", "face_embedding", "siswa", "guru",
    ]
    for t in tabel:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
