from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Guru, Device

bearer_scheme = HTTPBearer()


def verify_google_id_token(google_token: str) -> dict:
    """
    Verifikasi id_token yang dikirim client (dashboard web) setelah login
    lewat Google Sign-In. Menolak kalau token tidak valid, atau email
    bukan dari domain Google Workspace sekolah.
    """
    try:
        info = google_id_token.verify_oauth2_token(
            google_token, google_requests.Request(), settings.google_client_id
        )
    except Exception as e:
        print(f'DEBUG: Google token verification failed: {e}')
        raise HTTPException(status_code=401, detail="Token Google tidak valid")

    email = info.get("email", "")
    email_verified = info.get("email_verified", False)

    if not email_verified:
        raise HTTPException(status_code=401, detail="Email Google belum terverifikasi")

    email_domain = email.rsplit("@", 1)[-1].lower()
    if email_domain not in settings.allowed_email_domain_list:
        raise HTTPException(
            status_code=403,
            detail="Hanya akun "
            + ", ".join(f"@{d}" for d in settings.allowed_email_domain_list)
            + " yang diizinkan login",
        )

    return info


def issue_internal_jwt(guru: Guru) -> str:
    """Terbitkan JWT internal setelah verifikasi Google berhasil, supaya
    request selanjutnya tidak perlu verifikasi ke Google berulang kali."""
    payload = {
        "sub": str(guru.id),
        "email": guru.email,
        "role": guru.role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_guru(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Guru:
    """Dependency: dekode JWT internal, kembalikan record guru yang login."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Sesi tidak valid atau kedaluwarsa")

    guru = db.query(Guru).filter(Guru.id == int(payload["sub"]), Guru.aktif == True).first()
    if not guru:
        raise HTTPException(status_code=401, detail="Akun guru tidak ditemukan atau nonaktif")

    return guru


def require_role(*allowed_roles: str):
    """Dependency factory untuk membatasi endpoint per role.
    Contoh: Depends(require_role("admin", "guru_piket"))"""

    def _check(guru: Guru = Depends(get_current_guru)) -> Guru:
        if guru.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{guru.role}' tidak punya akses ke aksi ini",
            )
        return guru

    return _check


def get_guru_or_device(
    authorization: str | None = Header(default=None),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    db: Session = Depends(get_db),
) -> Guru | Device:
    """
    Dependency yang menerima DUA jenis autentikasi:
    1. JWT guru (Authorization: Bearer <token>) — untuk dashboard web
    2. Device API Key (X-Device-Api-Key + X-Device-Id) — untuk client kiosk
    
    Digunakan di endpoint read-only yang perlu diakses device:
    - GET /jadwal/efektif
    - GET /dispensasi/aktif
    """
    # Lazy import: app.routers.device juga mengimpor modul ini (require_role,
    # get_current_guru). Impor top-level di sini menimbulkan circular import
    # yang membuat seluruh aplikasi gagal di-load. Impor di dalam fungsi
    # memutus siklus tersebut.
    from app.services.device_auth import verify_api_key

    # Coba device API key dulu (prioritas untuk client kiosk)
    if x_device_api_key and x_device_id:
        device = db.query(Device).filter(Device.device_id == x_device_id, Device.aktif == True).first()
        if device and verify_api_key(x_device_api_key, device.api_key_hash):
            device.last_seen_at = datetime.utcnow()
            return device
    
    # Fallback ke JWT guru (untuk dashboard web)
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            raise HTTPException(status_code=401, detail="Sesi tidak valid atau kedaluwarsa")

        guru = db.query(Guru).filter(Guru.id == int(payload["sub"]), Guru.aktif == True).first()
        if not guru:
            raise HTTPException(status_code=401, detail="Akun guru tidak ditemukan atau nonaktif")
        return guru
    
    raise HTTPException(status_code=401, detail="Autentikasi tidak valid: butuh JWT guru atau Device API Key")
