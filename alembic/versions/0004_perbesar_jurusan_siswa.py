"""Perbesar kolom jurusan siswa

Revision ID: 0004_perbesar_jurusan_siswa
Revises: 0003_tambah_spektrum_keahlian
Create Date: 2026-08-27 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_perbesar_jurusan_siswa"
down_revision = "0003_tambah_spektrum_keahlian"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("siswa", "jurusan", type_=sa.String(length=150), existing_type=sa.String(length=50))


def downgrade():
    op.alter_column("siswa", "jurusan", type_=sa.String(length=50), existing_type=sa.String(length=150))
