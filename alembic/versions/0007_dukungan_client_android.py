"""Dukungan client Android: siswa.enrolled_device_id

Revision ID: 0007_dukungan_client_android
Revises: 8e4be0b0902a
Create Date: 2026-09-04 00:00:00

Lihat docs/PRD_DUKUNGAN_CLIENT_ANDROID.md (R-P1-4).

Catatan: heartbeat / kesegaran cache device (R-P0-2) sudah ada di server
lewat kolom `device.jadwal_jam_lalu` / `dispensasi_jam_lalu` /
`health_dilaporkan_pada` (migrasi 0006_health_device) + endpoint
`POST /device/{id}/health`. Migrasi ini hanya menambah kolom yang belum ada.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_dukungan_client_android"
down_revision = "8e4be0b0902a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("siswa", sa.Column("enrolled_device_id", sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column("siswa", "enrolled_device_id")
