from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Guru
from app.auth import require_role

router = APIRouter(prefix="/guru", tags=["guru"])


class GuruIn(BaseModel):
    nama: str
    email: EmailStr
    role: Literal["admin", "guru_piket", "wali_kelas", "kepala_sekolah"] = "guru_piket"
    kelas_diampu: Optional[str] = None
    aktif: bool = True


class GuruUpdate(BaseModel):
    nama: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "guru_piket", "wali_kelas", "kepala_sekolah"]] = None
    kelas_diampu: Optional[str] = None
    aktif: Optional[bool] = None


class GuruOut(BaseModel):
    id: int
    nama: str
    email: str
    role: str
    kelas_diampu: Optional[str] = None
    aktif: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[GuruOut])
def list_guru(
    role: Optional[str] = None,
    aktif: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Guru = Depends(require_role("admin")),
):
    q = db.query(Guru)
    if role:
        q = q.filter(Guru.role == role)
    if aktif is not None:
        q = q.filter(Guru.aktif == aktif)
    return q.order_by(Guru.nama).all()


@router.post("", response_model=GuruOut)
def create_guru(
    body: GuruIn,
    db: Session = Depends(get_db),
    current_user: Guru = Depends(require_role("admin")),
):
    if db.query(Guru).filter(Guru.email == body.email).first():
        raise HTTPException(status_code=409, detail=f"Email {body.email} sudah terdaftar")
    
    row = Guru(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{guru_id}", response_model=GuruOut)
def get_guru(
    guru_id: int,
    db: Session = Depends(get_db),
    current_user: Guru = Depends(require_role("admin")),
):
    row = db.query(Guru).filter(Guru.id == guru_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return row


@router.put("/{guru_id}", response_model=GuruOut)
def update_guru(
    guru_id: int,
    body: GuruUpdate,
    db: Session = Depends(get_db),
    current_user: Guru = Depends(require_role("admin")),
):
    row = db.query(Guru).filter(Guru.id == guru_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")

    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"] != row.email:
        if db.query(Guru).filter(Guru.email == data["email"]).first():
            raise HTTPException(status_code=409, detail=f"Email {data['email']} sudah digunakan")

    for k, v in data.items():
        setattr(row, k, v)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{guru_id}")
def delete_guru(
    guru_id: int,
    db: Session = Depends(get_db),
    current_user: Guru = Depends(require_role("admin")),
):
    row = db.query(Guru).filter(Guru.id == guru_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    
    # Soft delete / nonaktifkan
    row.aktif = False
    db.commit()
    return {"status": "ok", "message": f"Guru {row.nama} berhasil dinonaktifkan"}
