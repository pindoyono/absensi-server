"""Add dispensasi table

Revision ID: 0002_tambah_tabel_dispensasi
Revises: 0001_skema_awal
Create Date: 2026-08-26 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_tambah_tabel_dispensasi"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dispensasi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("siswa_id", sa.Integer(), sa.ForeignKey("siswa.id"), nullable=False),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("jenis", sa.String(length=20), nullable=False, server_default="PULANG_CEPAT"),
        sa.Column("kategori", sa.String(length=20), nullable=False, server_default="IZIN"),
        sa.Column("alasan", sa.Text(), nullable=True),
        sa.Column("dibuat_oleh", sa.Integer(), sa.ForeignKey("guru.id"), nullable=False),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("siswa_id", "tanggal", "jenis", name="uq_dispensasi_siswa_tanggal_jenis"),
    )


def downgrade():
    op.drop_table("dispensasi")
