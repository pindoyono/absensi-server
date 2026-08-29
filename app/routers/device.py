import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Guru
from app.auth import require_role, get_current_guru

router = APIRouter(prefix="/device", tags=["device"])


class DeviceIn(BaseModel):
    device_id: str
    nama_lokasi: str
    platform: str  # 'windows' | 'android'


class DeviceOut(BaseModel):
    device_id: str
    nama_lokasi: str
    platform: str
    aktif: bool
    last_seen_at: datetime | None = None
    dibuat_pada: datetime | None = None
    # PRD-observability-degradasi-offline-first §5.1: kesegaran data
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None
    health_dilaporkan_pada: datetime | None = None

    class Config:
        from_attributes = True

class DeviceHealthIn(BaseModel):
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return hashlib.sha256(raw_key.encode()).hexdigest() == hashed


@router.get("", response_model=list[DeviceOut])
def list_device(db: Session = Depends(get_db), guru: Guru = Depends(require_role("admin", "guru_piket"))):
    return db.query(Device).all()


@router.post("/register")
def register_device(
    body: DeviceIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Daftarkan device baru. API key mentah HANYA ditampilkan sekali di
    response ini — server hanya menyimpan hash-nya (SHA-256). Admin harus
    menyalin key ini ke konfigurasi device (Windows/Android) saat setup.
    Kalau key hilang, harus regenerate (bukan bisa dilihat ulang).
    """
    if db.query(Device).filter(Device.device_id == body.device_id).first():
        raise HTTPException(status_code=409, detail="device_id sudah terdaftar")

    raw_key = secrets.token_urlsafe(32)
    row = Device(
        device_id=body.device_id,
        nama_lokasi=body.nama_lokasi,
        platform=body.platform,
        api_key_hash=hash_api_key(raw_key),
    )
    db.add(row)
    db.commit()

    return {
        "device_id": body.device_id,
        "api_key": raw_key,  # tampil SEKALI SAJA, simpan baik-baik
        "peringatan": "Simpan api_key ini sekarang — tidak akan ditampilkan lagi.",
    }


@router.post("/{device_id}/regenerate-key")
def regenerate_key(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")

    raw_key = secrets.token_urlsafe(32)
    device.api_key_hash = hash_api_key(raw_key)
    db.commit()
    return {"device_id": device_id, "api_key": raw_key}


@router.delete("/{device_id}")
def deactivate_device(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    device.aktif = False
    db.commit()
    return {"status": "dinonaktifkan"}


@router.post("/{device_id}/health")
def report_device_health(
    device_id: str,
    body: DeviceHealthIn,
    db: Session = Depends(get_db),
):
    """
    PRD-observability-degradasi-offline-first §5.1.
    Client kiosk melaporkan kesegaran data jadwal & dispensasi.
    Tidak perlu auth — request datang dari device sendiri (tidak ada
    guru yang login). Cukup verifikasi device_id terdaftar & aktif.
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if not device.aktif:
        raise HTTPException(status_code=403, detail="Device tidak aktif")

    device.jadwal_jam_lalu = body.jadwal_jam_lalu
    device.dispensasi_jam_lalu = body.dispensasi_jam_lalu
    device.health_dilaporkan_pada = datetime.utcnow()
    db.commit()
    return {"status": "ok"}
