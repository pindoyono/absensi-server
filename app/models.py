import uuid

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime,
    ForeignKey, Text, UniqueConstraint, CheckConstraint, LargeBinary
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Guru(Base):
    __tablename__ = "guru"

    id = Column(Integer, primary_key=True)
    nama = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    role = Column(String(20), nullable=False, default="guru_piket")
    kelas_diampu = Column(String(20))
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())


class Siswa(Base):
    __tablename__ = "siswa"

    id = Column(Integer, primary_key=True)
    nis = Column(String(20), unique=True, nullable=False)
    nama = Column(String(100), nullable=False)
    kelas = Column(String(20), nullable=False)
    jurusan = Column(String(50), default="Teknik Elektronika")
    enrolled = Column(Boolean, default=False)
    tanggal_enrollment = Column(Date)
    enrolled_oleh = Column(Integer, ForeignKey("guru.id"))
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())

    face_embedding = relationship("FaceEmbedding", back_populates="siswa", uselist=False)


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
    last_seen_at = Column(DateTime)
    aktif = Column(Boolean, default=True)
    dibuat_pada = Column(DateTime, server_default=func.now())


class JadwalStandar(Base):
    __tablename__ = "jadwal_standar"
    __table_args__ = (
        UniqueConstraint("hari", "kelas"),
        CheckConstraint("hari IN ('SENIN','SELASA','RABU','KAMIS','JUMAT')"),
    )

    id = Column(Integer, primary_key=True)
    hari = Column(String(10), nullable=False)
    kelas = Column(String(20))
    jam_masuk = Column(Time, nullable=False)
    jam_pulang = Column(Time, nullable=False)


class JadwalOverride(Base):
    __tablename__ = "jadwal_override"

    id = Column(Integer, primary_key=True)
    tanggal = Column(Date, nullable=False)
    kelas = Column(String(20))
    jam_masuk = Column(Time)
    jam_pulang = Column(Time)
    alasan = Column(Text)
    dibuat_oleh = Column(Integer, ForeignKey("guru.id"))
    dibuat_pada = Column(DateTime, server_default=func.now())


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
