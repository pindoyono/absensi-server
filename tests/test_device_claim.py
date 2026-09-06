"""Provisioning device via QR — token sekali-pakai.

- POST /device/register  -> response memuat blok `claim` (token + payload QR)
- GET  /device/{id}/claim-qr (admin) -> token BARU, menimpa yang lama
- POST /device/claim {token} (tanpa auth) -> tukar jadi kredensial, token hangus
"""
import json

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
from app.services import device_claim


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Device(device_id="kiosk-1", nama_lokasi="Gerbang", platform="android",
                        api_key_hash=hash_api_key("rahasia"), raw_api_key="rahasia", aktif=True))
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


def _admin():
    tok = issue_internal_jwt(SimpleNamespace(id=1, email="admin@sekolah.sch.id", role="admin"))
    return {"Authorization": f"Bearer {tok}"}


def test_register_mengembalikan_blok_claim(client):
    r = client.post("/device/register", headers=_admin(),
                    json={"nama_lokasi": "Aula", "platform": "android"})
    assert r.status_code == 200, r.text
    claim = r.json()["claim"]
    assert claim["token"]
    payload = json.loads(claim["payload"])
    assert payload["v"] == 1 and payload["token"] == claim["token"] and payload["server"]


def test_claim_qr_admin_membuat_token_baru(client, db_session):
    r = client.get("/device/kiosk-1/claim-qr", headers=_admin())
    assert r.status_code == 200, r.text
    t1 = r.json()["token"]
    r2 = client.get("/device/kiosk-1/claim-qr", headers=_admin())
    t2 = r2.json()["token"]
    assert t1 != t2  # token lama ditimpa
    db_session.expire_all()
    assert db_session.query(models.Device).filter_by(device_id="kiosk-1").one().claim_token == t2


def test_claim_qr_butuh_auth_guru(client):
    assert client.get("/device/kiosk-1/claim-qr").status_code == 401


def test_claim_tukar_token_jadi_kredensial_lalu_hangus(client, db_session):
    token = client.get("/device/kiosk-1/claim-qr", headers=_admin()).json()["token"]

    r = client.post("/device/claim", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device_id"] == "kiosk-1"
    assert body["api_key"] == "rahasia"
    assert body["face_encryption_key"]
    assert body["server"]

    # sekali-pakai: token kedua kali gagal
    assert client.post("/device/claim", json={"token": token}).status_code == 404


def test_claim_token_ngawur_ditolak(client):
    assert client.post("/device/claim", json={"token": "bukan-token"}).status_code == 404
    assert client.post("/device/claim", json={"token": ""}).status_code == 400


def test_claim_token_kedaluwarsa_ditolak(client, db_session):
    device_claim.buat_claim_token(
        db_session.query(models.Device).filter_by(device_id="kiosk-1").one(), ttl_menit=-1
    )
    db_session.commit()
    token = db_session.query(models.Device).filter_by(device_id="kiosk-1").one().claim_token
    assert client.post("/device/claim", json={"token": token}).status_code == 404


def test_claim_token_expires_naive_utc_tetap_diterima(client, db_session):
    """Regresi: Postgres menyimpan datetime sebagai UTC-naive. Token yang masih
    30 menit lagi kedaluwarsa TIDAK boleh dianggap habis."""
    from datetime import datetime, timedelta
    d = db_session.query(models.Device).filter_by(device_id="kiosk-1").one()
    d.claim_token = "tok-naive"
    d.claim_token_expires = datetime.utcnow() + timedelta(minutes=30)  # naive, seperti PG
    db_session.commit()
    assert client.post("/device/claim", json={"token": "tok-naive"}).status_code == 200
