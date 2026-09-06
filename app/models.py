import uuid

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime,
    ForeignKey, Text, UniqueConstraint, CheckConstraint, LargeBinary, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression, func

from app.database import Base


class Guru(Base):
    __tablename__ = "guru"

    id = Column(Integer, primary_key=True)
    nama = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    role = Column(String(20), nullable=False, default="guru_piket")
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())


class Kelas(Base):
    """Rombel — entitas nyata (sebelumnya cuma string bebas di Siswa.kelas dsb).

    Sumber kebenaran daftar kelas. Kiosk TIDAK tahu tabel ini: semua kontrak
    ke kiosk tetap memakai NAMA kelas (di-compute dari relasi), lihat
    Siswa.kelas @property.
    """
    __tablename__ = "kelas"

    id = Column(Integer, primary_key=True)
    nama = Column(String(50), unique=True, nullable=False)          # "XI DKV A"
    tingkat = Column(String(10))                                     # "XI" — opsional
    konsentrasi_id = Column(Integer, ForeignKey("konsentrasi_keahlian.id"))
    wali_id = Column(Integer, ForeignKey("guru.id"))                 # 1 wali per kelas
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())

    konsentrasi = relationship("KonsentrasiKeahlian")
    wali = relationship("Guru")


class Siswa(Base):
    __tablename__ = "siswa"

    id = Column(Integer, primary_key=True)
    nis = Column(String(20), unique=True, nullable=False)
    nama = Column(String(100), nullable=False)
    # Rombel. NULL = "belum ada rombel" (bucket untuk di-drag di halaman Kelas).
    kelas_id = Column(Integer, ForeignKey("kelas.id"), nullable=True)
    # Opsional — kalau diisi, siswa bisa login Google di dashboard web dengan
    # role tetap "siswa" (akses terbatas, lihat get_current_siswa di app/auth.py).
    # NIS/absensi tidak terpengaruh sama sekali — ini murni jalur login tambahan.
    email = Column(String(150), unique=True, nullable=True)
    # Normalisasi: jurusan string lama dipertahankan utk backward-compat,
    # konsentrasi_id adalah FK ke tabel konsentrasi_keahlian (sumber kebenaran baru).
    jurusan = Column(String(150), default="Teknik Elektronika")
    konsentrasi_id = Column(Integer, ForeignKey("konsentrasi_keahlian.id"))
    enrolled = Column(Boolean, default=False)
    tanggal_enrollment = Column(Date)
    enrolled_oleh = Column(Integer, ForeignKey("guru.id"))
    # Diisi bila enrollment dilakukan dari kiosk (device-auth), bukan guru via dashboard.
    # PRD_DUKUNGAN_CLIENT_ANDROID.md R-P1-4. enrolled_oleh = NULL saat sumber = device.
    enrolled_device_id = Column(String(50))
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())

    face_embedding = relationship("FaceEmbedding", back_populates="siswa", uselist=False)
    konsentrasi = relationship("KonsentrasiKeahlian")
    kelas_rel = relationship("Kelas")

    @property
    def kelas(self) -> str:
        """Nama rombel — kontrak lama (kiosk, CSV, laporan) tetap pakai NAMA.

        String kosong bila siswa belum punya rombel.
        """
        return self.kelas_rel.nama if self.kelas_rel else ""


