from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Guru

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
