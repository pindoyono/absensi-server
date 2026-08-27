from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JadwalStandar, JadwalOverride, Guru
from app.auth import require_role, get_current_guru

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
    body: JadwalOverrideIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Guru piket bisa mengubah jam untuk tanggal tertentu (misal upacara,
    ujian, pulang lebih awal) — lihat bagian 8.1 dokumen arsitektur."""
    row = JadwalOverride(**body.model_dump(), dibuat_oleh=guru.id)
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
    guru: Guru = Depends(get_current_guru),
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
