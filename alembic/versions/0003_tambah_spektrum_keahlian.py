"""Add spektrum keahlian tables

Revision ID: 0003_tambah_spektrum_keahlian
Revises: 0002_tambah_tabel_dispensasi
Create Date: 2026-08-27 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_tambah_spektrum_keahlian"
down_revision = "0002_tambah_tabel_dispensasi"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bidang_keahlian",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nama", sa.String(length=100), nullable=False, unique=True),
        sa.Column("kode", sa.String(length=10), nullable=False, unique=True),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )

    op.create_table(
        "program_keahlian",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bidang_id", sa.Integer(), sa.ForeignKey("bidang_keahlian.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nama", sa.String(length=150), nullable=False),
        sa.Column("kode", sa.String(length=10), nullable=False),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("bidang_id", "nama", name="uq_program_bidang_nama"),
    )

    op.create_table(
        "konsentrasi_keahlian",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("program_keahlian.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nama", sa.String(length=150), nullable=False),
        sa.Column("kode", sa.String(length=10), nullable=False),
        sa.Column("durasi_tahun", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("program_id", "nama", name="uq_konsentrasi_program_nama"),
    )

    # Normalisasi siswa: tambah FK konsentrasi_id (jurusan string lama tetap ada utk backward-compat)
    op.add_column("siswa", sa.Column("konsentrasi_id", sa.Integer(), sa.ForeignKey("konsentrasi_keahlian.id"), nullable=True))


def downgrade():
    op.drop_column("siswa", "konsentrasi_id")
    op.drop_table("konsentrasi_keahlian")
    op.drop_table("program_keahlian")
    op.drop_table("bidang_keahlian")