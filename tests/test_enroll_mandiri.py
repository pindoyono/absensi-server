"""Daftar wajah mandiri oleh siswa + verifikasi admin."""
import base64
import uuid
from datetime import date, datetime, time
from types import SimpleNamespace

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

RAW = "kunci-mandiri"
DEV = {"X-Device-Id": "kioskM", "X-Device-Api-Key": RAW}
FOTO_B64 = base64.b64encode(b"\xff\xd8\xff\xe0jpeg-palsu").decode()
EMB = [0.01 * i for i in range(128)]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@s.sch.id", role="admin", aktif=True))
    s.add(models.Device(device_id="kioskM", nama_lokasi="Gerbang", platform="android",
                        api_key_hash=hash_api_key(RAW), aktif=True, izin_enroll_mandiri=False))
    s.add(models.Siswa(id=5, nis="55501", nama="Rani", aktif=True))
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


def _admin():
    return {"Authorization": f"Bearer {issue_internal_jwt(SimpleNamespace(id=1, email='admin@s.sch.id', role='admin'))}"}


def _enroll_mandiri(client, **kw):
    body = {"embedding": EMB, "model_version": "arcface-android", "mandiri": True, "foto_jpeg": FOTO_B64}
    body.update(kw)
    return client.post("/siswa/5/enroll", headers=DEV, json=body)


def test_device_tak_diizinkan_ditolak(client):
    assert _enroll_mandiri(client).status_code == 403


def test_mandiri_wajib_foto(client, db_session):
    db_session.query(models.Device).filter_by(device_id="kioskM").update({"izin_enroll_mandiri": True})
    db_session.commit()
    assert _enroll_mandiri(client, foto_jpeg=None).status_code == 422


def test_alur_lengkap_daftar_konfirmasi(client, db_session):
    db_session.query(models.Device).filter_by(device_id="kioskM").update({"izin_enroll_mandiri": True})
    db_session.commit()

    r = _enroll_mandiri(client)
    assert r.status_code == 200, r.text
    assert r.json()["menunggu_verifikasi"] is True

    db_session.expire_all()
    s = db_session.get(models.Siswa, 5)
    assert s.enrolled is True and s.enroll_mandiri_pending is True and s.enroll_foto is not None

    # muncul di daftar pending admin, dengan foto
    pend = client.get("/siswa/enroll-mandiri/pending", headers=_admin()).json()
    assert len(pend) == 1 and pend[0]["siswa_id"] == 5 and pend[0]["foto_jpeg"] == FOTO_B64

    # sync absensi ditolak selama pending
    rec = {"records": [{
        "record_id": str(uuid.uuid4()), "siswa_id": 5, "tanggal": date.today().isoformat(),
        "type": "MASUK", "jam_aktual": datetime.combine(date.today(), time(7, 5)).isoformat(),
        "status_kehadiran_otomatis": "NORMAL", "device_id": "kioskM",
    }]}
    sync = client.post("/absensi/sync", json=rec, headers=DEV).json()
    assert sync["hasil"][0]["status"] == "ditolak_kebijakan"
    assert "verifikasi" in sync["hasil"][0]["pesan"].lower()

    # admin konfirmasi → foto hilang, pending false
    ok = client.post("/siswa/5/enroll-mandiri/konfirmasi", headers=_admin())
    assert ok.status_code == 200, ok.text
    db_session.expire_all()
    s = db_session.get(models.Siswa, 5)
    assert s.enroll_mandiri_pending is False and s.enroll_foto is None

    # sekarang absensi diterima
    rec["records"][0]["record_id"] = str(uuid.uuid4())
    sync2 = client.post("/absensi/sync", json=rec, headers=DEV).json()
    assert sync2["disimpan"] == 1


def test_tolak_menghapus_embedding(client, db_session):
    db_session.query(models.Device).filter_by(device_id="kioskM").update({"izin_enroll_mandiri": True})
    db_session.commit()
    _enroll_mandiri(client)

    r = client.post("/siswa/5/enroll-mandiri/tolak", headers=_admin())
    assert r.status_code == 200, r.text
    db_session.expire_all()
    s = db_session.get(models.Siswa, 5)
    assert s.enrolled is False and s.enroll_mandiri_pending is False and s.enroll_foto is None
    assert db_session.query(models.FaceEmbedding).filter_by(siswa_id=5).first() is None


def test_konfirmasi_yang_tak_pending_409(client):
    assert client.post("/siswa/5/enroll-mandiri/konfirmasi", headers=_admin()).status_code == 409


def test_enroll_guru_batalkan_pending(client, db_session):
    """Enroll oleh guru (JWT) atas siswa yang sedang pending → langsung tepercaya."""
    db_session.query(models.Siswa).filter_by(id=5).update(
        {"enroll_mandiri_pending": True, "enroll_foto": b"x", "enrolled": True})
    db_session.add(models.FaceEmbedding(siswa_id=5, embedding_encrypted=b"x", model_version="v1"))
    db_session.commit()

    r = client.post("/siswa/5/enroll", headers=_admin(),
                    json={"embedding": EMB, "model_version": "arcface-android"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    s = db_session.get(models.Siswa, 5)
    assert s.enroll_mandiri_pending is False and s.enroll_foto is None


def test_health_balikkan_izin_enroll_mandiri(client, db_session):
    db_session.query(models.Device).filter_by(device_id="kioskM").update({"izin_enroll_mandiri": True})
    db_session.commit()
    r = client.post("/device/kioskM/health", headers=DEV, json={})
    assert r.status_code == 200
    assert r.json()["izin_enroll_mandiri"] is True


def test_patch_device_set_izin(client, db_session):
    r = client.patch("/device/kioskM", headers=_admin(), json={"izin_enroll_mandiri": True})
    assert r.status_code == 200, r.text
    assert r.json()["izin_enroll_mandiri"] is True
