"""Test geofencing per device:
- PUT /device/{id}/lokasi (admin) — set titik acuan + radius
- POST /device/{id}/lokasi/cek (device-auth) — validasi jarak/mock GPS
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401
from app.main import app
from app.auth import issue_internal_jwt
from app.services.device_auth import hash_api_key
from types import SimpleNamespace

RAW_KEY = "kunci-geofencing-123"

# Gerbang SMKN 2 Malinau (contoh) — kiosk fisik dianggap ada di sini.
TITIK_LAT, TITIK_LNG = -3.4295, 116.4396


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Device(device_id="kiosk-geo", nama_lokasi="Gerbang", platform="android",
                        api_key_hash=hash_api_key(RAW_KEY), aktif=True))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
    def _override():
        Session = sessionmaker(bind=engine)
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _override
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _admin_headers():
    token = issue_internal_jwt(SimpleNamespace(id=1, email="admin@sekolah.sch.id", role="admin"))
    return {"Authorization": f"Bearer {token}"}


DEVICE_HEADERS = {"X-Device-Api-Key": RAW_KEY}


def _atur_lokasi(client, radius=100):
    return client.put(
        "/device/kiosk-geo/lokasi",
        headers=_admin_headers(),
        json={"lat": TITIK_LAT, "lng": TITIK_LNG, "radius_meter": radius},
    )


# ─── Set lokasi (admin) ───────────────────────────────────────

def test_admin_set_lokasi(client, db_session):
    r = _atur_lokasi(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lokasi_lat"] == TITIK_LAT
    assert body["lokasi_lng"] == TITIK_LNG
    assert body["radius_meter"] == 100


def test_set_lokasi_radius_nol_ditolak(client, db_session):
    r = client.put("/device/kiosk-geo/lokasi", headers=_admin_headers(),
                   json={"lat": TITIK_LAT, "lng": TITIK_LNG, "radius_meter": 0})
    assert r.status_code == 422


def test_set_lokasi_bukan_admin_ditolak(client, db_session):
    db_session.add(models.Guru(id=2, nama="Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    db_session.commit()
    token = issue_internal_jwt(SimpleNamespace(id=2, email="piket@sekolah.sch.id", role="guru_piket"))
    r = client.put("/device/kiosk-geo/lokasi", headers={"Authorization": f"Bearer {token}"},
                   json={"lat": TITIK_LAT, "lng": TITIK_LNG, "radius_meter": 100})
    assert r.status_code == 403


# ─── Cek lokasi (kiosk) — device TANPA lokasi diatur (fail-closed) ────

def test_cek_lokasi_device_belum_diatur_ditolak(client, db_session):
    r = client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
                    json={"tersedia": True, "lat": TITIK_LAT, "lng": TITIK_LNG})  # tepat di titik pun tetap ditolak
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert "belum diatur" in body["alasan"]


# ─── Cek lokasi — device DENGAN lokasi diatur ─────────────────

def test_cek_lokasi_dalam_radius_valid(client, db_session):
    _atur_lokasi(client, radius=200)
    r = client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
                    json={"tersedia": True, "lat": TITIK_LAT, "lng": TITIK_LNG})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["jarak_meter"] < 1


def test_cek_lokasi_luar_radius_invalid(client, db_session):
    _atur_lokasi(client, radius=50)
    # ~1.1km ke utara dari titik acuan (0.01 derajat lat ~ 1.1km)
    r = client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
                    json={"tersedia": True, "lat": TITIK_LAT + 0.01, "lng": TITIK_LNG})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert body["jarak_meter"] > 1000


def test_cek_lokasi_mock_gps_ditolak(client, db_session):
    _atur_lokasi(client, radius=200)
    r = client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
                    json={"tersedia": True, "lat": TITIK_LAT, "lng": TITIK_LNG, "mock": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert "palsu" in body["alasan"]


def test_cek_lokasi_tidak_tersedia_ditolak(client, db_session):
    _atur_lokasi(client, radius=200)
    r = client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
                    json={"tersedia": False})
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False


def test_cek_lokasi_menyimpan_status_ke_device(client, db_session):
    _atur_lokasi(client, radius=50)
    client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
               json={"tersedia": True, "lat": TITIK_LAT + 0.01, "lng": TITIK_LNG})

    r = client.get("/device", headers=_admin_headers())
    assert r.status_code == 200
    dev = next(d for d in r.json() if d["device_id"] == "kiosk-geo")
    assert dev["lokasi_valid_terakhir"] is False
    assert dev["lokasi_dicek_pada"] is not None


def test_cek_lokasi_tanpa_api_key_ditolak(client, db_session):
    r = client.post("/device/kiosk-geo/lokasi/cek", json={"tersedia": True, "lat": 0, "lng": 0})
    assert r.status_code == 401


def test_ganti_lokasi_mereset_status_lama(client, db_session):
    _atur_lokasi(client, radius=50)
    client.post("/device/kiosk-geo/lokasi/cek", headers=DEVICE_HEADERS,
               json={"tersedia": True, "lat": TITIK_LAT + 0.01, "lng": TITIK_LNG})
    r = _atur_lokasi(client, radius=100)  # admin pindahkan pin
    assert r.json()["lokasi_valid_terakhir"] is None
