"""Perbaikan hasil review server: rate limit, raw_api_key tidak persist,
guard secret produksi."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401
from app.main import app
from app.services.device_auth import hash_api_key


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Device(device_id="kiosk-1", nama_lokasi="Gerbang", platform="android",
                        api_key_hash=hash_api_key("rahasia"), raw_api_key="rahasia", aktif=True))
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


DEV = {"X-Device-Id": "kiosk-1", "X-Device-Api-Key": "rahasia"}


# ---------- rate limit ----------

def test_login_google_kena_rate_limit(client):
    # batasi("login", 20, 60): request ke-21 dalam 1 menit → 429
    kode = [client.post("/auth/login/google", json={"google_id_token": "x"}).status_code for _ in range(25)]
    assert 429 in kode
    assert kode.index(429) >= 20  # 20 pertama tidak di-limit


def test_device_claim_kena_rate_limit(client):
    kode = [client.post("/device/claim", json={"token": "salah"}).status_code for _ in range(25)]
    assert 429 in kode


# ---------- raw_api_key tidak boleh persist ----------

def test_raw_api_key_dihapus_setelah_device_auth(client, db_session):
    # panggil endpoint device-auth apa pun (verify_device dipanggil di dalamnya)
    r = client.post("/device/kiosk-1/health", headers=DEV, json={})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.query(models.Device).filter_by(device_id="kiosk-1").one().raw_api_key is None


def test_raw_api_key_dihapus_setelah_claim_tapi_tetap_dikirim(client, db_session):
    from app.services import device_claim
    d = db_session.query(models.Device).filter_by(device_id="kiosk-1").one()
    device_claim.buat_claim_token(d)
    db_session.commit()
    token = db_session.query(models.Device).filter_by(device_id="kiosk-1").one().claim_token

    r = client.post("/device/claim", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["api_key"] == "rahasia"  # tetap dikirim ke kiosk
    db_session.expire_all()
    assert db_session.query(models.Device).filter_by(device_id="kiosk-1").one().raw_api_key is None


# ---------- guard secret produksi ----------

def test_secret_placeholder_errors_mendeteksi_default():
    from app.config import Settings
    s = Settings(_env_file=None)  # abaikan .env lokal
    masalah = s.secret_placeholder_errors()
    assert any("JWT_SECRET" in m for m in masalah)
    assert any("FACE_ENCRYPTION_KEY" in m for m in masalah)


def test_secret_placeholder_errors_bersih_kalau_diisi():
    from app.config import Settings
    s = Settings(
        _env_file=None,
        jwt_secret="x" * 40,
        face_encryption_key="kunci-fernet-unik-yang-bukan-placeholder=",
        google_client_id="abc.apps.googleusercontent.com",
        database_url="postgresql://real:cred@db.internal:5432/absensi",
    )
    assert s.secret_placeholder_errors() == []
