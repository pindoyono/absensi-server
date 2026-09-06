"""DELETE /siswa/{id}/hard — hapus permanen siswa + absensi + dispensasi + embedding."""
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


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    s.add(models.Siswa(id=7, nis="junk-44", nama="44", aktif=True))
    s.add(models.Absensi(record_id=uuid.uuid4(), siswa_id=7, tanggal=date(2026, 9, 8), type="MASUK",
                         jam_aktual=datetime.combine(date(2026, 9, 8), time(7, 0)),
                         status_kehadiran_otomatis="TERLAMBAT"))
    s.add(models.Dispensasi(siswa_id=7, tanggal=date(2026, 9, 8), jenis="PULANG_CEPAT",
                            kategori="SAKIT", alasan="x", dibuat_oleh=1))
    s.add(models.FaceEmbedding(siswa_id=7, embedding_encrypted=b"x", model_version="v1"))
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


def test_hard_delete_menghapus_siswa_dan_semua_relasinya(client, db_session):
    r = client.delete("/siswa/7/hard", headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["terhapus"] == {"absensi": 1, "dispensasi": 1, "embedding": 1}
    db_session.expire_all()
    assert db_session.query(models.Siswa).filter_by(id=7).first() is None
    assert db_session.query(models.Absensi).filter_by(siswa_id=7).count() == 0
    assert db_session.query(models.Dispensasi).filter_by(siswa_id=7).count() == 0
    assert db_session.query(models.FaceEmbedding).filter_by(siswa_id=7).count() == 0


def test_hard_delete_siswa_tidak_ada_404(client):
    assert client.delete("/siswa/999/hard", headers=_hdr()).status_code == 404


def test_hard_delete_hanya_admin(client):
    r = client.delete("/siswa/7/hard", headers=_hdr(role="guru_piket", gid=2, email="piket@sekolah.sch.id"))
    assert r.status_code == 403


def test_hard_delete_tanpa_auth_401(client):
    assert client.delete("/siswa/7/hard").status_code == 401
