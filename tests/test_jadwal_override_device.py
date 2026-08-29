"""Test endpoint POST /jadwal/override untuk device kiosk (PRD_JADWAL_OVERRIDE_DEVICE).

TC-1 s.d TC-10 dari PRD. Menggunakan TestClient + sqlite in-memory dengan
override get_db, supaya alur auth (get_guru_or_device) dan idempotensi
client_id teruji end-to-end tanpa Postgres.
"""
import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models  # noqa: F401 — register semua model ke Base
from app.main import app
from app.database import get_db
from app.routers.device import hash_api_key

# ─── Fixtures ─────────────────────────────────────────────────

@pytest.fixture()
def engine():
    # StaticPool + share connection: SQLite in-memory but SAMA database
    # untuk semua connection (fixture db_session dan override get_db client),
    # supaya seed data guru/device terlihat oleh request TestClient.
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
    # seed: 1 guru admin, 1 device aktif
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    raw_key = "kunci-device-test-123"
    s.add(models.Device(device_id="kiosk01", nama_lokasi="Gerbang", platform="windows",
                        api_key_hash=hash_api_key(raw_key), aktif=True))
    s.commit()
    yield s
    s.close()

@pytest.fixture()
def client(engine, db_session, monkeypatch):
    def _override_get_db():
        Session = sessionmaker(bind=engine)
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()

DEVICE_HEADERS = {"X-Device-Id": "kiosk01", "X-Device-Api-Key": "kunci-device-test-123"}

# ─── TC-1: Device kirim override valid ───────────────────────

def test_tc1_device_override_valid(client):
    body = {
        "tanggal": "2026-08-29", "jam_masuk": "09:00:00", "jam_pulang": "13:00:00",
        "kelas": "XI", "alasan": "Ujian sekolah", "client_id": str(uuid.uuid4()),
    }
    r = client.post("/jadwal/override", json=body, headers=DEVICE_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sumber"] == "device"
    assert data["client_id"] == body["client_id"]
    assert data["device_id"] == "kiosk01"
    assert data["dibuat_oleh"] is None

# ─── TC-2: Device kirim ulang client_id sama → tidak duplikat ─

def test_tc2_idempotensi_client_id(client):
    cid = str(uuid.uuid4())
    body = {"tanggal": "2026-08-29", "jam_masuk": "09:00:00", "jam_pulang": "13:00:00",
            "client_id": cid}
    r1 = client.post("/jadwal/override", json=body, headers=DEVICE_HEADERS)
    assert r1.status_code == 200
    r2 = client.post("/jadwal/override", json=body, headers=DEVICE_HEADERS)
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    # pastikan cuma 1 baris
    from app.database import get_db as _g
    # hitung via endpoint list (JWT guru)
    tok = _login_guru(client, "admin@sekolah.sch.id")
    lst = client.get("/jadwal/override", headers={"Authorization": f"Bearer {tok}"})
    assert lst.status_code == 200
    assert len([o for o in lst.json() if o["client_id"] == cid]) == 1

# ─── TC-3: Device tanpa client_id → baris baru (client_id NULL) ─

def test_tc3_device_tanpa_client_id(client):
    body = {"tanggal": "2026-08-30", "jam_masuk": "08:00:00", "jam_pulang": "14:00:00"}
    r = client.post("/jadwal/override", json=body, headers=DEVICE_HEADERS)
    assert r.status_code == 200
    assert r.json()["client_id"] is None
    assert r.json()["sumber"] == "device"

# ─── TC-4: Device dengan API Key salah → 401 ────────────────

def test_tc4_api_key_salah(client):
    bad = {"X-Device-Id": "kiosk01", "X-Device-Api-Key": "salah"}
    r = client.post("/jadwal/override", json={"tanggal": "2026-08-29",
                   "jam_masuk": "09:00:00", "jam_pulang": "13:00:00"}, headers=bad)
    assert r.status_code == 401

# ─── TC-5: Device non-aktif → 401 ───────────────────────────

def test_tc5_device_nonaktif(client, db_session):
    db_session.query(models.Device).filter(models.Device.device_id == "kiosk01").update(
        {"aktif": False})
    db_session.commit()
    r = client.post("/jadwal/override", json={"tanggal": "2026-08-29",
                   "jam_masuk": "09:00:00", "jam_pulang": "13:00:00"}, headers=DEVICE_HEADERS)
    assert r.status_code == 401

# ─── TC-6: JWT guru kirim override (backward-compatible) ─────

def test_tc6_jwt_guru_override(client):
    tok = _login_guru(client, "piket@sekolah.sch.id")
    body = {"tanggal": "2026-08-29", "jam_masuk": "07:00:00", "jam_pulang": "15:00:00",
            "kelas": "X", "alasan": "Upacara"}
    r = client.post("/jadwal/override", json=body, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sumber"] == "guru"
    assert data["dibuat_oleh"] == 2
    assert data["device_id"] is None

# ─── TC-7: jam_masuk >= jam_pulang → 400 ────────────────────

def test_tc7_jam_tidak_valid(client):
    body = {"tanggal": "2026-08-29", "jam_masuk": "13:00:00", "jam_pulang": "09:00:00",
            "client_id": str(uuid.uuid4())}
    r = client.post("/jadwal/override", json=body, headers=DEVICE_HEADERS)
    assert r.status_code == 400

# ─── TC-8: Tanpa auth sama sekali → 401 ─────────────────────

def test_tc8_tanpa_auth(client):
    r = client.post("/jadwal/override", json={"tanggal": "2026-08-29",
                   "jam_masuk": "09:00:00", "jam_pulang": "13:00:00"})
    assert r.status_code == 401

# ─── TC-9: Admin edit override dari device (PUT JWT) ────────

def test_tc9_admin_edit_override_device(client):
    cid = str(uuid.uuid4())
    cr = client.post("/jadwal/override", json={"tanggal": "2026-08-29",
                     "jam_masuk": "09:00:00", "jam_pulang": "13:00:00", "client_id": cid},
                     headers=DEVICE_HEADERS)
    oid = cr.json()["id"]
    tok = _login_guru(client, "admin@sekolah.sch.id")
    r = client.put(f"/jadwal/override/{oid}", json={"tanggal": "2026-08-29",
                  "jam_masuk": "10:00:00", "jam_pulang": "12:00:00", "alasan": "Revisi"},
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    assert r.json()["jam_masuk"] == "10:00:00"

# ─── TC-10: Admin hapus override dari device (DELETE JWT) ────

def test_tc10_admin_delete_override_device(client):
    cid = str(uuid.uuid4())
    cr = client.post("/jadwal/override", json={"tanggal": "2026-08-29",
                     "jam_masuk": "09:00:00", "jam_pulang": "13:00:00", "client_id": cid},
                     headers=DEVICE_HEADERS)
    oid = cr.json()["id"]
    tok = _login_guru(client, "admin@sekolah.sch.id")
    r = client.delete(f"/jadwal/override/{oid}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    lst = client.get("/jadwal/override", headers={"Authorization": f"Bearer {tok}"})
    assert all(o["id"] != oid for o in lst.json())

# ─── Helper ──────────────────────────────────────────────────

def _login_guru(client, email):
    """Issue JWT internal tanpa sentuh DB asli (cukup bikin objek Guru ringan)."""
    from app.auth import issue_internal_jwt
    from types import SimpleNamespace
    role = "admin" if "admin" in email else "guru_piket"
    gid = 1 if role == "admin" else 2
    guru = SimpleNamespace(id=gid, email=email, role=role)
    return issue_internal_jwt(guru)
