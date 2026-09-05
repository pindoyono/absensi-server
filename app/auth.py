from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Guru, Device, Siswa

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
        # "tipe" (bukan "role") yang membedakan token guru vs siswa di
        # get_current_guru/get_current_siswa -- guru.id dan siswa.id sama-sama
        # auto-increment dari 1, jadi TANPA field ini token siswa dengan
        # sub="3" bisa salah tertukar dibaca sebagai guru id=3 kalau baris itu
        # kebetulan ada (lihat get_current_siswa di bawah).
        "tipe": "guru",
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def issue_siswa_jwt(siswa: Siswa) -> str:
    """Terbitkan JWT internal untuk siswa yang login Google (role tetap
    'siswa', akses dibatasi lewat get_current_siswa — lihat komentar
    `tipe` di issue_internal_jwt soal kenapa field ini wajib ada)."""
    payload = {
        "sub": str(siswa.id),
        "email": siswa.email,
        "role": "siswa",
        "tipe": "siswa",
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Sesi tidak valid atau kedaluwarsa")


def get_current_guru(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Guru:
    """Dependency: dekode JWT internal, kembalikan record guru yang login.
    Menolak token siswa (tipe != "guru") walau `sub`-nya kebetulan valid
    sebagai id baris guru lain -- lihat catatan di issue_internal_jwt."""
    payload = decode_token(credentials.credentials)
    if payload.get("tipe") != "guru":
        raise HTTPException(status_code=401, detail="Token ini bukan sesi guru/admin")

    guru = db.query(Guru).filter(Guru.id == int(payload["sub"]), Guru.aktif == True).first()
    if not guru:
        raise HTTPException(status_code=401, detail="Akun guru tidak ditemukan atau nonaktif")

    return guru


def get_current_siswa(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Siswa:
    """Dependency setara get_current_guru, tapi untuk siswa yang login
    Google (role tetap 'siswa', akses ke endpoint self-service saja)."""
    payload = decode_token(credentials.credentials)
    if payload.get("tipe") != "siswa":
        raise HTTPException(status_code=401, detail="Token ini bukan sesi siswa")

    siswa = db.query(Siswa).filter(Siswa.id == int(payload["sub"]), Siswa.aktif == True).first()
    if not siswa:
        raise HTTPException(status_code=401, detail="Akun siswa tidak ditemukan atau nonaktif")

    return siswa


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
    
    # Fallback ke JWT guru (untuk dashboard web) -- token siswa ditolak
    # sengaja (get_guru_or_device dipakai endpoint device-facing, bukan area
    # siswa), lihat catatan "tipe" di issue_internal_jwt.
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization[7:])
        if payload.get("tipe") != "guru":
            raise HTTPException(status_code=401, detail="Token ini bukan sesi guru/admin")

        guru = db.query(Guru).filter(Guru.id == int(payload["sub"]), Guru.aktif == True).first()
        if not guru:
            raise HTTPException(status_code=401, detail="Akun guru tidak ditemukan atau nonaktif")
        return guru
    
    raise HTTPException(status_code=401, detail="Autentikasi tidak valid: butuh JWT guru atau Device API Key")