class FaceEmbedding(Base):
    __tablename__ = "face_embedding"

    id = Column(Integer, primary_key=True)
    siswa_id = Column(Integer, ForeignKey("siswa.id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding_encrypted = Column(LargeBinary, nullable=False)
    model_version = Column(String(20), nullable=False)
    dibuat_pada = Column(DateTime, server_default=func.now())
    diperbarui_pada = Column(DateTime, server_default=func.now())

    siswa = relationship("Siswa", back_populates="face_embedding")


class Device(Base):
    __tablename__ = "device"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), unique=True, nullable=False)
    nama_lokasi = Column(String(100))
    platform = Column(String(20))
    api_key_hash = Column(String(200), nullable=False)
    raw_api_key = Column(String(200), nullable=True)
    last_seen_at = Column(DateTime)
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())

    # PRD-observability-degradasi-offline-first §5.1: kesegaran data yang
    # dilaporkan client kiosk via POST /device/{id}/health. jadwal_jam_lalu /
    # dispensasi_jam_lalu = jam sejak terakhir berhasil sync (None = belum
    # pernah sync sama sekali, kondisi lebih parah dari basi).
    jadwal_jam_lalu = Column(Float, nullable=True)
    dispensasi_jam_lalu = Column(Float, nullable=True)
    health_dilaporkan_pada = Column(DateTime, nullable=True)

    # Geofencing per device — diatur admin lewat peta di dashboard (PUT
    # /device/{id}/lokasi). Fail-closed: NULL (belum diatur) berarti device
    # BELUM BOLEH dipakai absen sampai admin mengatur titik acuannya —
    # lihat POST /device/{id}/lokasi/cek.
    lokasi_lat = Column(Float, nullable=True)
    lokasi_lng = Column(Float, nullable=True)
    radius_meter = Column(Integer, nullable=True)
    # Hasil pengecekan TERAKHIR yang dilaporkan kiosk (POST /device/{id}/lokasi/cek)
    # — bukan sumber kebenaran keamanan (kiosk yang memutuskan blokir sendiri
    # dari response), murni untuk ditampilkan di dashboard admin.
    lokasi_valid_terakhir = Column(Boolean, nullable=True)
    lokasi_alasan_terakhir = Column(String(200), nullable=True)
    lokasi_dicek_pada = Column(DateTime, nullable=True)

    # Provisioning via QR (lihat app/services/device_claim.py + POST /device/claim).
    # Token acak sekali-pakai yang di-encode ke QR saat admin menambah device.
    # Kiosk memindainya lalu menukarnya jadi device_id + api_key. Plaintext
    # (setara raw_api_key), berumur pendek (claim_token_expires), dikosongkan
    # begitu ditukar.
    claim_token = Column(String(64), nullable=True, index=True)
    claim_token_expires = Column(DateTime, nullable=True)


class JadwalStandar(Base):
    __tablename__ = "jadwal_standar"
    __table_args__ = (
        UniqueConstraint("hari", "kelas_id", name="uq_jadwal_standar_hari_kelas_id"),
        CheckConstraint("hari IN ('SENIN','SELASA','RABU','KAMIS','JUMAT')"),
    )

    id = Column(Integer, primary_key=True)
    hari = Column(String(10), nullable=False)
    # NULL = berlaku semua kelas (semantik lama dipertahankan).
    kelas_id = Column(Integer, ForeignKey("kelas.id"), nullable=True)
    jam_masuk = Column(Time, nullable=False)
    jam_pulang = Column(Time, nullable=False)


class JadwalOverride(Base):
    __tablename__ = "jadwal_override"

    id = Column(Integer, primary_key=True)
    tanggal = Column(Date, nullable=False)
    # NULL = berlaku semua kelas (semantik lama dipertahankan).
    kelas_id = Column(Integer, ForeignKey("kelas.id"), nullable=True)
    jam_masuk = Column(Time)
    jam_pulang = Column(Time)
    alasan = Column(Text)
    dibuat_oleh = Column(Integer, ForeignKey("guru.id"))
    dibuat_pada = Column(DateTime, server_default=func.now())
    # PRD_JADWAL_OVERRIDE_DEVICE: override bisa dibuat dari device kiosk
    # (offline-first) lalu di-push ke server. client_id = UUID idempotency
    # key dari device (retry sync tidak membuat duplikat), device_id =
    # audit trail sumber (bukan FK, device bisa dihapus), sumber = 'guru' | 'device'.
    client_id = Column(String(36), unique=True, nullable=True, index=True)
    device_id = Column(String(50), nullable=True)
    sumber = Column(String(10), nullable=False, default="guru")


