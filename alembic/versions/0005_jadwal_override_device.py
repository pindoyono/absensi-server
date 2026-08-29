"""Tambah kolom device override ke jadwal_override

Revision ID: 0005_jadwal_override_device
Revises: 0004_perbesar_jurusan_siswa
Create Date: 2026-08-29 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_jadwal_override_device"
down_revision = "0004_perbesar_jurusan_siswa"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("jadwal_override", sa.Column("client_id", sa.String(length=36), unique=True, nullable=True))
    op.add_column("jadwal_override", sa.Column("device_id", sa.String(length=50), nullable=True))
    op.add_column("jadwal_override", sa.Column("sumber", sa.String(length=10), nullable=False, server_default="guru"))
    op.create_index("ix_jadwal_override_client_id", "jadwal_override", ["client_id"])

def downgrade():
    op.drop_index("ix_jadwal_override_client_id", table_name="jadwal_override")
    op.drop_column("jadwal_override", "sumber")
    op.drop_column("jadwal_override", "device_id")
    op.drop_column("jadwal_override", "client_id")
