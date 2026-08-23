import uuid
from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel


class GoogleLoginRequest(BaseModel):
    google_id_token: str


class LoginResponse(BaseModel):
    access_token: str
    nama: str
    role: str


class AbsensiRecordIn(BaseModel):
    """Satu record absensi yang dikirim client saat sync.
    record_id dibuat DI CLIENT (bukan server) agar aman untuk retry."""
    record_id: uuid.UUID
    siswa_id: int
    tanggal: date
    type: Literal["MASUK", "PULANG"]
    jam_aktual: datetime
    status_kehadiran_otomatis: Literal["NORMAL", "TERLAMBAT", "PULANG_CEPAT"] = "NORMAL"
    catatan: Optional[str] = None
    device_id: str


class SyncRequest(BaseModel):
    records: list[AbsensiRecordIn]


class SyncResultItem(BaseModel):
    record_id: uuid.UUID
    status: Literal["disimpan", "duplikat_diabaikan", "gagal"]
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
