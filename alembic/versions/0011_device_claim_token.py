"""Tambah device.claim_token + claim_token_expires — provisioning via QR

Revision ID: 0011_device_claim_token
Revises: 0010_absensi_lokasi_mock
Create Date: 2026-09-06 00:00:00

Token acak sekali-pakai yang di-encode ke QR saat admin menambah device.
Kiosk memindainya lalu menukarnya (POST /device/claim) jadi device_id +
api_key. Kedua kolom nullable — device lama tidak terpengaruh.
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_device_claim_token"
down_revision = "0010_absensi_lokasi_mock"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("device", sa.Column("claim_token", sa.String(length=64), nullable=True))
    op.add_column("device", sa.Column("claim_token_expires", sa.DateTime(), nullable=True))
    op.create_index("ix_device_claim_token", "device", ["claim_token"])


def downgrade():
    op.drop_index("ix_device_claim_token", table_name="device")
    op.drop_column("device", "claim_token_expires")
    op.drop_column("device", "claim_token")
