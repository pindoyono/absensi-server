"""Test PRD_EMBEDDING_SYNC: sinkronisasi status aktif/hapus siswa pada
GET /embeddings/sync.

Acceptance criteria PRD:
1. Siswa nonaktif (aktif=False) tetap muncul di payload sync dengan
   field "aktif": false (SRV-1, SRV-2).
2. Siswa aktif muncul dengan "aktif": true.
3. Filter diperbarui_sejak tetap bekerja (incremental sync).
4. DELETE /siswa/{id} (soft delete) menonaktifkan siswa sehingga
   client kiosk bisa menghapus cache lokalnya.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401 — register semua model ke Base
from app.main import app
from app.routers.device import hash_api_key
from app.services.crypto import encrypt_embedding


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
    s.add(models.Device(device_id="kiosk01", nama_lokasi="Gerbang", platform="windows",
                        api_key_hash=hash_api_key("kunci-device-test-123"), aktif=True))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
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


def _seed_siswa_dengan_embedding(db, *, siswa_id, nis, nama, kelas, aktif=True):
    siswa = models.Siswa(id=siswa_id, nis=nis, nama=nama, kelas=kelas, aktif=aktif)
    db.add(siswa)
    db.flush()
    db.add(models.FaceEmbedding(
        siswa_id=siswa_id,
        embedding_encrypted=encrypt_embedding([0.1] * 64),
        model_version="minifasnet-v1",
    ))
    db.commit()
    return siswa


def _sync(client):
    r = client.get("/embeddings/sync", headers=DEVICE_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ─── SRV-2: field aktif ada di payload ───────────────────────

def test_sync_menyertakan_field_aktif(client, db_session):
    _seed_siswa_dengan_embedding(db_session, siswa_id=1, nis="22001",
                                 nama="Ahmad", kelas="XI", aktif=True)
    data = _sync(client)
    assert data["jumlah"] == 1
    item = data["data"][0]
    assert item["siswa_id"] == 1
    assert item["aktif"] is True


# ─── SRV-1: siswa nonaktif tetap terkirim ────────────────────

def test_sync_menyertakan_siswa_nonaktif(client, db_session):
    _seed_siswa_dengan_embedding(db_session, siswa_id=1, nis="22001",
                                 nama="Ahmad", kelas="XI", aktif=True)
    _seed_siswa_dengan_embedding(db_session, siswa_id=2, nis="22002",
                                 nama="Budi", kelas="XII", aktif=False)
    data = _sync(client)
    assert data["jumlah"] == 2
    by_id = {d["siswa_id"]: d for d in data["data"]}
    assert by_id[1]["aktif"] is True
    assert by_id[2]["aktif"] is False


# ─── Incremental sync tetap jalan ────────────────────────────

def test_sync_diperbarui_sejak(client, db_session):
    _seed_siswa_dengan_embedding(db_session, siswa_id=1, nis="22001",
                                 nama="Ahmad", kelas="XI", aktif=True)
    _seed_siswa_dengan_embedding(db_session, siswa_id=2, nis="22002",
                                 nama="Budi", kelas="XII", aktif=False)

    # semua embedding baru dibuat "sekarang" → sync dengan cutoff masa lalu
    # harus mengembalikan keduanya
    cutoff = datetime.utcnow() - timedelta(hours=1)
    r = client.get("/embeddings/sync", headers={**DEVICE_HEADERS,
                   "X-Device-Api-Key": "kunci-device-test-123"},
                   params={"diperbarui_sejak": cutoff.isoformat()})
    assert r.status_code == 200
    assert r.json()["jumlah"] == 2

    # cutoff di masa depan → tidak ada yang berubah sejak itu
    r = client.get("/embeddings/sync", headers=DEVICE_HEADERS,
                   params={"diperbarui_sejak": (datetime.utcnow() + timedelta(hours=1)).isoformat()})
    assert r.status_code == 200
    assert r.json()["jumlah"] == 0


# ─── Soft delete via DELETE /siswa/{id} ──────────────────────

def test_delete_siswa_menonaktifkan_dan_terkirim_di_sync(client, db_session):
    _seed_siswa_dengan_embedding(db_session, siswa_id=1, nis="22001",
                                 nama="Ahmad", kelas="XI", aktif=True)

    # login admin (JWT internal)
    from app.auth import issue_internal_jwt
    from types import SimpleNamespace
    token = issue_internal_jwt(SimpleNamespace(id=1, email="admin@sekolah.sch.id", role="admin"))

    r = client.delete("/siswa/1", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["aktif"] is False

    # baris tetap ada (soft delete), aktif=False
    row = db_session.query(models.Siswa).filter(models.Siswa.id == 1).first()
    assert row is not None
    assert row.aktif is False

    # sync mengirim status nonaktif → client kiosk bisa hapus cache lokal
    data = _sync(client)
    assert data["jumlah"] == 1
    assert data["data"][0]["aktif"] is False


# ─── Auth device tetap berlaku ───────────────────────────────

def test_sync_api_key_salah(client):
    r = client.get("/embeddings/sync", headers={
        "X-Device-Id": "kiosk01", "X-Device-Api-Key": "salah"})
    assert r.status_code == 401
