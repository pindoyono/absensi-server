import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Siswa, FaceEmbedding, Guru
from app.auth import require_role, get_current_guru
from app.services.crypto import encrypt_embedding

router = APIRouter(prefix="/siswa", tags=["siswa"])


# ---------- Schemas khusus router ini ----------

class SiswaIn(BaseModel):
    nis: str
    nama: str
    kelas: str
    jurusan: str = "Teknik Elektronika"


class SiswaOut(BaseModel):
    id: int
    nis: str
    nama: str
    kelas: str
    jurusan: str
    enrolled: bool
    tanggal_enrollment: Optional[date] = None

    class Config:
        from_attributes = True


class EnrollRequest(BaseModel):
    """
    Embedding wajah DIHITUNG DI CLIENT (memakai engine MiniFASNet yang sama
    dipakai untuk matching sehari-hari), bukan di server. Ini keputusan
    desain sengaja: menghindari server perlu dependency machine learning
    berat, dan memastikan model yang dipakai untuk enrollment SAMA PERSIS
    dengan model yang dipakai untuk matching harian (mencegah mismatch
    versi model antara proses enroll vs proses absen).
    """
    embedding: list[float] = Field(..., min_length=64, description="Vector embedding wajah dari engine client")
    model_version: str = Field(..., description="misal 'minifasnet-v1' — dicatat untuk audit kompatibilitas model")

    model_config = {"protected_namespaces": ()}


# ---------- Endpoints ----------

@router.get("", response_model=list[SiswaOut])
def list_siswa(
    kelas: Optional[str] = None,
    enrolled: Optional[bool] = None,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    q = db.query(Siswa).filter(Siswa.aktif == True)
    if kelas:
        q = q.filter(Siswa.kelas == kelas)
    if enrolled is not None:
        q = q.filter(Siswa.enrolled == enrolled)
    return q.order_by(Siswa.kelas, Siswa.nama).all()


@router.post("", response_model=SiswaOut)
def create_siswa(
    body: SiswaIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if db.query(Siswa).filter(Siswa.nis == body.nis).first():
        raise HTTPException(status_code=409, detail=f"NIS {body.nis} sudah terdaftar")
    row = Siswa(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{siswa_id}", response_model=SiswaOut)
def update_siswa(
    siswa_id: int,
    body: SiswaIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    row = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.post("/import")
def import_siswa_csv(
    file: UploadFile = File(..., description="CSV kolom: nis,nama,kelas,jurusan"),
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Impor massal dari CSV (export dari Google Sheets sekolah).
    Format kolom wajib: nis,nama,kelas — kolom jurusan opsional.
    NIS yang sudah ada akan DILEWATI (tidak menimpa), supaya aman
    dijalankan berulang kali untuk menambah data baru saja.
    """
    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    ditambahkan = dilewati = 0
    baris_error: list[str] = []

    for i, row in enumerate(reader, start=2):  # baris 1 = header
        nis = (row.get("nis") or "").strip()
        nama = (row.get("nama") or "").strip()
        kelas = (row.get("kelas") or "").strip()
        jurusan = (row.get("jurusan") or "Teknik Elektronika").strip()

        if not nis or not nama or not kelas:
            baris_error.append(f"Baris {i}: kolom nis/nama/kelas kosong")
            continue

        if db.query(Siswa).filter(Siswa.nis == nis).first():
            dilewati += 1
            continue

        db.add(Siswa(nis=nis, nama=nama, kelas=kelas, jurusan=jurusan))
        ditambahkan += 1

    db.commit()
    return {
        "ditambahkan": ditambahkan,
        "dilewati_sudah_ada": dilewati,
        "baris_error": baris_error,
    }


@router.post("/{siswa_id}/enroll")
def enroll_siswa(
    siswa_id: int,
    body: EnrollRequest,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Simpan/perbarui embedding wajah siswa (terenkripsi). Bisa dipanggil
    ulang untuk re-enroll (menimpa embedding lama)."""
    siswa = db.query(Siswa).filter(Siswa.id == siswa_id, Siswa.aktif == True).first()
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")

    encrypted = encrypt_embedding(body.embedding)

    existing = db.query(FaceEmbedding).filter(FaceEmbedding.siswa_id == siswa_id).first()
    if existing:
        existing.embedding_encrypted = encrypted
        existing.model_version = body.model_version
    else:
        db.add(FaceEmbedding(
            siswa_id=siswa_id,
            embedding_encrypted=encrypted,
            model_version=body.model_version,
        ))

    siswa.enrolled = True
    siswa.tanggal_enrollment = date.today()
    siswa.enrolled_oleh = guru.id

    db.commit()
    return {"status": "ok", "siswa_id": siswa_id, "enrolled": True}


@router.get("/enrollment-progress")
def enrollment_progress(
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Untuk dashboard progres enrollment (bagian 10.3/10.4 dokumen arsitektur)
    — supaya admin tahu siapa saja yang belum enroll tanpa jadwal formal."""
    total = db.query(Siswa).filter(Siswa.aktif == True).count()
    sudah = db.query(Siswa).filter(Siswa.aktif == True, Siswa.enrolled == True).count()

    # query ringkas per kelas untuk yang belum enroll
    from sqlalchemy import func
    belum_per_kelas = (
        db.query(Siswa.kelas, func.count(Siswa.id))
        .filter(Siswa.aktif == True, Siswa.enrolled == False)
        .group_by(Siswa.kelas)
        .all()
    )

    return {
        "total_siswa": total,
        "sudah_enroll": sudah,
        "belum_enroll": total - sudah,
        "persentase": round((sudah / total * 100), 1) if total else 0,
        "belum_enroll_per_kelas": {k: v for k, v in belum_per_kelas},
    }
