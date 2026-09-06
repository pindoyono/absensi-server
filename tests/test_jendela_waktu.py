"""Test validasi jendela waktu absen + dispensasi (BAGIAN A server)."""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Siswa, Device, Absensi, Dispensasi, JadwalStandar


# ─── Faktor kuman ──────────────────────────────────────────────

JAM_MASUK = time(7, 0)
JAM_PULANG = time(15, 0)
HARI = "SENIN"


def _setup(db: Session, *, tanggal: date | None = None):
    """Buat data minimal: 1 siswa, 1 device, 1 jadwal standar Senin."""
    tanggal = tanggal or date.today()
    db.add(Siswa(id=1, nis="T001", nama="Siswa Tes"))
    db.add(Device(device_id="dev1", platform="windows", api_key_hash="x"))
    db.add(JadwalStandar(hari=HARI, jam_masuk=JAM_MASUK, jam_pulang=JAM_PULANG))
    db.commit()
    return tanggal


def _sync_absensi(db: Session, *, siswa_id=1, type_, jam_aktual: datetime, tanggal: date | None = None):
    """Replika ringkas dari loop sync_absensi (tanpa device verify)."""
    from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

    tanggal = tanggal or jam_aktual.date()

    # Cari kelas siswa
    siswa = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    kelas_id = siswa.kelas_id if siswa else None
    jadwal = _ambil_jadwal_efektif(db, kelas_id, tanggal)

    if jadwal:
        penolakan = _validasi_jendela_waktu(
            db,
            type(type("obj", (), {"siswa_id": siswa_id, "type": type_, "jam_aktual": jam_aktual, "tanggal": tanggal})()),
            jadwal,
        )
    else:
        penolakan = None

    return penolakan


def _Record(siswa_id, type_, jam_aktual, tanggal):
    """Anonymous record object for testing _validasi_jendela_waktu."""
    return type("Rec", (), {"siswa_id": siswa_id, "type": type_, "jam_aktual": jam_aktual, "tanggal": tanggal})()


# ─── MASUK ────────────────────────────────────────────────────