class Absensi(Base):
    __tablename__ = "absensi"
    __table_args__ = (
        UniqueConstraint("siswa_id", "tanggal", "type", name="uq_absensi_siswa_tanggal_type"),
        CheckConstraint("type IN ('MASUK','PULANG')"),
    )

    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    siswa_id = Column(Integer, ForeignKey("siswa.id"), nullable=False)
    tanggal = Column(Date, nullable=False)
    type = Column(String(10), nullable=False)

    jam_aktual = Column(DateTime, nullable=False)
    status_kehadiran_otomatis = Column(String(20), nullable=False, default="NORMAL")
    status_kehadiran_final = Column(String(20))
    catatan = Column(Text)

    device_id = Column(String(50), ForeignKey("device.device_id"))
    approved_by = Column(Integer, ForeignKey("guru.id"))
    approved_at = Column(DateTime)

    # True kalau client menandai lokasi perangkat berasal dari mock-location
    # (fake GPS) saat record ini dibuat. Server TIDAK menolak record —
    # hanya menyimpan tanda ini supaya guru piket bisa meninjau (record
    # tetap muncul di /absensi/perlu-verifikasi). Batas deteksi GPS palsu:
    # lihat docs/API_CONTRACT.md bagian Geofencing.
    lokasi_mock = Column(Boolean, nullable=False, default=False, server_default=expression.false())

    synced_at = Column(DateTime, server_default=func.now())


class Dispensasi(Base):
    """Izin di muka yang diberikan guru piket sebelum siswa absen pulang.
    Misal: siswa izin pulang cepat hari X, maka saat sync PULANG sebelum
    jam_pulang_standar, server menerima record ini."""
    __tablename__ = "dispensasi"
    __table_args__ = (UniqueConstraint("siswa_id", "tanggal", "jenis"),)

    id = Column(Integer, primary_key=True)
    siswa_id = Column(Integer, ForeignKey("siswa.id"), nullable=False)
    tanggal = Column(Date, nullable=False)
    jenis = Column(String(20), nullable=False, default="PULANG_CEPAT")
    kategori = Column(String(20), nullable=False, default="IZIN")
    # IZIN | SAKIT | DISPENSASI_KEGIATAN | LAINNYA
    alasan = Column(Text)
    dibuat_oleh = Column(Integer, ForeignKey("guru.id"), nullable=False)
    dibuat_pada = Column(DateTime, server_default=func.now())


# ============================================================
# Spektrum Keahlian (Kepmendikbudristek No. 244/M/2024)
# Normalisasi 3 level: Bidang -> Program -> Konsentrasi
# ============================================================

class BidangKeahlian(Base):
    """Level 1: Bidang Keahlian (mis. 'Teknologi Informasi')"""
    __tablename__ = "bidang_keahlian"

    id = Column(Integer, primary_key=True)
    nama = Column(String(100), unique=True, nullable=False)
    kode = Column(String(10), unique=True, nullable=False)  # mis. '4'
    dibuat_pada = Column(DateTime, server_default=func.now())

    program_keahlian = relationship("ProgramKeahlian", back_populates="bidang", cascade="all, delete-orphan")


class ProgramKeahlian(Base):
    """Level 2: Program Keahlian (mis. 'Pengembangan Perangkat Lunak dan Gim')"""
    __tablename__ = "program_keahlian"
    __table_args__ = (UniqueConstraint("bidang_id", "nama"),)

    id = Column(Integer, primary_key=True)
    bidang_id = Column(Integer, ForeignKey("bidang_keahlian.id", ondelete="CASCADE"), nullable=False)
    nama = Column(String(150), nullable=False)
    kode = Column(String(10), nullable=False)  # mis. '4.1'
    dibuat_pada = Column(DateTime, server_default=func.now())

    bidang = relationship("BidangKeahlian", back_populates="program_keahlian")
    konsentrasi_keahlian = relationship("KonsentrasiKeahlian", back_populates="program", cascade="all, delete-orphan")


class KonsentrasiKeahlian(Base):
    """Level 3: Konsentrasi Keahlian (mis. 'Rekayasa Perangkat Lunak')"""
    __tablename__ = "konsentrasi_keahlian"
    __table_args__ = (UniqueConstraint("program_id", "nama"),)

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("program_keahlian.id", ondelete="CASCADE"), nullable=False)
    nama = Column(String(150), nullable=False)
    kode = Column(String(10), nullable=False)  # mis. '4.1.1'
    durasi_tahun = Column(Integer, default=3)  # 3 atau 4 tahun
    dibuat_pada = Column(DateTime, server_default=func.now())

    program = relationship("ProgramKeahlian", back_populates="konsentrasi_keahlian")
