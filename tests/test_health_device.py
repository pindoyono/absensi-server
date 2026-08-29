from datetime import datetime, timedelta

from app.models import Device
from app.routers import device as device_router
from app.database import get_db
from fastapi.testclient import TestClient
from app.main import app


def _client_with_db(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_report_health_menambah_kolom(db_session):
    db_session.add(Device(
        device_id="dev-health-1", platform="windows",
        api_key_hash="x", aktif=True,
        last_seen_at=datetime.utcnow(),
    ))
    db_session.commit()

    client = _client_with_db(db_session)
    r = client.post("/device/dev-health-1/health", json={
        "jadwal_jam_lalu": 2.5, "dispensasi_jam_lalu": 0.1,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    d = db_session.query(Device).filter(Device.device_id == "dev-health-1").first()
    assert d.jadwal_jam_lalu == 2.5
    assert d.dispensasi_jam_lalu == 0.1
    assert d.health_dilaporkan_pada is not None


def test_status_kesehatan_mendeteksi_basi_dan_online(db_session):
    # device online (last_seen < 5 menit) tapi jadwal belum pernah sync (None)
    db_session.add(Device(
        device_id="dev-basi-1", platform="windows",
        api_key_hash="x", aktif=True,
        last_seen_at=datetime.utcnow() - timedelta(seconds=30),
    ))
    db_session.commit()

    client = _client_with_db(db_session)
    r = client.get("/status-kesehatan")
    assert r.status_code == 200
    body = r.json()
    assert body["device_basi_dan_online"] == 1
    dev = body["devices"][0]
    assert dev["online"] is True
    assert dev["jadwal_basi"] is True
    assert dev["basi_dan_online"] is True