class TestJendelaMasuk:
    def test_sebelum_jendela_2jam_ditolak(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 04:00, jadwal masuk 07:00 → earliest 05:00 → 04:00 < 05:00 → ditolak
        rec = _Record(1, "MASUK", datetime(2026, 8, 24, 4, 0), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        assert jadwal is not None
        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is not None
        assert "belum dibuka" in pesan.lower()

    def test_persis_di_jendela_2jam_diterima(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 05:00 = earliest (07:00 - 2h) → valid
        rec = _Record(1, "MASUK", datetime(2026, 8, 24, 5, 0), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is None

    def test_setelah_jam_masuk_tetap_diterima(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 08:30 → setelah jam masuk 07:00 → tetap diterima (terlambat, bukan ditolak)
        rec = _Record(1, "MASUK", datetime(2026, 8, 24, 8, 30), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is None


# ─── PULANG tanpa dispensasi ─────────────────────────────────

class TestJendelaPulangTanpaDispensasi:
    def test_pulang_sebelum_jadwal_ditolak(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 12:00 < 15:00 → ditolak, tidak ada dispensasi
        rec = _Record(1, "PULANG", datetime(2026, 8, 24, 12, 0), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is not None
        assert "Belum waktunya pulang" in pesan or "belum waktunya pulang" in pesan

    def test_pulang_persis_jam_jadwal_diterima(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 15:00 = jam pulang → diterima
        rec = _Record(1, "PULANG", datetime(2026, 8, 24, 15, 0), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is None

    def test_pulang_setelah_jam_jadwal_diterima(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # jam 16:00 → setelah jam pulang → tetap diterima
        rec = _Record(1, "PULANG", datetime(2026, 8, 24, 16, 0), tanggal)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal)

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is None


# ─── PULANG dengan dispensasi ─────────────────────────────────

class TestJendelaPulangDenganDispensasi:
    def test_pulang_sebelum_jadwal_dengan_dispensasi_diterima(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # Buat dispensasi untuk siswa 1
        db_session.add(Dispensasi(
            siswa_id=1, tanggal=date(2026, 8, 24),
            jenis="PULANG_CEPAT", kategori="SAKIT", alasan="Demam",
            dibuat_oleh=1,
        ))
        db_session.commit()

        rec = _Record(1, "PULANG", datetime(2026, 8, 24, 12, 0), date(2026, 8, 24))
        jadwal = _ambil_jadwal_efektif(db_session, None, date(2026, 8, 24))

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is None  # ada dispensasi → diterima

    def test_dispensasi_siswa_beda_tidak_mempengaruhi(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif, _validasi_jendela_waktu

        tanggal = _setup(db_session, tanggal=date(2026, 8, 24))
        # Buat SISWA 2, tapi daftarkan dispensasi untuk SISWA 2
        db_session.add(Siswa(id=2, nis="T002", nama="Siswa Lain"))
        db_session.add(Dispensasi(
            siswa_id=2, tanggal=date(2026, 8, 24),
            jenis="PULANG_CEPAT", kategori="IZIN",
            dibuat_oleh=1,
        ))
        db_session.commit()

        # Siswa 1 coba pulang → ditolak (dispensasi punya siswa 2)
        rec = _Record(1, "PULANG", datetime(2026, 8, 24, 12, 0), date(2026, 8, 24))
        jadwal = _ambil_jadwal_efektif(db_session, None, date(2026, 8, 24))

        pesan = _validasi_jendela_waktu(db_session, rec, jadwal)
        assert pesan is not None
        assert "Belum waktunya pulang" in pesan or "belum waktunya pulang" in pesan


# ─── Edge case: weekend ──────────────────────────────────────

class TestWeekend:
    def test_weekend_tidak_ada_jadwal(self, db_session: Session):
        from app.routers.absensi import _ambil_jadwal_efektif

        # 2026-08-22 = Sabtu
        tanggal_sabtu = date(2026, 8, 22)
        jadwal = _ambil_jadwal_efektif(db_session, None, tanggal_sabtu)
        assert jadwal is None


# ─── Dispensasi model test ───────────────────────────────────

class TestDispensasiCRUD:
    def test_uniq_constraint_siswa_tanggal_jenis(self, db_session: Session):
        """Satu siswa hanya boleh punya 1 dispensasi per jenis per hari."""
        _setup(db_session, tanggal=date(2026, 8, 25))

        db_session.add(Dispensasi(
            siswa_id=1, tanggal=date(2026, 8, 25),
            jenis="PULANG_CEPAT", kategori="IZIN",
            dibuat_oleh=1,
        ))
        db_session.commit()

        # Dispensasi kedua untuk siswa & tanggal & jenis sama → harus gagal
        with pytest.raises(Exception):  # IntegrityError
            db_session.add(Dispensasi(
                siswa_id=1, tanggal=date(2026, 8, 25),
                jenis="PULANG_CEPAT", kategori="SAKIT",
                dibuat_oleh=1,
            ))
            db_session.commit()

        db_session.rollback()

    def test_dispensasi_beda_tanggal_boleh(self, db_session: Session):
        """Beda tanggal → dispensasi berbeda → boleh."""
        _setup(db_session, tanggal=date(2026, 8, 25))

        db_session.add(Dispensasi(
            siswa_id=1, tanggal=date(2026, 8, 25),
            jenis="PULANG_CEPAT", kategori="IZIN",
            dibuat_oleh=1,
        ))
        db_session.add(Dispensasi(
            siswa_id=1, tanggal=date(2026, 8, 26),
            jenis="PULANG_CEPAT", kategori="SAKIT",
            dibuat_oleh=1,
        ))
        db_session.commit()
        assert db_session.query(Dispensasi).count() == 2
