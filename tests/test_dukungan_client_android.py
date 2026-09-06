"""Test perubahan server untuk client Android — docs/PRD_DUKUNGAN_CLIENT_ANDROID.md

- R-P0-1: intake absensi menerima kategori dispensasi (SAKIT/IZIN/...) tanpa 422 batch
- R-P0-2: POST /device/{id}/health menerima body kiosk apa adanya (field ekstra diabaikan)
- R-P1-1: face_encryption_key di response /device/register
- R-P1-2: GET /auth/roster (device-auth)
- R-P1-4: POST /siswa/{id}/enroll via device-auth

Catatan: mekanisme & penyimpanan health device diuji lengkap di
tests/test_device_health.py (fitur milik branch device-health). Di sini
hanya memastikan endpoint tsb tetap kompatibel dengan body yang dikirim
client Android (superset field), supaya integrasi client tidak menggagalkan
seluruh siklus sync.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401
from app.main import app
from app.services.device_auth import hash_api_key

RAW_KEY = "kunci-device-test-abc"
DEV = {"X-Device-Id": "kiosk01", "X-Device-Api-Key": RAW_KEY}


def _hari_ini() -> str:
    return ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU", "MINGGU"][date.today().weekday()]


def _tanggal_hari_sekolah() -> date:
    """Tanggal nyata yang jatuh di hari sekolah (SENIN-JUMAT).

    `_ambil_jadwal_efektif()` (app/routers/absensi.py) memetakan weekday() dari
    TANGGAL RECORD itu sendiri ke nama hari, dan langsung return None (tidak
    ada jadwal) untuk Sabtu/Minggu -- beda dengan fixture db_session di sini
    yang cuma men-seed JadwalStandar berlabel "SENIN" saat hari ini akhir
    pekan. Tanpa penyesuaian ini, tes yang menguji validasi jendela waktu jadi
    flaky tergantung hari dijalankannya: kalau hari ini kebetulan Sabtu/Minggu,
    validasi kebijakan dilewati sama sekali dan absen tersimpan begitu saja.
    """
    hari_ini = date.today()
    if hari_ini.weekday() >= 5:  # 5=SABTU, 6=MINGGU
        return hari_ini + timedelta(days=7 - hari_ini.weekday())  # SENIN berikutnya
    return hari_ini


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine)()
    s.add(models.Device(device_id="kiosk01", nama_lokasi="Gerbang", platform="android",
                        api_key_hash=hash_api_key(RAW_KEY), aktif=True))
    s.add(models.Guru(id=1, nama="Bu Admin", email="admin@sekolah.sch.id", role="admin", aktif=True))
    s.add(models.Guru(id=2, nama="Pak Piket", email="piket@sekolah.sch.id", role="guru_piket", aktif=True))
    s.add(models.Guru(id=3, nama="Mantan", email="mantan@sekolah.sch.id", role="guru_piket", aktif=False))
    s.add(models.Kelas(id=1, nama="XI"))
    s.add(models.Kelas(id=2, nama="XII"))
    s.add(models.Siswa(id=1, nis="12345", nama="Budi", kelas_id=1, aktif=True))
    # Hari sekolah SENIN..JUMAT; akhir pekan pakai SENIN supaya validasi jendela tetap jalan.
    hari = _hari_ini()
    if hari in ("SABTU", "MINGGU"):
        hari = "SENIN"
    s.add(models.JadwalStandar(hari=hari, kelas_id=1, jam_masuk=time(7, 0), jam_pulang=time(15, 0)))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db_session):
    def _get_db():
        s = sessionmaker(bind=engine)()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _rec(**kw):
    base = dict(
        record_id=str(uuid.uuid4()), siswa_id=1, tanggal=date.today().isoformat(),
        type="MASUK", jam_aktual=datetime.combine(date.today(), time(7, 5)).isoformat(),
        status_kehadiran_otomatis="NORMAL", device_id="kiosk01",
    )
    base.update(kw)
    return base


# ---------- R-P0-1 ----------

def test_sync_menerima_kategori_dispensasi_tanpa_422(client, db_session):
    db_session.add(models.Dispensasi(siswa_id=1, tanggal=date.today(), jenis="PULANG_CEPAT",
                                     kategori="SAKIT", alasan="demam", dibuat_oleh=1))
    db_session.commit()
    batch = {"records": [
        _rec(type="MASUK"),
        _rec(type="PULANG", status_kehadiran_otomatis="SAKIT",
             jam_aktual=datetime.combine(date.today(), time(10, 0)).isoformat()),
    ]}
    r = client.post("/absensi/sync", json=batch, headers=DEV)
    assert r.status_code == 200, r.text
    assert r.json()["disimpan"] == 2


def test_sync_pulang_cepat_tanpa_dispensasi_ditolak_bukan_422(client):
    tanggal = _tanggal_hari_sekolah()
    batch = {"records": [_rec(
        tanggal=tanggal.isoformat(),
        type="PULANG", status_kehadiran_otomatis="IZIN",
        jam_aktual=datetime.combine(tanggal, time(9, 0)).isoformat(),
    )]}
    r = client.post("/absensi/sync", json=batch, headers=DEV)
    assert r.status_code == 200, r.text
    assert r.json()["hasil"][0]["status"] == "ditolak_kebijakan"


# ---------- R-P0-2 (kompatibilitas body client Android) ----------

def test_device_health_menerima_body_kiosk_penuh(client, db_session):
    """Client Android mengirim superset field (embedding_hari_lalu, pending_kirim,
    app_version) — server device-health hanya butuh jadwal/dispensasi; field
    ekstra harus diabaikan, BUKAN 422."""
    r = client.post("/device/kiosk01/health", headers=DEV, json={
        "jadwal_jam_lalu": 2.6, "dispensasi_jam_lalu": 1.0,
        "embedding_hari_lalu": 0, "pending_kirim": 3, "app_version": "1.0.0",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    dev = db_session.query(models.Device).filter_by(device_id="kiosk01").one()
    assert dev.jadwal_jam_lalu == pytest.approx(2.6)
    assert dev.last_seen_at is not None


def test_device_health_tanpa_auth_401(client):
    assert client.post("/device/kiosk01/health", json={}).status_code == 401


# ---------- R-P1-1 ----------

def test_register_membalikkan_face_encryption_key(client, db_session):
    from app.auth import issue_internal_jwt
    token = issue_internal_jwt(db_session.query(models.Guru).get(1))
    r = client.post("/device/register",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"device_id": "kiosk-baru", "nama_lokasi": "Aula", "platform": "android"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key"]
    assert "face_encryption_key" in body and len(body["face_encryption_key"]) >= 40


# ---------- R-P1-2 ----------

def test_roster_device_auth(client):
    r = client.get("/auth/roster", headers=DEV)
    assert r.status_code == 200, r.text
    emails = {g["email"] for g in r.json()["guru"]}
    assert emails == {"admin@sekolah.sch.id", "piket@sekolah.sch.id"}  # nonaktif tidak muncul


def test_roster_termasuk_nonaktif(client):
    r = client.get("/auth/roster", params={"termasuk_nonaktif": 1}, headers=DEV)
    assert r.status_code == 200
    assert any(g["email"] == "mantan@sekolah.sch.id" and g["aktif"] is False for g in r.json()["guru"])


def test_roster_tanpa_device_auth_401(client):
    assert client.get("/auth/roster").status_code == 401


# ---------- R-P1-4 ----------

def test_enroll_via_device_auth(client, db_session):
    emb = [0.01 * i for i in range(128)]
    r = client.post("/siswa/1/enroll", headers=DEV,
                    json={"embedding": emb, "model_version": "arcface-android-v1"})
    assert r.status_code == 200, r.text
    assert r.json()["sumber"] == "device"
    s = db_session.query(models.Siswa).get(1)
    assert s.enrolled is True
    assert s.enrolled_device_id == "kiosk01"
    assert s.enrolled_oleh is None
    assert db_session.query(models.FaceEmbedding).filter_by(siswa_id=1).count() == 1


def test_enroll_device_siswa_tidak_ada_404(client):
    r = client.post("/siswa/999/enroll", headers=DEV,
                    json={"embedding": [0.1] * 64, "model_version": "v1"})
    assert r.status_code == 404


# ---------- GET /siswa via device-auth (roster lengkap untuk kiosk) ----------

def test_list_siswa_via_device_auth_roster_lengkap(client, db_session):
    # 3 siswa: 1 sudah enroll, 2 belum. Kiosk harus dapat ketiganya.
    db_session.add(models.Siswa(id=2, nis="12346", nama="Ani", kelas_id=1, aktif=True))
    db_session.add(models.Siswa(id=3, nis="12347", nama="Cici", kelas_id=2, aktif=True))
    db_session.query(models.Siswa).filter_by(id=1).update({"enrolled": True})
    db_session.commit()

    r = client.get("/siswa", headers=DEV)
    assert r.status_code == 200, r.text
    data = r.json()
    assert {s["nis"] for s in data} == {"12345", "12346", "12347"}
    assert {s["enrolled"] for s in data if s["nis"] == "12345"} == {True}


def test_list_siswa_tanpa_auth_401(client):
    assert client.get("/siswa").status_code == 401


def test_list_siswa_hanya_siswa_aktif(client, db_session):
    db_session.add(models.Siswa(id=2, nis="99999", nama="Alumni", kelas_id=2, aktif=False))
    db_session.commit()
    r = client.get("/siswa", headers=DEV)
    assert r.status_code == 200
    assert all(s["nis"] != "99999" for s in r.json())


# ---------- Tandai (bukan tolak) absensi dari lokasi mock / fake GPS ----------

def _piket_headers(db_session):
    from app.auth import issue_internal_jwt
    return {"Authorization": f"Bearer {issue_internal_jwt(db_session.query(models.Guru).get(2))}"}


def test_sync_lokasi_mock_tetap_disimpan_tidak_ditolak(client, db_session):
    rid = uuid.uuid4()
    r = client.post("/absensi/sync", json={"records": [_rec(record_id=str(rid), lokasi_mock=True)]}, headers=DEV)
    assert r.status_code == 200, r.text
    assert r.json()["hasil"][0]["status"] == "disimpan"
    row = db_session.query(models.Absensi).filter_by(record_id=rid).one()
    assert row.lokasi_mock is True


def test_sync_tanpa_field_lokasi_mock_default_false(client, db_session):
    rid = uuid.uuid4()
    r = client.post("/absensi/sync", json={"records": [_rec(record_id=str(rid))]}, headers=DEV)
    assert r.status_code == 200, r.text
    row = db_session.query(models.Absensi).filter_by(record_id=rid).one()
    assert row.lokasi_mock is False


def test_record_lokasi_mock_muncul_di_perlu_verifikasi(client, db_session):
    from app.services.waktu import hari_ini
    rid = str(uuid.uuid4())
    hari = hari_ini().isoformat()  # /perlu-verifikasi memfilter berdasarkan tanggal WITA
    client.post("/absensi/sync", json={"records": [
        _rec(record_id=rid, lokasi_mock=True, tanggal=hari,
             jam_aktual=datetime.combine(hari_ini(), time(7, 5)).isoformat())
    ]}, headers=DEV)
    r = client.get("/absensi/perlu-verifikasi", headers=_piket_headers(db_session))
    assert r.status_code == 200, r.text
    hit = [x for x in r.json() if str(x["record_id"]) == rid]
    assert len(hit) == 1 and hit[0]["lokasi_mock"] is True


def test_record_normal_tanpa_mock_tidak_muncul_di_perlu_verifikasi(client, db_session):
    from app.services.waktu import hari_ini
    rid = str(uuid.uuid4())
    hari = hari_ini().isoformat()
    client.post("/absensi/sync", json={"records": [
        _rec(record_id=rid, tanggal=hari,
             jam_aktual=datetime.combine(hari_ini(), time(7, 5)).isoformat())
    ]}, headers=DEV)
    r = client.get("/absensi/perlu-verifikasi", headers=_piket_headers(db_session))
    assert all(str(x["record_id"]) != rid for x in r.json())
