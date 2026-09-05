import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Siswa, FaceEmbedding, Guru, Device, KonsentrasiKeahlian
from app.auth import require_role, get_current_guru, get_guru_or_device
from app.services.crypto import encrypt_embedding

router = APIRouter(prefix="/siswa", tags=["siswa"])


# ---------- Schemas khusus router ini ----------

class SiswaIn(BaseModel):
    nis: str
    nama: str
    kelas: str
    jurusan: str = "Teknik Elektronika"
    konsentrasi_id: Optional[int] = None


class SiswaOut(BaseModel):
    id: int
    nis: str
    nama: str
    kelas: str
    jurusan: str
    konsentrasi_id: Optional[int] = None
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
    auth: Guru | Device = Depends(get_guru_or_device),
):
    """Daftar siswa aktif — SELURUH roster (bukan hanya yang sudah enroll).

    Menerima JWT guru (dashboard web) ATAU Device API Key (kiosk Android):
    kiosk butuh roster lengkap untuk layar "Data Siswa" dan untuk memilih
    siswa yang BELUM enroll di layar Enrollment. `GET /embeddings/sync` hanya
    mengirim siswa yang sudah punya embedding, jadi tidak cukup untuk itu.
    """
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

@router.delete("/{siswa_id}")
def deactivate_siswa(
    siswa_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Soft delete: set aktif=False (bukan hapus baris, supaya riwayat absensi
    tetap utuh). PRD_EMBEDDING_SYNC: siswa nonaktif tetap dikirim via
    GET /embeddings/sync dengan aktif=false, sehingga client kiosk bisa
    menghapus cache embedding lokal dan siswa tidak bisa absen lagi.
    """
    row = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    row.aktif = False
    # Bump timestamp embedding supaya client yang sudah sync incremental
    # (diperbarui_sejak) tetap menerima status aktif=false ini pada siklus
    # sync berikutnya — tanpa ini, penonaktifan tidak pernah terkirim.
    emb = db.query(FaceEmbedding).filter(FaceEmbedding.siswa_id == siswa_id).first()
    if emb:
        emb.diperbarui_pada = datetime.utcnow()
    db.commit()
    return {"status": "ok", "siswa_id": siswa_id, "aktif": False}


@router.post("/{siswa_id}/aktifkan")
def aktifkan_siswa(
    siswa_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Kebalikan dari DELETE /siswa/{id} — satu-satunya jalan mengembalikan
    siswa yang keliru dinonaktifkan (manual, atau oleh cron retensi wajah
    di app/routers/retensi.py — mis. siswa program 4 tahun yang salah
    ditandai kedaluwarsa umur embedding-nya, lihat docs/API_CONTRACT.md
    bagian 3a). Tanpa endpoint ini, penonaktifan tidak bisa dibatalkan
    lewat API sama sekali (PUT /siswa/{id} tidak menerima field `aktif`,
    dan POST /enroll menolak siswa yang aktif=False — lihat catatan di
    enroll_siswa di bawah).

    Kalau embedding wajahnya belum terlanjur dihapus permanen (masih
    dalam jeda propagasi 7 hari retensi), siswa langsung bisa absen lagi
    setelah kiosk sync berikutnya. Kalau sudah terlanjur dihapus, siswa
    tetap harus di-enroll ulang wajahnya — tapi sekarang endpoint enroll
    tidak lagi menolaknya karena aktif sudah True lagi.
    """
    row = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if row.aktif:
        return {"status": "ok", "siswa_id": siswa_id, "aktif": True, "embedding_tersedia": None}

    row.aktif = True
    emb = db.query(FaceEmbedding).filter(FaceEmbedding.siswa_id == siswa_id).first()
    if emb:
        # Bump supaya client yang sync incremental (diperbarui_sejak) tetap
        # menerima status aktif=true ini pada siklus sync berikutnya.
        emb.diperbarui_pada = datetime.utcnow()
    db.commit()
    return {"status": "ok", "siswa_id": siswa_id, "aktif": True, "embedding_tersedia": emb is not None}


@router.get("/template-csv")
def download_template_siswa_csv(
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Download template CSV untuk import massal siswa. Kolom: nis,nama,kelas,
    jurusan,konsentrasi_id. Baris contoh diambil dari konsentrasi keahlian
    yang ada (jika ada) supaya user tahu format konsentrasi_id yang valid.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["nis", "nama", "kelas", "jurusan", "konsentrasi_id"])

    # 3 baris contoh dari konsentrasi keahlian terdaftar (jika ada)
    konsentrasi = db.query(KonsentrasiKeahlian).order_by(KonsentrasiKeahlian.kode).limit(3).all()
    if konsentrasi:
        for k in konsentrasi:
            writer.writerow(["", "Contoh " + k.nama, "XII", k.nama, k.id])
    else:
        writer.writerow(["", "Contoh Siswa", "XII", "Teknik Elektronika", ""])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_siswa.csv"},
    )

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
        konsentrasi_id_raw = (row.get("konsentrasi_id") or "").strip()
        konsentrasi_id = int(konsentrasi_id_raw) if konsentrasi_id_raw.isdigit() else None

        if not nis or not nama or not kelas:
            baris_error.append(f"Baris {i}: kolom nis/nama/kelas kosong")
            continue

        if db.query(Siswa).filter(Siswa.nis == nis).first():
            dilewati += 1
            continue

        db.add(Siswa(nis=nis, nama=nama, kelas=kelas, jurusan=jurusan, konsentrasi_id=konsentrasi_id))
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
    auth: Guru | Device = Depends(get_guru_or_device),
):
    """Simpan/perbarui embedding wajah siswa (terenkripsi). Bisa dipanggil
    ulang untuk re-enroll (menimpa embedding lama).

    Menerima DUA auth (PRD_DUKUNGAN_CLIENT_ANDROID.md R-P1-4):
    - JWT guru (admin / guru_piket) -> `enrolled_oleh` = guru.id
    - Device API Key (kiosk)        -> `enrolled_device_id` = device.device_id
    """
    is_device = isinstance(auth, Device)
    if not is_device and auth.role not in ("admin", "guru_piket"):
        raise HTTPException(status_code=403, detail=f"Role '{auth.role}' tidak boleh enroll")

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
    if is_device:
        siswa.enrolled_oleh = None
        siswa.enrolled_device_id = auth.device_id
    else:
        siswa.enrolled_oleh = auth.id

    db.commit()
    return {
        "status": "ok", "siswa_id": siswa_id, "enrolled": True,
        "sumber": "device" if is_device else "guru",
    }


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
