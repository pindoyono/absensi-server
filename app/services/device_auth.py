"""Helper autentikasi device (kiosk) yang dipakai lintas router.

Fungsi `verify_device` sebelumnya ada sebagai `_verify_device` private di
`app/routers/absensi.py`. Karena `POST /device/{id}/health` juga butuh
verifikasi yang sama persis, helper dipindahkan ke sini supaya tidak ada
impor lintas-router ke simbol bertanda underscore (yang seharusnya private).

`hash_api_key` / `verify_api_key` ikut di sini agar `app/routers/device.py`
bisa memakai `verify_device` tanpa circular import (device_auth tidak
mengimpor apa pun dari app.routers.*).
"""
import hashlib
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Device


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return hashlib.sha256(raw_key.encode()).hexdigest() == hashed


def verify_device(db: Session, device_id: str, x_device_api_key: str | None) -> Device:
    """
    Setiap request dari client (Windows/Android) wajib menyertakan header
    `X-Device-Api-Key` berisi api_key mentah yang diberikan saat registrasi
    device (lihat POST /device/register). Server membandingkan hash-nya,
    bukan menyimpan/membandingkan key mentah.

    Mengembalikan row Device yang terdaftar & aktif, atau raise 401.
    Juga memperbarui `last_seen_at` sebagai efek samping (sama seperti
    `get_guru_or_device`).
    """
    device = db.query(Device).filter(Device.device_id == device_id, Device.aktif == True).first()
    if not device:
        raise HTTPException(status_code=401, detail=f"Device '{device_id}' tidak terdaftar/nonaktif")

    if not x_device_api_key or not verify_api_key(x_device_api_key, device.api_key_hash):
        raise HTTPException(status_code=401, detail="API key device tidak valid")

    device.last_seen_at = datetime.utcnow()
    return device
