"""Geofencing per device: lokasi_lat/lng/radius + status cek terakhir

Revision ID: 0008_geofencing_device
Revises: 0007_dukungan_client_android
Create Date: 2026-09-05 00:00:00

Semua kolom nullable — device lama tanpa lokasi diatur tetap berfungsi
normal (fitur opt-in per device, lihat app/routers/device.py).
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_geofencing_device"
down_revision = "0007_dukungan_client_android"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("device", sa.Column("lokasi_lat", sa.Float(), nullable=True))
    op.add_column("device", sa.Column("lokasi_lng", sa.Float(), nullable=True))
    op.add_column("device", sa.Column("radius_meter", sa.Integer(), nullable=True))
    op.add_column("device", sa.Column("lokasi_valid_terakhir", sa.Boolean(), nullable=True))
    op.add_column("device", sa.Column("lokasi_alasan_terakhir", sa.String(length=200), nullable=True))
    op.add_column("device", sa.Column("lokasi_dicek_pada", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("device", "lokasi_dicek_pada")
    op.drop_column("device", "lokasi_alasan_terakhir")
    op.drop_column("device", "lokasi_valid_terakhir")
    op.drop_column("device", "radius_meter")
    op.drop_column("device", "lokasi_lng")
    op.drop_column("device", "lokasi_lat")
