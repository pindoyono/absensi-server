"""Daftar wajah mandiri oleh siswa — izin per device + status verifikasi

Revision ID: 0013_enroll_mandiri
Revises: 0012_kelas_normalisasi
Create Date: 2026-09-08 12:00:00

- device.izin_enroll_mandiri: device boleh dipakai siswa daftar wajah sendiri
- siswa.enroll_mandiri_pending: sudah daftar mandiri, tunggu konfirmasi admin
  (absensi ditolak sampai dikonfirmasi)
- siswa.enroll_foto: foto capture saat daftar (bukti verifikasi), dihapus
  setelah dikonfirmasi/ditolak
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_enroll_mandiri"
down_revision = "0012_kelas_normalisasi"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "device",
        sa.Column("izin_enroll_mandiri", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "siswa",
        sa.Column("enroll_mandiri_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("siswa", sa.Column("enroll_foto", sa.LargeBinary(), nullable=True))


def downgrade():
    op.drop_column("siswa", "enroll_foto")
    op.drop_column("siswa", "enroll_mandiri_pending")
    op.drop_column("device", "izin_enroll_mandiri")
