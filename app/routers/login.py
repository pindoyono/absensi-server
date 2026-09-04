from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Guru
from app.schemas import GoogleLoginRequest, LoginResponse
from app.auth import verify_google_id_token, issue_internal_jwt, get_current_guru
from app.services.device_auth import verify_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def read_me(current_user: Guru = Depends(get_current_guru)):
    """Profil user yang sedang login (dari JWT internal)."""
    return {
        "id": current_user.id,
        "nama": current_user.nama,
        "email": current_user.email,
        "role": current_user.role,
    }


@router.post("/login/google", response_model=LoginResponse)
def login_google(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Dipanggil dashboard web / client kiosk setelah user berhasil login lewat
    Google Sign-In. Client mengirim id_token dari Google, server verifikasi
    lalu cocokkan dengan data guru yang sudah terdaftar.
    """
    info = verify_google_id_token(body.google_id_token)
    email = info["email"]

    guru = db.query(Guru).filter(Guru.email == email, Guru.aktif == True).first()
    if not guru:
        # Email valid dari domain sekolah, tapi belum didaftarkan admin sebagai guru.
        # Role/akses tidak bisa ditentukan otomatis dari Google — harus di-mapping
        # manual oleh admin sekolah dulu (lihat 9.4 di dokumen arsitektur).
        raise HTTPException(
            status_code=403,
            detail="Akun belum terdaftar sebagai guru di sistem. Hubungi admin sekolah.",
        )

    token = issue_internal_jwt(guru)
    return LoginResponse(access_token=token, email=guru.email, nama=guru.nama, role=guru.role)


class RosterItem(BaseModel):
    email: str
    nama: str
    role: str
    aktif: bool


class RosterResponse(BaseModel):
    server_time: str
    guru: list[RosterItem]


@router.get("/roster", response_model=RosterResponse)
def roster(
    termasuk_nonaktif: int = 0,
    db: Session = Depends(get_db),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """Daftar guru + role untuk device kiosk — dipakai men-*seed* akun login
    offline (`akun_lokal`) supaya SEMUA guru bisa login offline di device mana
    pun, bukan hanya yang pernah login Google di situ. Role = sumber kebenaran
    server. TIDAK mengirim password/hash. Lihat PRD_DUKUNGAN_CLIENT_ANDROID.md R-P1-2.
    """
    if not x_device_id or not x_device_api_key:
        raise HTTPException(status_code=401, detail="Butuh Device API Key")
    device = db.query(Device).filter(Device.device_id == x_device_id, Device.aktif == True).first()
    if not device or not verify_api_key(x_device_api_key, device.api_key_hash):
        raise HTTPException(status_code=401, detail="Device tidak valid")
    device.last_seen_at = datetime.now(timezone.utc)

    q = db.query(Guru)
    if not termasuk_nonaktif:
        q = q.filter(Guru.aktif == True)
    guru = [
        RosterItem(email=g.email, nama=g.nama, role=g.role, aktif=bool(g.aktif))
        for g in q.order_by(Guru.role, Guru.nama).all()
    ]
    db.commit()
    return RosterResponse(server_time=datetime.now(timezone.utc).isoformat(), guru=guru)
