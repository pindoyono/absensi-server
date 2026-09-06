"""DELETE /absensi/{record_id} — hapus permanen 1 record, admin-only."""
import uuid
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.database import Base, get_db
from app import models  # noqa: F401
from app.main import app
from app.auth import issue_internal_jwt


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


RID = uuid.uuid4()


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    s.add(models.Kelas(id=1, nama="XI"))
    s.add(models.Siswa(id=1, nis="111", nama="Ani", kelas_id=1, aktif=True))
    s.add(models.Absensi(record_id=RID, siswa_id=1, tanggal=date(2026, 9, 6), type="MASUK",
                         jam_aktual=datetime.combine(date(2026, 9, 6), time(7, 0)),
                         status_kehadiran_otomatis="TERLAMBAT"))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
    def _o():
        s = sessionmaker(bind=engine)()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _o
    yield TestClient(app)
    app.dependency_overrides.clear()


def _hdr(role="admin", gid=1, email="admin@sekolah.sch.id"):
    return {"Authorization": f"Bearer {issue_internal_jwt(SimpleNamespace(id=gid, email=email, role=role))}"}


def test_admin_hapus_record(client, db_session):
    r = client.delete(f"/absensi/{RID}", headers=_hdr())
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(models.Absensi).filter_by(record_id=RID).first() is None


def test_hapus_membebaskan_slot_unik(client, db_session):
    """Setelah dihapus, tidak ada baris utk (siswa, tanggal, type) → slot
    UNIQUE bebas, siswa bisa absen ulang."""
    client.delete(f"/absensi/{RID}", headers=_hdr())
    db_session.expire_all()
    assert db_session.query(models.Absensi).filter_by(
        siswa_id=1, tanggal=date(2026, 9, 6), type="MASUK"
    ).count() == 0


def test_record_tidak_ada_404(client):
    assert client.delete(f"/absensi/{uuid.uuid4()}", headers=_hdr()).status_code == 404


def test_guru_piket_tidak_boleh_hapus(client):
    r = client.delete(f"/absensi/{RID}", headers=_hdr(role="guru_piket", gid=2, email="piket@sekolah.sch.id"))
    assert r.status_code == 403


def test_tanpa_auth_401(client):
    assert client.delete(f"/absensi/{RID}").status_code == 401
