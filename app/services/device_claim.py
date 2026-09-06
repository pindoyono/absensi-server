"""Provisioning device via QR — token sekali-pakai.

Alur:
  1. Admin menambah device (POST /device/register) atau membuka QR-nya lagi
     (GET /device/{id}/claim-qr) → server membuat `claim_token` acak, berumur
     `TTL_MENIT`, dan mengembalikan `payload_qr()` untuk di-render jadi QR.
  2. Kiosk memindai QR → POST /device/claim {token} → server memverifikasi
     token (ada, belum kedaluwarsa), MENGOSONGKAN token (sekali-pakai), lalu
     mengembalikan device_id + api_key + face_encryption_key + server URL.

Token disimpan plaintext di kolom `device.claim_token` (setara `raw_api_key`
yang memang sudah plaintext di desain ini) tapi berumur pendek & langsung
hangus setelah dipakai.
"""
import json
import secrets
from datetime import timedelta

from app.config import settings
from app.services.waktu import sekarang

TTL_MENIT = 60
PAYLOAD_VERSI = 1


def buat_claim_token(device, *, ttl_menit: int = TTL_MENIT) -> tuple[str, "datetime"]:
    """Set token baru + kedaluwarsa pada `device` (belum commit). Return (token, expires)."""
    token = secrets.token_urlsafe(32)
    expires = sekarang() + timedelta(minutes=ttl_menit)
    device.claim_token = token
    device.claim_token_expires = expires
    return token, expires


def payload_qr(token: str) -> str:
    """String JSON ringkas yang di-encode ke QR. Client mem-parse ini."""
    return json.dumps(
        {"v": PAYLOAD_VERSI, "server": settings.public_base_url.rstrip("/"), "token": token},
        separators=(",", ":"),
    )


def token_masih_berlaku(device) -> bool:
    if not device.claim_token or not device.claim_token_expires:
        return False
    exp = device.claim_token_expires
    now = sekarang()
    # Kolom DateTime bisa naive (disimpan tanpa tz) — samakan dulu.
    if exp.tzinfo is None:
        now = now.replace(tzinfo=None)
    return exp > now
