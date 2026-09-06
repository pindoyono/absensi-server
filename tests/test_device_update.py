"""PATCH /device/{id} — admin ubah nama lokasi / platform device."""
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
from app.services.device_auth import hash_api_key


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
    s.add(models.Device(device_id="kiosk-1", nama_lokasi="Gerbang Lama", platform="android",
                        api_key_hash=hash_api_key("k"), aktif=True))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
    def _override():
        s = sessionmaker(bind=engine)()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _hdr(role="admin", gid=1, email="admin@sekolah.sch.id"):
    return {"Authorization": f"Bearer {issue_internal_jwt(SimpleNamespace(id=gid, email=email, role=role))}"}


def test_admin_ubah_nama_lokasi(client, db_session):
    r = client.patch("/device/kiosk-1", headers=_hdr(), json={"nama_lokasi": "  Gerbang Belakang  "})
    assert r.status_code == 200, r.text
    assert r.json()["nama_lokasi"] == "Gerbang Belakang"  # di-trim
    db_session.expire_all()
    assert db_session.query(models.Device).filter_by(device_id="kiosk-1").one().nama_lokasi == "Gerbang Belakang"


def test_field_tidak_dikirim_tidak_berubah(client, db_session):
    r = client.patch("/device/kiosk-1", headers=_hdr(), json={"platform": "windows"})
    assert r.status_code == 200, r.text
    assert r.json()["platform"] == "windows"
    assert r.json()["nama_lokasi"] == "Gerbang Lama"  # tetap


def test_nama_kosong_ditolak(client):
    assert client.patch("/device/kiosk-1", headers=_hdr(), json={"nama_lokasi": "   "}).status_code == 422


def test_platform_ngawur_ditolak(client):
    assert client.patch("/device/kiosk-1", headers=_hdr(), json={"platform": "ios"}).status_code == 422


def test_device_tidak_ada_404(client):
    assert client.patch("/device/ghost", headers=_hdr(), json={"nama_lokasi": "X"}).status_code == 404


def test_guru_piket_tidak_boleh(client):
    r = client.patch("/device/kiosk-1", headers=_hdr(role="guru_piket", gid=2, email="piket@sekolah.sch.id"),
                     json={"nama_lokasi": "X"})
    assert r.status_code == 403


def test_tanpa_auth_401(client):
    assert client.patch("/device/kiosk-1", json={"nama_lokasi": "X"}).status_code == 401
