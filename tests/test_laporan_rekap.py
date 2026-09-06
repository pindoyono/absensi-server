"""GET /laporan/rekap — 'tanpa keterangan' hanya menghitung hari sekolah
(Senin–Jumat, minus JadwalOverride libur sekolah-wide)."""
import uuid
from datetime import date, datetime, time

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


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Siswa(id=1, nis="111", nama="Ani", kelas="XI", aktif=True))
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


def _hdr():
    return {"Authorization": f"Bearer {issue_internal_jwt(SimpleNamespace(id=1, email='admin@sekolah.sch.id', role='admin'))}"}


def _rekap(client, dari, sampai):
    r = client.get("/laporan/rekap", headers=_hdr(), params={"dari_tanggal": dari, "sampai_tanggal": sampai})
    assert r.status_code == 200, r.text
    return r.json()["data"][0]


def test_akhir_pekan_tidak_dihitung_sebagai_alpa(client):
    # Sen 2026-09-07 .. Min 2026-09-13 = 5 hari kerja + 2 akhir pekan, 0 absen
    row = _rekap(client, "2026-09-07", "2026-09-13")
    assert row["tanpa_keterangan_estimasi"] == 5  # bukan 7


def test_hari_libur_override_dikurangi(client, db_session):
    # Rabu 2026-09-09 ditandai libur (jam kosong) → 4 hari sekolah, bukan 5
    db_session.add(models.JadwalOverride(tanggal=date(2026, 9, 9), kelas=None,
                                         jam_masuk=None, jam_pulang=None, alasan="libur nasional"))
    db_session.commit()
    row = _rekap(client, "2026-09-07", "2026-09-13")
    assert row["tanpa_keterangan_estimasi"] == 4


def test_record_mengurangi_tanpa_keterangan(client, db_session):
    db_session.add(models.Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date(2026, 9, 8), type="MASUK",
        jam_aktual=datetime.combine(date(2026, 9, 8), time(7, 0)), status_kehadiran_otomatis="NORMAL",
    ))
    db_session.commit()
    row = _rekap(client, "2026-09-07", "2026-09-13")
    assert row["hadir"] == 1
    assert row["tanpa_keterangan_estimasi"] == 4  # 5 hari sekolah - 1 hadir
