"""Tambah absensi.lokasi_mock — tandai record dari lokasi mock (fake GPS)

Revision ID: 0010_absensi_lokasi_mock
Revises: 0009_siswa_email
Create Date: 2026-09-06 00:00:00

Client menandai record absensi yang dibuat saat OS mendeteksi mock-location
(fake GPS). Server TIDAK menolak record tsb — hanya menyimpan tandanya
supaya guru piket bisa meninjau (record muncul di /absensi/perlu-verifikasi).

Kolom NOT NULL DEFAULT false — record lama otomatis terisi false, client
lama yang tak mengirim field ini tetap berfungsi normal.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_absensi_lokasi_mock"
down_revision = "0009_siswa_email"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "absensi",
        sa.Column("lokasi_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("absensi", "lokasi_mock")
