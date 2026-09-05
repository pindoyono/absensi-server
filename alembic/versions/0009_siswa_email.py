"""Tambah siswa.email — opsional, untuk login Google role siswa

Revision ID: 0009_siswa_email
Revises: 0008_geofencing_device
Create Date: 2026-09-05 00:00:00

Kolom nullable + unique. Siswa tanpa email tetap berfungsi normal (absen
via NIS/wajah tidak terpengaruh) — ini murni jalur login tambahan untuk
dashboard web, lihat app/auth.py (get_current_siswa) & app/routers/login.py.
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_siswa_email"
down_revision = "0008_geofencing_device"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("siswa", sa.Column("email", sa.String(length=150), nullable=True))
    op.create_unique_constraint("uq_siswa_email", "siswa", ["email"])


def downgrade():
    op.drop_constraint("uq_siswa_email", "siswa", type_="unique")
    op.drop_column("siswa", "email")
