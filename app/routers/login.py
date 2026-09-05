from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Guru, Siswa
from app.schemas import GoogleLoginRequest, LoginResponse
from app.auth import verify_google_id_token, issue_internal_jwt, issue_siswa_jwt, get_current_guru, decode_token
from app.services.device_auth import verify_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def read_me(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db),
):
    """
    Profil user yang sedang login (dari JWT internal) — guru/admin ATAU
    siswa, dibedakan lewat klaim "tipe" di token (lihat app/auth.py).
    UserMenu di dashboard web memanggil ini lepas dari jenis akunnya.
    """
    payload = decode_token(credentials.credentials)
    if payload.get("tipe") == "siswa":
        siswa = db.query(Siswa).filter(Siswa.id == int(payload["sub"]), Siswa.aktif == True).first()
        if not siswa:
            raise HTTPException(status_code=401, detail="Akun siswa tidak ditemukan atau nonaktif")
        return {"id": siswa.id, "nama": siswa.nama, "email": siswa.email, "role": "siswa"}

    guru = db.query(Guru).filter(Guru.id == int(payload["sub"]), Guru.aktif == True).first()
    if not guru:
        raise HTTPException(status_code=401, detail="Akun guru tidak ditemukan atau nonaktif")
    return {"id": guru.id, "nama": guru.nama, "email": guru.email, "role": guru.role}


@router.post("/login/google", response_model=LoginResponse)
def login_google(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Dipanggil dashboard web / client kiosk setelah user berhasil login lewat
    Google Sign-In. Client mengirim id_token dari Google, server verifikasi
    lalu cocokkan dengan data guru YANG SUDAH TERDAFTAR, atau siswa yang
    emailnya sudah diisi admin di Data Siswa (role tetap "siswa", akses
    dashboard sangat terbatas — lihat get_current_siswa di app/auth.py).
    """
    info = verify_google_id_token(body.google_id_token)
    email = info["email"]

    guru = db.query(Guru).filter(Guru.email == email, Guru.aktif == True).first()
    if guru:
        token = issue_internal_jwt(guru)
        return LoginResponse(access_token=token, email=guru.email, nama=guru.nama, role=guru.role)

    siswa = db.query(Siswa).filter(Siswa.email == email, Siswa.aktif == True).first()
    if siswa:
        token = issue_siswa_jwt(siswa)
        return LoginResponse(access_token=token, email=siswa.email, nama=siswa.nama, role="siswa", nis=siswa.nis)

    # Email valid dari Google, tapi belum di-mapping admin ke akun guru
    # ataupun siswa manapun — role/akses tidak bisa ditentukan otomatis.
    raise HTTPException(
        status_code=403,
        detail="Akun belum terdaftar sebagai guru/siswa di sistem. Hubungi admin sekolah.",
    )


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
