from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dispensasi, Guru
from app.auth import require_role, get_current_guru

router = APIRouter(prefix="/dispensasi", tags=["dispensasi"])


class DispensasiIn(BaseModel):
    siswa_id: int
    tanggal: date
    jenis: str = "PULANG_CEPAT"
    kategori: str = "IZIN"
    alasan: Optional[str] = None


class DispensasiOut(BaseModel):
    id: int
    siswa_id: int
    tanggal: date
    jenis: str
    kategori: str
    alasan: Optional[str] = None
    dibuat_oleh: int

    class Config:
        from_attributes = True


@router.post("", response_model=DispensasiOut)
def buat_dispensasi(
    body: DispensasiIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Buat/update dispensasi untuk siswa. Satu siswa cuma boleh punya 1
    dispensasi per jenis per hari (UNIQUE constraint) — kalau sudah ada,
    field-nya diupdate (upsert)."""
    existing = db.query(Dispensasi).filter(
        Dispensasi.siswa_id == body.siswa_id,
        Dispensasi.tanggal == body.tanggal,
        Dispensasi.jenis == body.jenis,
    ).first()

    if existing:
        existing.kategori = body.kategori
        existing.alasan = body.alasan
        existing.dibuat_oleh = guru.id
        db.commit()
        db.refresh(existing)
        return existing

    row = Dispensasi(**body.model_dump(), dibuat_oleh=guru.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/aktif", response_model=list[DispensasiOut])
def list_dispensasi_aktif(
    tanggal: date,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    """Dipanggil client untuk sinkronisasi cache lokal — semua
    dispensasi yang berlaku untuk tanggal tertentu."""
    rows = db.query(Dispensasi).filter(Dispensasi.tanggal == tanggal).all()
    return rows


@router.get("", response_model=list[DispensasiOut])
def list_semua_dispensasi(
    tanggal_dari: Optional[date] = None,
    tanggal_sampai: Optional[date] = None,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    """List semua dispensasi (untuk dashboard admin)."""
    q = db.query(Dispensasi)
    if tanggal_dari:
        q = q.filter(Dispensasi.tanggal >= tanggal_dari)
    if tanggal_sampai:
        q = q.filter(Dispensasi.tanggal <= tanggal_sampai)
    return q.order_by(Dispensasi.tanggal.desc()).all()


@router.delete("/{dispensasi_id}")
def batalkan_dispensasi(
    dispensasi_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Hapus dispensasi — ini membatalkan izin pulang cepat sebelumnya."""
    row = db.query(Dispensasi).filter(Dispensasi.id == dispensasi_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Dispensasi tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "dibatalkan"}
