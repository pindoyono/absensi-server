from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Guru
from app.schemas import GoogleLoginRequest, LoginResponse
from app.auth import verify_google_id_token, issue_internal_jwt

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login/google", response_model=LoginResponse)
def login_google(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Dipanggil dashboard web setelah guru berhasil login lewat Google Sign-In
    di sisi browser. Client mengirim id_token dari Google, server verifikasi
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
    return LoginResponse(access_token=token, nama=guru.nama, role=guru.role)
