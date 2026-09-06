from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Kelas, Siswa, Guru, Device, JadwalStandar, JadwalOverride
from app.auth import require_role, get_guru_or_device

router = APIRouter(prefix="/kelas", tags=["kelas"])


class KelasIn(BaseModel):
    nama: str
    tingkat: Optional[str] = None
    konsentrasi_id: Optional[int] = None
    wali_id: Optional[int] = None


class KelasUpdate(BaseModel):
    nama: Optional[str] = None
    tingkat: Optional[str] = None
    konsentrasi_id: Optional[int] = None
    wali_id: Optional[int] = None
    aktif: Optional[bool] = None


def _serialize(k: Kelas, jumlah_siswa: int, wali_nama: Optional[str]) -> dict:
    return {
        "id": k.id,
        "nama": k.nama,
        "tingkat": k.tingkat,
        "konsentrasi_id": k.konsentrasi_id,
        "wali_id": k.wali_id,
        "wali_nama": wali_nama,
        "aktif": k.aktif,
        "jumlah_siswa": jumlah_siswa,
    }


@router.get("")
def list_kelas(
    db: Session = Depends(get_db),
    auth: Guru | Device = Depends(get_guru_or_device),
):
    """Daftar kelas — dapat diakses guru (dashboard) maupun device (kiosk)."""
    hitung = dict(
        db.query(Siswa.kelas_id, func.count(Siswa.id))
        .filter(Siswa.aktif == True)
        .group_by(Siswa.kelas_id)
        .all()
    )
    wali = {g.id: g.nama for g in db.query(Guru).all()}
    rows = db.query(Kelas).order_by(Kelas.nama).all()
    return [_serialize(k, hitung.get(k.id, 0), wali.get(k.wali_id)) for k in rows]


@router.post("")
def create_kelas(
    body: KelasIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if db.query(Kelas).filter(Kelas.nama == body.nama).first():
        raise HTTPException(status_code=409, detail=f"Kelas '{body.nama}' sudah ada")
    if body.wali_id and not db.query(Guru).filter(Guru.id == body.wali_id).first():
        raise HTTPException(status_code=422, detail=f"wali_id {body.wali_id} tidak ada")
    row = Kelas(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row, 0, None)


@router.put("/{kelas_id}")
def update_kelas(
    kelas_id: int,
    body: KelasUpdate,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(Kelas).filter(Kelas.id == kelas_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    data = body.model_dump(exclude_unset=True)
    if "nama" in data and data["nama"] != row.nama:
        if db.query(Kelas).filter(Kelas.nama == data["nama"]).first():
            raise HTTPException(status_code=409, detail=f"Kelas '{data['nama']}' sudah ada")
    if data.get("wali_id") and not db.query(Guru).filter(Guru.id == data["wali_id"]).first():
        raise HTTPException(status_code=422, detail=f"wali_id {data['wali_id']} tidak ada")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    jumlah = db.query(Siswa).filter(Siswa.kelas_id == row.id, Siswa.aktif == True).count()
    wali_nama = None
    if row.wali_id:
        g = db.query(Guru).filter(Guru.id == row.wali_id).first()
        wali_nama = g.nama if g else None
    return _serialize(row, jumlah, wali_nama)


@router.delete("/{kelas_id}")
def delete_kelas(
    kelas_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """Hapus kelas — ditolak 409 kalau masih ada siswa / jadwal yang mereferensikan."""
    row = db.query(Kelas).filter(Kelas.id == kelas_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    n_siswa = db.query(Siswa).filter(Siswa.kelas_id == kelas_id).count()
    n_standar = db.query(JadwalStandar).filter(JadwalStandar.kelas_id == kelas_id).count()
    n_override = db.query(JadwalOverride).filter(JadwalOverride.kelas_id == kelas_id).count()
    if n_siswa or n_standar or n_override:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Kelas masih dipakai: {n_siswa} siswa, {n_standar} jadwal standar, "
                f"{n_override} jadwal override. Pindahkan dulu sebelum menghapus."
            ),
        )
    db.delete(row)
    db.commit()
    print(
        f"AUDIT kelas.hapus kelas_id={kelas_id} nama={row.nama} oleh guru_id={guru.id} ({guru.email})"
    )
    return {"status": "ok", "kelas_id": kelas_id}


@router.get("/{kelas_id}/siswa")
def siswa_kelas(
    kelas_id: int,
    db: Session = Depends(get_db),
    auth: Guru | Device = Depends(get_guru_or_device),
):
    row = db.query(Kelas).filter(Kelas.id == kelas_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    siswa = (
        db.query(Siswa)
        .filter(Siswa.kelas_id == kelas_id, Siswa.aktif == True)
        .order_by(Siswa.nama)
        .all()
    )
    return [
        {"id": s.id, "nis": s.nis, "nama": s.nama, "enrolled": s.enrolled}
        for s in siswa
    ]
