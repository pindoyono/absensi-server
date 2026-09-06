"""Test fitur Device Health Monitoring (PRD-tuntaskan-device-health).

Menguji:
- POST /device/{id}/health wajib X-Device-Api-Key (401 kalau tidak ada)
- POST /device/{id}/health dengan key benar menyimpan kolom
- GET /device/status-kesehatan (guru) menandai device bermasalah & belum lapor
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401 — register semua model
from app.main import app
from app.services.device_auth import hash_api_key


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    raw = "kunci-device-health-123"
    s.add(models.Device(
        device_id="kiosk-health", nama_lokasi="Gerbang", platform="windows",
        api_key_hash=hash_api_key(raw), aktif=True,
    ))
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


def _login_guru(client, email):
    from app.auth import issue_internal_jwt
    from types import SimpleNamespace
    role = "admin" if "admin" in email else "guru_piket"
    gid = 1 if role == "admin" else 2
    return issue_internal_jwt(SimpleNamespace(id=gid, email=email, role=role))


def test_health_tanpa_api_key_ditolak(client):
    r = client.post("/device/kiosk-health/health", json={"jadwal_jam_lalu": 1.0})
    assert r.status_code == 401  # sebelumnya lolos (bug lama)


def test_health_dengan_api_key_benar_tersimpan(client):
    r = client.post(
        "/device/kiosk-health/health",
        headers={"X-Device-Api-Key": "kunci-device-health-123"},
        json={"jadwal_jam_lalu": 1.5, "dispensasi_jam_lalu": 0.5},
    )
    assert r.status_code == 200
    # response ikut membawa nama_lokasi + platform (kiosk menyegarkan metadata lokalnya)
    assert r.json()["nama_lokasi"] == "Gerbang"
    assert r.json()["platform"] == "windows"
    # verifikasi lewat endpoint baca (guru)
    tok = _login_guru(client, "admin@sekolah.sch.id")
    lst = client.get("/device/status-kesehatan", headers={"Authorization": f"Bearer {tok}"})
    assert lst.status_code == 200
    dev = next(d for d in lst.json() if d["device_id"] == "kiosk-health")
    assert dev["jadwal_jam_lalu"] == 1.5
    assert dev["dispensasi_jam_lalu"] == 0.5
    assert dev["belum_pernah_lapor"] is False


def test_status_kesehatan_menandai_device_bermasalah(client):
    # jadwal_jam_lalu=10 (>6 ambang) harus jadwal_bermasalah=true
    client.post(
        "/device/kiosk-health/health",
        headers={"X-Device-Api-Key": "kunci-device-health-123"},
        json={"jadwal_jam_lalu": 10, "dispensasi_jam_lalu": 0.5},
    )
    tok = _login_guru(client, "admin@sekolah.sch.id")
    lst = client.get("/device/status-kesehatan", headers={"Authorization": f"Bearer {tok}"})
    dev = next(d for d in lst.json() if d["device_id"] == "kiosk-health")
    assert dev["jadwal_bermasalah"] is True
    assert dev["dispensasi_bermasalah"] is False


def test_status_kesehatan_device_belum_pernah_lapor(client):
    # device baru, health_dilaporkan_pada masih NULL -> belum_pernah_lapor=true
    tok = _login_guru(client, "admin@sekolah.sch.id")
    lst = client.get("/device/status-kesehatan", headers={"Authorization": f"Bearer {tok}"})
    dev = next(d for d in lst.json() if d["device_id"] == "kiosk-health")
    assert dev["belum_pernah_lapor"] is True


def test_register_tanpa_device_id_di_generate_otomatis(client):
    """Opsi B: device_id kosong -> server generate dev-xxxxxxxx."""
    tok = _login_guru(client, "admin@sekolah.sch.id")
    r = client.post(
        "/device/register",
        headers={"Authorization": f"Bearer {tok}"},
        json={"nama_lokasi": "Lokasi Otomatis", "platform": "windows"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["device_id"].startswith("dev-")
    assert len(data["device_id"]) == 12  # dev- + 8 karakter
    assert data["api_key"]


def test_register_dengan_device_id_override(client):
    """Opsi B: device_id diisi manual tetap dihormati."""
    tok = _login_guru(client, "admin@sekolah.sch.id")
    r = client.post(
        "/device/register",
        headers={"Authorization": f"Bearer {tok}"},
        json={"device_id": "lab-rpl-01", "nama_lokasi": "Lab RPL", "platform": "windows"},
    )
    assert r.status_code == 200
    assert r.json()["device_id"] == "lab-rpl-01"
