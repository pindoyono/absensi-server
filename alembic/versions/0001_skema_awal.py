"""skema awal

Revision ID: 0001
Revises: 
Create Date: 2026-08-23 09:45:02.007465

"""
"""
Migration awal — menjalankan schema.sql apa adanya, supaya schema.sql
tetap jadi satu-satunya sumber kebenaran untuk struktur database
(dokumentasi & migration tidak saling berbeda).
"""
import os
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA_SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "schema.sql")


def upgrade() -> None:
    with open(_SCHEMA_SQL_PATH) as f:
        sql = f.read()
    # Jalankan tiap statement terpisah oleh titik koma (schema.sql tidak
    # mengandung ';' di dalam string/komentar, aman untuk split sederhana)
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def downgrade() -> None:
    tabel = [
        "sync_log", "absensi", "jadwal_override", "jadwal_standar",
        "device", "face_embedding", "siswa", "guru",
    ]
    for t in tabel:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
