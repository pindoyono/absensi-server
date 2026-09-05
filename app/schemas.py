import uuid
from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel


class PasswordLoginRequest(BaseModel):
    username: str
    password: str

class GoogleLoginRequest(BaseModel):
    google_id_token: str


class LoginResponse(BaseModel):
    access_token: str
    email: str
    nama: str
    role: str
    # Hanya terisi kalau role == "siswa" -- client Android memakai NIS ini
    # (bukan email) untuk mencocokkan ke siswa_cache lokal (sumber identitas
    # siswa yang sudah dipakai di seluruh alur NIS/enrollment yang ada).
    nis: Optional[str] = None


# Nilai `status_kehadiran_otomatis` yang boleh dikirim client saat sync.
# Client (Windows & Android) mengirim kategori dispensasi apa adanya untuk
# absen pulang cepat berdispensasi (IZIN/SAKIT/DISPENSASI_KEGIATAN/LAINNYA) —
# lihat docs/PRD_DUKUNGAN_CLIENT_ANDROID.md R-P0-1. Tanpa ini seluruh batch
# sync 422 hanya karena satu record berdispensasi.
StatusKehadiran = Literal[
    "NORMAL", "TERLAMBAT", "PULANG_CEPAT",
    "IZIN", "SAKIT", "DISPENSASI_KEGIATAN", "LAINNYA",
]
KATEGORI_DISPENSASI = {"IZIN", "SAKIT", "DISPENSASI_KEGIATAN", "LAINNYA"}


class AbsensiRecordIn(BaseModel):
    """Satu record absensi yang dikirim client saat sync.
    record_id dibuat DI CLIENT (bukan server) agar aman untuk retry."""
    record_id: uuid.UUID
    siswa_id: int
    tanggal: date
    type: Literal["MASUK", "PULANG"]
    jam_aktual: datetime
    status_kehadiran_otomatis: StatusKehadiran = "NORMAL"
    catatan: Optional[str] = None
    device_id: str


class SyncRequest(BaseModel):
    records: list[AbsensiRecordIn]


class SyncResultItem(BaseModel):
    record_id: uuid.UUID
    status: Literal["disimpan", "duplikat_diabaikan", "gagal", "ditolak_kebijakan"]
    pesan: Optional[str] = None


class SyncResponse(BaseModel):
    total: int
    disimpan: int
    duplikat: int
    gagal: int
    hasil: list[SyncResultItem]


class ApprovalRequest(BaseModel):
    status_kehadiran_final: Literal["NORMAL", "TERLAMBAT", "PULANG_CEPAT", "IZIN", "SAKIT"]
    catatan: Optional[str] = None
