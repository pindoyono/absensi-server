from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JadwalStandar, JadwalOverride, Guru, Device
from app.auth import require_role, get_current_guru, get_guru_or_device

router = APIRouter(prefix="/jadwal", tags=["jadwal"])


class JadwalStandarIn(BaseModel):
    hari: str  # SENIN..JUMAT
    kelas: Optional[str] = None
    jam_masuk: time
    jam_pulang: time


class JadwalOverrideIn(BaseModel):
    tanggal: date
    kelas: Optional[str] = None
    jam_masuk: Optional[time] = None
    jam_pulang: Optional[time] = None
    alasan: Optional[str] = None


class JadwalOverrideDeviceIn(BaseModel):
    """Body POST /jadwal/override — dipakai bersama oleh JWT guru maupun
    Device API Key (PRD_JADWAL_OVERRIDE_DEVICE). Untuk guru, jam boleh
    kosong (backward-compatible); untuk device wajib terisi (divalidasi
    manual di handler)."""
    tanggal: date
    kelas: Optional[str] = None
    jam_masuk: Optional[time] = None
    jam_pulang: Optional[time] = None
    alasan: Optional[str] = None
    client_id: Optional[str] = None  # UUID idempotency key dari device


HARI_VALID = {"SENIN", "SELASA", "RABU", "KAMIS", "JUMAT"}


@router.get("/standar")
def list_jadwal_standar(db: Session = Depends(get_db), guru: Guru = Depends(get_current_guru)):
    return db.query(JadwalStandar).order_by(JadwalStandar.hari).all()


@router.post("/standar")
def upsert_jadwal_standar(
    body: JadwalStandarIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if body.hari not in HARI_VALID:
        raise HTTPException(status_code=400, detail=f"hari harus salah satu dari {HARI_VALID}")

    existing = (
        db.query(JadwalStandar)
        .filter(JadwalStandar.hari == body.hari, JadwalStandar.kelas == body.kelas)
        .first()
    )
    if existing:
        existing.jam_masuk = body.jam_masuk
        existing.jam_pulang = body.jam_pulang
    else:
        db.add(JadwalStandar(**body.model_dump()))
    db.commit()
    return {"status": "ok"}


@router.get("/override")
def list_jadwal_override(
    dari_tanggal: Optional[date] = None,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    q = db.query(JadwalOverride)
    if dari_tanggal:
        q = q.filter(JadwalOverride.tanggal >= dari_tanggal)
    return q.order_by(JadwalOverride.tanggal.desc()).all()


@router.post("/override")
def create_jadwal_override(
    body: JadwalOverrideDeviceIn,
    db: Session = Depends(get_db),
    auth: Guru | Device = Depends(get_guru_or_device),
):
    """Buat override jadwal untuk tanggal tertentu (misal upacara, ujian,
    pulang lebih awal) — lihat bagian 8.1 dokumen arsitektur.

    Menerima DUA jenis autentikasi (PRD_JADWAL_OVERRIDE_DEVICE):
    - JWT guru (admin / guru_piket) → sumber='guru', dibuat_oleh=guru.id
    - Device API Key (kiosk offline-first) → sumber='device', dibuat_oleh=NULL,
      device_id tercatat untuk audit. Device hanya boleh POST (create),
      PUT/DELETE tetap khusus JWT guru.

    Idempoten untuk device: `client_id` (UUID dari client) dipakai sebagai
    idempotency key — request ulang dengan client_id sama mengembalikan
    record yang sudah ada tanpa membuat baris baru (retry tiap siklus sync
    aman).
    """
    is_device = isinstance(auth, Device)

    # FR-5: idempotensi via client_id
    if body.client_id:
        existing = (
            db.query(JadwalOverride)
            .filter(JadwalOverride.client_id == body.client_id)
            .first()
        )
        if existing:
            return existing

    if is_device:
        # FR-3: device wajib kirim jam lengkap (override lokal sudah valid
        # di client, server menolak data separuh agar tidak merusak jadwal)
        if body.jam_masuk is None or body.jam_pulang is None:
            raise HTTPException(
                status_code=400,
                detail="jam_masuk dan jam_pulang wajib diisi untuk override dari device",
            )
        # FR-9
        if body.jam_masuk >= body.jam_pulang:
            raise HTTPException(status_code=400, detail="jam_masuk harus < jam_pulang")
    else:
        # Role gate yang sebelumnya dipegang require_role("admin","guru_piket")
        if auth.role not in ("admin", "guru_piket"):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{auth.role}' tidak punya akses ke aksi ini",
            )
        # FR-7: perilaku guru dipertahankan — jam boleh sebagian (dashboard
        # lama mengirim null), urutan tetap divalidasi kalau keduanya ada
        if body.jam_masuk and body.jam_pulang and body.jam_masuk >= body.jam_pulang:
            raise HTTPException(status_code=400, detail="jam_masuk harus < jam_pulang")

    row = JadwalOverride(
        tanggal=body.tanggal,
        kelas=body.kelas,
        jam_masuk=body.jam_masuk,
        jam_pulang=body.jam_pulang,
        alasan=body.alasan,
        client_id=body.client_id,
        device_id=auth.device_id if is_device else None,
        sumber="device" if is_device else "guru",
        dibuat_oleh=None if is_device else auth.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.put("/override/{override_id}")
def update_jadwal_override(
    override_id: int,
    body: JadwalOverrideIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    row = db.query(JadwalOverride).filter(JadwalOverride.id == override_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jadwal override tidak ditemukan")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    row.dibuat_oleh = guru.id
    db.commit()
    db.refresh(row)
    return row

@router.delete("/override/{override_id}")
def delete_jadwal_override(
    override_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    row = db.query(JadwalOverride).filter(JadwalOverride.id == override_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jadwal override tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@router.get("/efektif")
def jadwal_efektif_hari_ini(
    kelas: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: Guru | Device = Depends(get_guru_or_device),
):
    """Jadwal yang berlaku HARI INI untuk kelas tertentu — cek override
    dulu, baru fallback ke jadwal standar. Ini logika yang sama yang
    harus diimplementasikan di client (jadwal di-cache ke client saat
    sync, supaya tetap valid dipakai walau offline)."""
    today = date.today()
    hari_nama = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", None, None][today.weekday()]

    override = (
        db.query(JadwalOverride)
        .filter(JadwalOverride.tanggal == today)
        .filter((JadwalOverride.kelas == kelas) | (JadwalOverride.kelas.is_(None)))
        .order_by(JadwalOverride.kelas.desc().nullslast())  # kelas spesifik menang atas NULL
        .first()
    )
    if override and override.jam_masuk and override.jam_pulang:
        return {
            "sumber": "override",
            "jam_masuk": override.jam_masuk,
            "jam_pulang": override.jam_pulang,
            "alasan": override.alasan,
        }

    if not hari_nama:
        return {"sumber": "tidak_ada_sekolah", "jam_masuk": None, "jam_pulang": None}

    standar = (
        db.query(JadwalStandar)
        .filter(JadwalStandar.hari == hari_nama)
        .filter((JadwalStandar.kelas == kelas) | (JadwalStandar.kelas.is_(None)))
        .order_by(JadwalStandar.kelas.desc().nullslast())
        .first()
    )
    if not standar:
        raise HTTPException(status_code=404, detail="Jadwal standar untuk hari/kelas ini belum diatur")

    return {"sumber": "standar", "jam_masuk": standar.jam_masuk, "jam_pulang": standar.jam_pulang}
