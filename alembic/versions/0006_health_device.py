"""Tambah kolom health/kesegaran data ke tabel device

Revision ID: 0006_health_device
Revises: 0005_jadwal_override_device
Create Date: 2026-08-29 00:00:00

PRD-observability-degradasi-offline-first §5.1:
Client kiosk melaporkan kesegaran data (jadwal/dispensasi) via
POST /device/{id}/health, server menyimpan di kolom berikut supaya
dashboard admin bisa melihat device yang "diam-diam" basi.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_health_device"
down_revision = "0005_jadwal_override_device"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("device", sa.Column("jadwal_jam_lalu", sa.Float(), nullable=True))
    op.add_column("device", sa.Column("dispensasi_jam_lalu", sa.Float(), nullable=True))
    op.add_column("device", sa.Column("health_dilaporkan_pada", sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column("device", "health_dilaporkan_pada")
    op.drop_column("device", "dispensasi_jam_lalu")
    op.drop_column("device", "jadwal_jam_lalu")
