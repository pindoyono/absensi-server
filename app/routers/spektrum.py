from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import BidangKeahlian, ProgramKeahlian, KonsentrasiKeahlian, Guru
from app.auth import require_role, get_current_guru

router = APIRouter(prefix="/spektrum", tags=["spektrum"])


# ---------- Schemas ----------

class BidangIn(BaseModel):
    nama: str
    kode: str

class BidangOut(BaseModel):
    id: int
    nama: str
    kode: str
    class Config:
        from_attributes = True

class ProgramIn(BaseModel):
    bidang_id: int
    nama: str
    kode: str

class ProgramOut(BaseModel):
    id: int
    bidang_id: int
    nama: str
    kode: str
    class Config:
        from_attributes = True

class KonsentrasiIn(BaseModel):
    program_id: int
    nama: str
    kode: str
    durasi_tahun: int = 3

class KonsentrasiOut(BaseModel):
    id: int
    program_id: int
    nama: str
    kode: str
    durasi_tahun: int
    class Config:
        from_attributes = True

class KonsentrasiDetailOut(KonsentrasiOut):
    program_nama: Optional[str] = None
    bidang_nama: Optional[str] = None


# ---------- Bidang Keahlian ----------

@router.get("/bidang", response_model=list[BidangOut])
def list_bidang(db: Session = Depends(get_db), guru: Guru = Depends(get_current_guru)):
    return db.query(BidangKeahlian).order_by(BidangKeahlian.kode).all()

@router.post("/bidang", response_model=BidangOut)
def create_bidang(
    body: BidangIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if db.query(BidangKeahlian).filter(BidangKeahlian.nama == body.nama).first():
        raise HTTPException(status_code=409, detail=f"Bidang '{body.nama}' sudah ada")
    row = BidangKeahlian(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.put("/bidang/{bidang_id}", response_model=BidangOut)
def update_bidang(
    bidang_id: int,
    body: BidangIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(BidangKeahlian).filter(BidangKeahlian.id == bidang_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Bidang keahlian tidak ditemukan")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row

@router.delete("/bidang/{bidang_id}")
def delete_bidang(
    bidang_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(BidangKeahlian).filter(BidangKeahlian.id == bidang_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Bidang keahlian tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------- Program Keahlian ----------

@router.get("/program", response_model=list[ProgramOut])
def list_program(
    bidang_id: Optional[int] = None,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    q = db.query(ProgramKeahlian)
    if bidang_id:
        q = q.filter(ProgramKeahlian.bidang_id == bidang_id)
    return q.order_by(ProgramKeahlian.kode).all()

@router.post("/program", response_model=ProgramOut)
def create_program(
    body: ProgramIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if not db.query(BidangKeahlian).filter(BidangKeahlian.id == body.bidang_id).first():
        raise HTTPException(status_code=404, detail="Bidang keahlian tidak ditemukan")
    row = ProgramKeahlian(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.put("/program/{program_id}", response_model=ProgramOut)
def update_program(
    program_id: int,
    body: ProgramIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(ProgramKeahlian).filter(ProgramKeahlian.id == program_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Program keahlian tidak ditemukan")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row

@router.delete("/program/{program_id}")
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(ProgramKeahlian).filter(ProgramKeahlian.id == program_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Program keahlian tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------- Konsentrasi Keahlian ----------

@router.get("/konsentrasi", response_model=list[KonsentrasiDetailOut])
def list_konsentrasi(
    program_id: Optional[int] = None,
    bidang_id: Optional[int] = None,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    q = (
        db.query(KonsentrasiKeahlian)
        .join(ProgramKeahlian, KonsentrasiKeahlian.program_id == ProgramKeahlian.id)
        .join(BidangKeahlian, ProgramKeahlian.bidang_id == BidangKeahlian.id)
        .options(
            joinedload(KonsentrasiKeahlian.program).joinedload(ProgramKeahlian.bidang)
        )
    )
    if program_id:
        q = q.filter(KonsentrasiKeahlian.program_id == program_id)
    if bidang_id:
        q = q.filter(ProgramKeahlian.bidang_id == bidang_id)
    rows = q.order_by(KonsentrasiKeahlian.kode).all()

    result = []
    for r in rows:
        item = KonsentrasiDetailOut.model_validate(r)
        item.program_nama = r.program.nama if r.program else None
        item.bidang_nama = r.program.bidang.nama if r.program and r.program.bidang else None
        result.append(item)
    return result

@router.post("/konsentrasi", response_model=KonsentrasiOut)
def create_konsentrasi(
    body: KonsentrasiIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if not db.query(ProgramKeahlian).filter(ProgramKeahlian.id == body.program_id).first():
        raise HTTPException(status_code=404, detail="Program keahlian tidak ditemukan")
    row = KonsentrasiKeahlian(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.put("/konsentrasi/{konsentrasi_id}", response_model=KonsentrasiOut)
def update_konsentrasi(
    konsentrasi_id: int,
    body: KonsentrasiIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(KonsentrasiKeahlian).filter(KonsentrasiKeahlian.id == konsentrasi_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Konsentrasi keahlian tidak ditemukan")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row

@router.delete("/konsentrasi/{konsentrasi_id}")
def delete_konsentrasi(
    konsentrasi_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(KonsentrasiKeahlian).filter(KonsentrasiKeahlian.id == konsentrasi_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Konsentrasi keahlian tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------- Data Lengkap (Tree) ----------

@router.get("/tree")
def get_tree(db: Session = Depends(get_db), guru: Guru = Depends(get_current_guru)):
    """Struktur lengkap: Bidang -> Program -> Konsentrasi, untuk dropdown cascading."""
    bidang_list = (
        db.query(BidangKeahlian)
        .options(
            joinedload(BidangKeahlian.program_keahlian).joinedload(ProgramKeahlian.konsentrasi_keahlian)
        )
        .order_by(BidangKeahlian.kode)
        .all()
    )
    return [
        {
            "id": b.id,
            "nama": b.nama,
            "kode": b.kode,
            "program": [
                {
                    "id": p.id,
                    "nama": p.nama,
                    "kode": p.kode,
                    "konsentrasi": [
                        {
                            "id": k.id,
                            "nama": k.nama,
                            "kode": k.kode,
                            "durasi_tahun": k.durasi_tahun,
                        }
                        for k in p.konsentrasi_keahlian
                    ],
                }
                for p in b.program_keahlian
            ],
        }
        for b in bidang_list
    ]