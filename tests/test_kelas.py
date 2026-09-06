"""Manajemen Kelas (rombel) — CRUD, guard hapus, pindah rombel, kompat kiosk."""
import io
import uuid
from datetime import date, time
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

RAW_KEY = "kunci-kelas-test"
DEV = {"X-Device-Id": "kioskA", "X-Device-Api-Key": RAW_KEY}


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Guru(id=1, nama="Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Wali A", email="wali@sekolah.sch.id", role="wali_kelas", aktif=True))
    s.add(models.Device(device_id="kioskA", platform="android",
                        api_key_hash=hash_api_key(RAW_KEY), aktif=True))
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


def _hdr(gid=1, email="admin@sekolah.sch.id", role="admin"):
    return {"Authorization": f"Bearer {issue_internal_jwt(SimpleNamespace(id=gid, email=email, role=role))}"}


def test_crud_kelas(client):
    r = client.post("/kelas", headers=_hdr(), json={"nama": "XI TE 1", "tingkat": "XI"})
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    assert client.post("/kelas", headers=_hdr(), json={"nama": "XI TE 1"}).status_code == 409

    r = client.put(f"/kelas/{kid}", headers=_hdr(), json={"nama": "XI TE 1 (revisi)", "wali_id": 2})
    assert r.status_code == 200, r.text
    assert r.json()["wali_nama"] == "Wali A"

    r = client.get("/kelas", headers=_hdr())
    assert r.status_code == 200
    assert [k["nama"] for k in r.json()] == ["XI TE 1 (revisi)"]

    assert client.delete(f"/kelas/{kid}", headers=_hdr()).status_code == 200
    assert client.get("/kelas", headers=_hdr()).json() == []


def test_delete_ditolak_kalau_masih_ada_siswa(client, db_session):
    k = models.Kelas(nama="X RPL 1")
    db_session.add(k)
    db_session.commit()
    db_session.add(models.Siswa(nis="1", nama="Budi", kelas_id=k.id, aktif=True))
    db_session.commit()

    r = client.delete(f"/kelas/{k.id}", headers=_hdr())
    assert r.status_code == 409
    assert "1 siswa" in r.json()["detail"]


def test_pindah_kelas_siswa(client, db_session):
    a = models.Kelas(nama="A")
    b = models.Kelas(nama="B")
    db_session.add_all([a, b])
    db_session.commit()
    s = models.Siswa(nis="9", nama="Sri", kelas_id=a.id, aktif=True)
    db_session.add(s)
    db_session.commit()

    r = client.patch(f"/siswa/{s.id}", headers=_hdr(), json={"kelas_id": b.id})
    assert r.status_code == 200, r.text
    assert r.json()["kelas"] == "B"
    assert r.json()["kelas_id"] == b.id

    # keluarkan dari rombel
    r = client.patch(f"/siswa/{s.id}", headers=_hdr(), json={"kelas_id": None})
    assert r.status_code == 200
    assert r.json()["kelas"] == ""

    # kelas_id ngawur → 422
    assert client.patch(f"/siswa/{s.id}", headers=_hdr(), json={"kelas_id": 9999}).status_code == 422


def test_list_kelas_via_device_auth(client, db_session):
    db_session.add(models.Kelas(nama="XII"))
    db_session.commit()
    r = client.get("/kelas", headers=DEV)
    assert r.status_code == 200
    assert r.json()[0]["nama"] == "XII"


def test_filter_siswa_by_kelas_id_dan_tanpa_rombel(client, db_session):
    k = models.Kelas(nama="K1")
    db_session.add(k)
    db_session.commit()
    db_session.add(models.Siswa(nis="1", nama="Punya", kelas_id=k.id, aktif=True))
    db_session.add(models.Siswa(nis="2", nama="Belum", kelas_id=None, aktif=True))
    db_session.commit()

    assert {s["nama"] for s in client.get(f"/siswa?kelas_id={k.id}", headers=_hdr()).json()} == {"Punya"}
    # sentinel 0 = belum ada rombel
    assert {s["nama"] for s in client.get("/siswa?kelas_id=0", headers=_hdr()).json()} == {"Belum"}
    # kompat: filter pakai NAMA
    assert {s["nama"] for s in client.get("/siswa?kelas=K1", headers=_hdr()).json()} == {"Punya"}


def test_import_csv_kelas_id(client, db_session):
    k = models.Kelas(nama="XI IMPOR")
    db_session.add(k)
    db_session.commit()

    csv_ok = f"nis,nama,kelas_id\n001,Andi,{k.id}\n002,Bima,\n"
    r = client.post("/siswa/import", headers=_hdr(),
                    files={"file": ("s.csv", io.BytesIO(csv_ok.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["ditambahkan"] == 2

    csv_bad = "nis,nama,kelas_id\n003,Cika,9999\n"
    r = client.post("/siswa/import", headers=_hdr(),
                    files={"file": ("s.csv", io.BytesIO(csv_bad.encode()), "text/csv")})
    assert r.json()["ditambahkan"] == 0
    assert r.json()["baris_error"]

    andi = client.get("/siswa?kelas=XI IMPOR", headers=_hdr()).json()
    assert {s["nama"] for s in andi} == {"Andi"}


def test_jadwal_efektif_resolusi_nama_kelas_kiosk(client, db_session):
    from app.services.waktu import hari_ini

    k = models.Kelas(nama="XI TKJ")
    db_session.add(k)
    db_session.commit()
    for h in ("SENIN", "SELASA", "RABU", "KAMIS", "JUMAT"):
        db_session.add(models.JadwalStandar(hari=h, kelas_id=k.id, jam_masuk=time(7, 0), jam_pulang=time(15, 0)))
        db_session.add(models.JadwalStandar(hari=h, kelas_id=None, jam_masuk=time(8, 0), jam_pulang=time(14, 0)))
    db_session.commit()

    # kiosk kirim NAMA kelas — endpoint tak 500 walau nama tak dikenal
    r = client.get("/jadwal/efektif?kelas=NGACO", headers=DEV)
    assert r.status_code == 200, r.text

    if hari_ini().weekday() >= 5:
        pytest.skip("akhir pekan — /jadwal/efektif tidak punya param tanggal")

    # hari sekolah → nama kelas spesifik menang atas school-wide
    r = client.get("/jadwal/efektif?kelas=XI TKJ", headers=DEV)
    assert r.json()["jam_masuk"] == "07:00:00"
    r = client.get("/jadwal/efektif?kelas=NGACO", headers=DEV)
    assert r.json()["jam_masuk"] == "08:00:00"


def test_jadwal_override_device_kirim_nama_kelas(client, db_session):
    k = models.Kelas(nama="XI TKR")
    db_session.add(k)
    db_session.commit()
    body = {
        "tanggal": "2026-09-10", "jam_masuk": "09:00:00", "jam_pulang": "13:00:00",
        "kelas": "XI TKR", "alasan": "Ujian", "client_id": str(uuid.uuid4()),
    }
    r = client.post("/jadwal/override", json=body, headers=DEV)
    assert r.status_code == 200, r.text
    assert r.json()["kelas_id"] == k.id
    assert r.json()["kelas"] == "XI TKR"


def test_guru_out_wali_kelas_derived(client, db_session):
    k = models.Kelas(nama="XI WALI", wali_id=2)
    db_session.add(k)
    db_session.commit()
    r = client.get("/guru", headers=_hdr())
    assert r.status_code == 200
    wali = [g for g in r.json() if g["id"] == 2][0]
    assert wali["wali_kelas"] == ["XI WALI"]
