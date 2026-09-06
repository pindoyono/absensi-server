"""Test retensi data wajah: POST /admin/retensi/bersihkan-wajah.

Kebijakan (lihat app/routers/retensi.py):
1. Embedding berumur > 3 tahun 1 bulan (sejak `dibuat_pada`) pada siswa
   yang MASIH aktif -> siswa dinonaktifkan (fase 1), belum dihapus.
2. Embedding siswa yang SUDAH nonaktif, sudah kedaluwarsa umurnya, DAN
   sudah lewat jeda propagasi 7 hari sejak `diperbarui_pada` -> dihapus
   permanen (fase 2). Baris `siswa` tidak disentuh.
3. Endpoint menolak tanpa X-Retensi-Secret yang benar.
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
from app.config import settings
from app.services.crypto import encrypt_embedding

SECRET = "rahasia-cron-test"


@pytest.fixture(autouse=True)
def _isi_secret():
    lama = settings.retensi_cron_secret
    settings.retensi_cron_secret = SECRET
    yield
    settings.retensi_cron_secret = lama


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
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


def _seed(db, *, siswa_id, nis, dibuat_pada, diperbarui_pada=None, aktif=True):
    siswa = models.Siswa(id=siswa_id, nis=nis, nama=f"Siswa {siswa_id}", aktif=aktif)
    db.add(siswa)
    db.flush()
    db.add(models.FaceEmbedding(
        siswa_id=siswa_id,
        embedding_encrypted=encrypt_embedding([0.1] * 64),
        model_version="minifasnet-v1",
        dibuat_pada=dibuat_pada,
        diperbarui_pada=diperbarui_pada or dibuat_pada,
    ))
    db.commit()
    return siswa


HEADERS_OK = {"X-Retensi-Secret": SECRET}


def test_tolak_tanpa_secret_benar(client):
    r = client.post("/admin/retensi/bersihkan-wajah", headers={"X-Retensi-Secret": "salah"})
    assert r.status_code == 401


def test_tolak_kalau_secret_belum_dikonfigurasi(client):
    settings.retensi_cron_secret = ""
    r = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r.status_code == 503


def test_embedding_belum_kedaluwarsa_tidak_disentuh(client, db_session):
    _seed(db_session, siswa_id=1, nis="22001", dibuat_pada=datetime.utcnow() - timedelta(days=30))
    r = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dinonaktifkan"] == 0
    assert body["dihapus_permanen"] == 0
    row = db_session.query(models.Siswa).get(1)
    assert row.aktif is True


def test_fase1_nonaktifkan_siswa_aktif_yang_kedaluwarsa(client, db_session):
    tua = datetime.utcnow() - timedelta(days=365 * 3 + 60)  # lewat 3th1bln
    _seed(db_session, siswa_id=1, nis="22001", dibuat_pada=tua, aktif=True)

    r = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dinonaktifkan"] == 1
    assert body["dihapus_permanen"] == 0  # baru dinonaktifkan, belum lewat jeda 7 hari

    siswa = db_session.query(models.Siswa).get(1)
    emb = db_session.query(models.FaceEmbedding).filter_by(siswa_id=1).first()
    assert siswa.aktif is False
    assert emb is not None  # embedding masih ada — belum dihapus permanen


def test_fase2_hapus_permanen_setelah_lewat_jeda_propagasi(client, db_session):
    tua = datetime.utcnow() - timedelta(days=365 * 3 + 60)
    lewat_jeda = datetime.utcnow() - timedelta(days=8)
    _seed(db_session, siswa_id=1, nis="22001", dibuat_pada=tua, diperbarui_pada=lewat_jeda, aktif=False)

    r = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dinonaktifkan"] == 0  # sudah nonaktif dari awal
    assert body["dihapus_permanen"] == 1
    assert body["siswa_id_dihapus_permanen"] == [1]

    assert db_session.query(models.FaceEmbedding).filter_by(siswa_id=1).first() is None
    # baris siswa TIDAK dihapus — riwayat absensi tetap utuh
    assert db_session.query(models.Siswa).get(1) is not None


def test_siswa_nonaktif_kedaluwarsa_tapi_belum_lewat_jeda_belum_dihapus(client, db_session):
    tua = datetime.utcnow() - timedelta(days=365 * 3 + 60)
    baru_saja = datetime.utcnow() - timedelta(days=1)
    _seed(db_session, siswa_id=1, nis="22001", dibuat_pada=tua, diperbarui_pada=baru_saja, aktif=False)

    r = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r.status_code == 200, r.text
    assert r.json()["dihapus_permanen"] == 0
    assert db_session.query(models.FaceEmbedding).filter_by(siswa_id=1).first() is not None


def test_idempotent_dijalankan_berulang(client, db_session):
    tua = datetime.utcnow() - timedelta(days=365 * 3 + 60)
    _seed(db_session, siswa_id=1, nis="22001", dibuat_pada=tua, aktif=True)

    r1 = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r1.json()["dinonaktifkan"] == 1

    # Jalan lagi langsung — siswa sudah nonaktif tapi belum lewat jeda, tidak error/duplikat.
    r2 = client.post("/admin/retensi/bersihkan-wajah", headers=HEADERS_OK)
    assert r2.status_code == 200
    assert r2.json()["dinonaktifkan"] == 0
    assert r2.json()["dihapus_permanen"] == 0
