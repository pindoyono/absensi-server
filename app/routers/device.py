import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Guru
from app.auth import require_role, get_current_guru
from app.services.device_auth import verify_device, hash_api_key, verify_api_key

router = APIRouter(prefix="/device", tags=["device"])


class DeviceIn(BaseModel):
    device_id: str | None = None  # opsional — kosongkan untuk generate otomatis
    nama_lokasi: str
    platform: str  # 'windows' | 'android'


class DeviceOut(BaseModel):
    device_id: str
    nama_lokasi: str
    platform: str
    aktif: bool
    last_seen_at: datetime | None = None
    dibuat_pada: datetime | None = None
    raw_api_key: str | None = None
    # PRD-observability-degradasi-offline-first §5.1: kesegaran data
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None
    health_dilaporkan_pada: datetime | None = None

    class Config:
        from_attributes = True

class DeviceHealthIn(BaseModel):
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None



@router.get("", response_model=list[DeviceOut])
def list_device(db: Session = Depends(get_db), guru: Guru = Depends(require_role("admin", "guru_piket"))):
    return db.query(Device).all()


def _generate_device_id(db: Session) -> str:
    """Generate device_id unik (Opsi B): dev-XXXXXXXX (8 karakter aman URL)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    for _ in range(10):  # hindari tabrakan unik yang sangat kecil kemungkinannya
        candidate = "dev-" + "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.query(Device).filter(Device.device_id == candidate).first():
            return candidate
    raise HTTPException(status_code=500, detail="Gagal generate device_id unik")


@router.post("/register")
def register_device(
    body: DeviceIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Daftarkan device baru. API key mentah HANYA ditampilkan sekali di
    response ini — server hanya menyimpan hash-nya (SHA-256). Admin harus
    menyalin device_id + api_key ini ke konfigurasi device (Windows/Android)
    saat setup. Kalau key hilang, harus regenerate (bukan bisa dilihat ulang).

    Opsi B: device_id otomatis di-generate (dev-XXXXXXXX) kalau tidak diisi.
    Admin tetap boleh override lewat field device_id (tetap divalidasi unik).
    """
    device_id = body.device_id
    if device_id:
        device_id = device_id.strip()
        if db.query(Device).filter(Device.device_id == device_id).first():
            raise HTTPException(status_code=409, detail="device_id sudah terdaftar")
    else:
        device_id = _generate_device_id(db)

    raw_key = secrets.token_urlsafe(32)
    row = Device(
        device_id=device_id,
        nama_lokasi=body.nama_lokasi,
        platform=body.platform,
        api_key_hash=hash_api_key(raw_key),
        raw_api_key=raw_key,
    )
    db.add(row)
    db.commit()

    return {
        "device_id": device_id,
        "api_key": raw_key,  # tampil SEKALI SAJA, simpan baik-baik
        "peringatan": "Simpan device_id & api_key ini sekarang — tidak akan ditampilkan lagi.",
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
    device.raw_api_key = raw_key
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


# Ambang batas basi — HARUS sama dengan BATAS_STALE_JADWAL_JAM /
# BATAS_STALE_DISPENSASI_JAM di config client kiosk, supaya dashboard dan
# kiosk "sepakat" soal kapan data dianggap basi (PRD-tuntaskan-device-health §3).
BATAS_STALE_JADWAL_JAM = 6
BATAS_STALE_DISPENSASI_JAM = 2


@router.post("/{device_id}/health")
def report_device_health(
    device_id: str,
    body: DeviceHealthIn,
    db: Session = Depends(get_db),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    PRD-observability-degradasi-offline-first §5.1.
    Client kiosk melaporkan kesegaran data jadwal & dispensasi.

    Butuh X-Device-Api-Key (sama seperti /absensi/sync, /embeddings/sync,
    /jadwal/efektif) -- TANPA ini, device_id bisa ditebak/dipalsukan untuk
    mengirim laporan kesehatan palsu.
    """
    verify_device(db, device_id, x_device_api_key)

    device = db.query(Device).filter(Device.device_id == device_id).first()
    device.jadwal_jam_lalu = body.jadwal_jam_lalu
    device.dispensasi_jam_lalu = body.dispensasi_jam_lalu
    device.health_dilaporkan_pada = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.get("/status-kesehatan")
def status_kesehatan_semua_device(
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """
    PRD-tuntaskan-device-health §3. Dipakai dashboard — ringkasan kesehatan
    semua device aktif. Ambang batas sama dengan config client kiosk.
    """
    devices = db.query(Device).filter(Device.aktif == True).all()
    return [
        {
            "device_id": d.device_id,
            "nama_lokasi": d.nama_lokasi,
            "online_terakhir": d.last_seen_at,
            "health_dilaporkan_pada": d.health_dilaporkan_pada,
            "jadwal_jam_lalu": d.jadwal_jam_lalu,
            "dispensasi_jam_lalu": d.dispensasi_jam_lalu,
            "jadwal_bermasalah": (d.jadwal_jam_lalu or 999) > BATAS_STALE_JADWAL_JAM,
            "dispensasi_bermasalah": (d.dispensasi_jam_lalu or 999) > BATAS_STALE_DISPENSASI_JAM,
            "belum_pernah_lapor": d.health_dilaporkan_pada is None,
        }
        for d in devices
    ]
