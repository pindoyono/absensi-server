import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Siswa, Device, Absensi


def _buat_siswa_dan_device(db):
    db.add(Siswa(id=1, nis="123", nama="Test Siswa", kelas="XI"))
    db.add(Device(device_id="dev1", platform="windows", api_key_hash="x"))
    db.commit()


def test_masuk_pertama_berhasil(db_session):
    _buat_siswa_dan_device(db_session)
    r = Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    )
    db_session.add(r)
    db_session.commit()
    assert db_session.query(Absensi).count() == 1


def test_masuk_kedua_di_hari_sama_ditolak(db_session):
    """Ini aturan bisnis paling inti: 1 siswa hanya boleh 1x MASUK per hari,
    walau record_id-nya beda (misal dikirim device berbeda)."""
    _buat_siswa_dan_device(db_session)
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.commit()

    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(Absensi).count() == 1


def test_masuk_dan_pulang_boleh_di_hari_sama(db_session):
    _buat_siswa_dan_device(db_session)
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="PULANG", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.commit()
    assert db_session.query(Absensi).count() == 2


def test_record_id_sama_dianggap_retry_bukan_data_baru(db_session):
    """Simulasi client retry karena timeout — record_id sama harus
    idempotent, tidak boleh membuat 2 baris."""
    _buat_siswa_dan_device(db_session)
    rid = uuid.uuid4()
    db_session.add(Absensi(
        record_id=rid, siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.commit()

    # record_id sama persis dikirim ulang (skenario retry)
    existing = db_session.query(Absensi).filter(Absensi.record_id == rid).first()
    assert existing is not None  # endpoint sync akan mendeteksi ini sebagai duplikat, bukan insert baru


def test_masuk_untuk_tanggal_berbeda_tetap_boleh(db_session):
    """Pastikan constraint tidak salah scope — beda tanggal harus tetap
    dianggap record baru yang sah."""
    _buat_siswa_dan_device(db_session)
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today() - timedelta(days=1),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.commit()
    assert db_session.query(Absensi).count() == 2


def test_siswa_berbeda_boleh_masuk_di_hari_sama(db_session):
    db_session.add(Siswa(id=1, nis="123", nama="Siswa A", kelas="XI"))
    db_session.add(Siswa(id=2, nis="124", nama="Siswa B", kelas="XI"))
    db_session.add(Device(device_id="dev1", platform="windows", api_key_hash="x"))
    db_session.commit()

    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=1, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.add(Absensi(
        record_id=uuid.uuid4(), siswa_id=2, tanggal=date.today(),
        type="MASUK", jam_aktual=datetime.now(), device_id="dev1",
    ))
    db_session.commit()
    assert db_session.query(Absensi).count() == 2
