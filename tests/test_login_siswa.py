"""Test login Google untuk siswa (role tetap "siswa") + isolasi token guru vs siswa.

- POST /auth/login/google: fallback ke Siswa.email kalau bukan guru
- GET /auth/me: bekerja untuk token guru MAUPUN siswa
- GET /siswa/saya, GET /siswa/saya/absensi: self-service, tak bisa lihat data siswa lain
- Token siswa DITOLAK di endpoint guru-only (dan sebaliknya) lewat klaim "tipe"
  (app/auth.py) -- ini yang mencegah id numerik siswa "ketuker" jadi guru id
  yang sama saat keduanya kebetulan auto-increment dari 1.
"""
import uuid
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401
from app.main import app
from app.routers import login as login_module
from app.auth import issue_internal_jwt, issue_siswa_jwt


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    # id=1 guru dan id=1 siswa SENGAJA sama -- ini justru skenario yang harus
    # dibuktikan aman (lihat docstring modul).
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Kelas(id=1, nama="XI"))
    s.add(models.Siswa(id=1, nis="22001", nama="Budi", kelas_id=1, email="budi@sekolah.sch.id", aktif=True))
    s.add(models.Siswa(id=2, nis="22002", nama="Sri", kelas_id=1, email="sri@sekolah.sch.id", aktif=True))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
    def _get_db():
        Session = sessionmaker(bind=engine)
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _mock_google(monkeypatch, email: str):
    # login_google() memanggil verify_google_id_token via `from app.auth import
    # verify_google_id_token` -- binding itu ada di namespace app.routers.login,
    # bukan app.auth, jadi patch harus di situ supaya benar-benar terpakai.
    monkeypatch.setattr(
        login_module, "verify_google_id_token",
        lambda token: {"email": email, "email_verified": True},
    )


# ─── Login Google -- fallback ke siswa ────────────────────────

def test_login_google_siswa_terdaftar_role_siswa(client, db_session, monkeypatch):
    _mock_google(monkeypatch, "budi@sekolah.sch.id")
    r = client.post("/auth/login/google", json={"google_id_token": "dummy"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "siswa"
    assert body["email"] == "budi@sekolah.sch.id"
    assert body["nama"] == "Budi"
    assert body["nis"] == "22001"  # dipakai client Android mencocokkan ke siswa_cache lokal


def test_login_google_guru_tetap_prioritas(client, db_session, monkeypatch):
    _mock_google(monkeypatch, "admin@sekolah.sch.id")
    r = client.post("/auth/login/google", json={"google_id_token": "dummy"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


def test_login_google_email_tak_dikenal_ditolak(client, db_session, monkeypatch):
    _mock_google(monkeypatch, "siapa@sekolah.sch.id")
    r = client.post("/auth/login/google", json={"google_id_token": "dummy"})
    assert r.status_code == 403


def test_login_google_siswa_nonaktif_ditolak(client, db_session, monkeypatch):
    db_session.query(models.Siswa).filter_by(id=1).update({"aktif": False})
    db_session.commit()
    _mock_google(monkeypatch, "budi@sekolah.sch.id")
    r = client.post("/auth/login/google", json={"google_id_token": "dummy"})
    assert r.status_code == 403


# ─── /auth/me untuk kedua tipe ────────────────────────────────

def test_me_untuk_token_siswa(client, db_session):
    siswa = db_session.query(models.Siswa).filter_by(id=1).first()
    token = issue_siswa_jwt(siswa)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "siswa"
    assert r.json()["email"] == "budi@sekolah.sch.id"


def test_me_untuk_token_guru(client, db_session):
    guru = db_session.query(models.Guru).filter_by(id=1).first()
    token = issue_internal_jwt(guru)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


# ─── Isolasi token: siswa TIDAK bisa dianggap guru walau id sama ──

def test_token_siswa_ditolak_di_endpoint_guru_only(client, db_session):
    siswa = db_session.query(models.Siswa).filter_by(id=1).first()  # id=1, SAMA dengan guru id=1
    token = issue_siswa_jwt(siswa)
    r = client.get("/guru", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401  # bukan malah dianggap guru id=1 (admin)


def test_token_guru_ditolak_di_endpoint_siswa_only(client, db_session):
    guru = db_session.query(models.Guru).filter_by(id=1).first()
    token = issue_internal_jwt(guru)
    r = client.get("/siswa/saya", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ─── Self-service siswa ───────────────────────────────────────

def test_profil_saya(client, db_session):
    siswa = db_session.query(models.Siswa).filter_by(id=1).first()
    token = issue_siswa_jwt(siswa)
    r = client.get("/siswa/saya", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["nis"] == "22001"


def test_absensi_saya_hanya_milik_sendiri(client, db_session):
    now = datetime.combine(date.today(), time(7, 0))
    db_session.add(models.Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(), type="MASUK",
        jam_aktual=now, status_kehadiran_otomatis="NORMAL",
    ))
    db_session.add(models.Absensi(
        record_id=uuid.uuid4(), siswa_id=2, tanggal=date.today(), type="MASUK",
        jam_aktual=now, status_kehadiran_otomatis="NORMAL",
    ))
    db_session.commit()

    siswa1 = db_session.query(models.Siswa).filter_by(id=1).first()
    token = issue_siswa_jwt(siswa1)
    r = client.get("/siswa/saya/absensi", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1  # bukan 2 -- tidak lihat punya siswa lain


# ─── Email siswa: uniqueness ──────────────────────────────────

def test_create_siswa_email_duplikat_ditolak(client, db_session):
    guru = db_session.query(models.Guru).filter_by(id=1).first()
    token = issue_internal_jwt(guru)
    r = client.post("/siswa", headers={"Authorization": f"Bearer {token}"}, json={
        "nis": "22099", "nama": "Baru", "kelas_id": 1, "email": "budi@sekolah.sch.id",
    })
    assert r.status_code == 409
