"""Normalisasi kelas (rombel) — tabel `kelas` + kelas_id FK di semua tempat

Revision ID: 0012_kelas_normalisasi
Revises: 0011_device_claim_token
Create Date: 2026-09-06 12:00:00

`kelas` sebelumnya cuma string bebas di siswa.kelas, jadwal_standar.kelas,
jadwal_override.kelas, guru.kelas_diampu. Migrasi ini:
- membuat tabel `kelas` (sumber kebenaran daftar rombel),
- backfill dari string distinct yang ada,
- menambah `kelas_id` FK di siswa / jadwal_standar / jadwal_override,
- memindahkan wali kelas ke `kelas.wali_id` (dari guru.kelas_diampu),
- menukar unique (hari, kelas) → (hari, kelas_id) di jadwal_standar,
- men-drop 4 kolom string lama.

Kontrak ke kiosk TIDAK berubah — server tetap mengekspos NAMA kelas
(di-compute dari relasi, lihat Siswa.kelas @property).
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_kelas_normalisasi"
down_revision = "0011_device_claim_token"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kelas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nama", sa.String(length=50), nullable=False, unique=True),
        sa.Column("tingkat", sa.String(length=10), nullable=True),
        sa.Column("konsentrasi_id", sa.Integer(), sa.ForeignKey("konsentrasi_keahlian.id"), nullable=True),
        sa.Column("wali_id", sa.Integer(), sa.ForeignKey("guru.id"), nullable=True),
        sa.Column("aktif", sa.Boolean(), server_default=sa.true(), nullable=True),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )

    # 1. Backfill daftar kelas dari semua string yang pernah dipakai.
    op.execute(
        """
        INSERT INTO kelas (nama, aktif)
        SELECT DISTINCT btrim(nama) AS nama, true
        FROM (
            SELECT kelas AS nama FROM siswa WHERE kelas IS NOT NULL AND btrim(kelas) <> ''
            UNION SELECT kelas FROM jadwal_standar WHERE kelas IS NOT NULL AND btrim(kelas) <> ''
            UNION SELECT kelas FROM jadwal_override WHERE kelas IS NOT NULL AND btrim(kelas) <> ''
        ) t
        """
    )

    # 2. siswa.kelas_id
    op.add_column("siswa", sa.Column("kelas_id", sa.Integer(), sa.ForeignKey("kelas.id"), nullable=True))
    op.execute("UPDATE siswa s SET kelas_id = k.id FROM kelas k WHERE btrim(s.kelas) = k.nama")

    # 3. jadwal_standar.kelas_id (NULL tetap NULL = berlaku semua kelas)
    op.add_column("jadwal_standar", sa.Column("kelas_id", sa.Integer(), sa.ForeignKey("kelas.id"), nullable=True))
    op.execute("UPDATE jadwal_standar j SET kelas_id = k.id FROM kelas k WHERE btrim(j.kelas) = k.nama")

    # 4. jadwal_override.kelas_id
    op.add_column("jadwal_override", sa.Column("kelas_id", sa.Integer(), sa.ForeignKey("kelas.id"), nullable=True))
    op.execute("UPDATE jadwal_override j SET kelas_id = k.id FROM kelas k WHERE btrim(j.kelas) = k.nama")

    # 5. wali kelas: guru.kelas_diampu → kelas.wali_id
    op.execute(
        """
        UPDATE kelas k SET wali_id = g.id
        FROM guru g
        WHERE btrim(g.kelas_diampu) = k.nama AND g.role = 'wali_kelas'
        """
    )

    # 6. tukar unique constraint di jadwal_standar. Nama constraint lama = default
    #    Postgres untuk `UNIQUE (hari, kelas)` inline di 0001. IF EXISTS supaya
    #    aman kalau ternyata dinamai lain / sudah tak ada.
    op.execute("ALTER TABLE jadwal_standar DROP CONSTRAINT IF EXISTS jadwal_standar_hari_kelas_key")
    op.execute("ALTER TABLE jadwal_standar DROP CONSTRAINT IF EXISTS uq_jadwal_standar_hari_kelas")
    op.create_unique_constraint(
        "uq_jadwal_standar_hari_kelas_id", "jadwal_standar", ["hari", "kelas_id"]
    )

    # 7. buang kolom string lama
    op.drop_index("idx_siswa_kelas", table_name="siswa")
    op.drop_column("siswa", "kelas")
    op.drop_column("jadwal_standar", "kelas")
    op.drop_column("jadwal_override", "kelas")
    op.drop_column("guru", "kelas_diampu")

    # 8. index bantu
    op.create_index("ix_siswa_kelas_id", "siswa", ["kelas_id"])


def downgrade():
    op.drop_index("ix_siswa_kelas_id", table_name="siswa")

    op.add_column("guru", sa.Column("kelas_diampu", sa.String(length=20), nullable=True))
    op.add_column("jadwal_override", sa.Column("kelas", sa.String(length=20), nullable=True))
    op.add_column("jadwal_standar", sa.Column("kelas", sa.String(length=20), nullable=True))
    op.add_column("siswa", sa.Column("kelas", sa.String(length=20), nullable=True))

    op.execute("UPDATE siswa s SET kelas = k.nama FROM kelas k WHERE s.kelas_id = k.id")
    op.execute("UPDATE siswa SET kelas = '' WHERE kelas IS NULL")
    op.execute("UPDATE jadwal_standar j SET kelas = k.nama FROM kelas k WHERE j.kelas_id = k.id")
    op.execute("UPDATE jadwal_override j SET kelas = k.nama FROM kelas k WHERE j.kelas_id = k.id")
    op.execute(
        """
        UPDATE guru g SET kelas_diampu = k.nama
        FROM kelas k WHERE k.wali_id = g.id
        """
    )

    op.alter_column("siswa", "kelas", nullable=False)
    op.create_index("idx_siswa_kelas", "siswa", ["kelas"])

    op.execute("ALTER TABLE jadwal_standar DROP CONSTRAINT IF EXISTS uq_jadwal_standar_hari_kelas_id")
    op.create_unique_constraint("jadwal_standar_hari_kelas_key", "jadwal_standar", ["hari", "kelas"])

    op.drop_column("jadwal_override", "kelas_id")
    op.drop_column("jadwal_standar", "kelas_id")
    op.drop_column("siswa", "kelas_id")
    op.drop_table("kelas")
