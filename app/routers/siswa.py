import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Siswa, FaceEmbedding, Guru, Device, KonsentrasiKeahlian, Absensi, Dispensasi, Kelas
from app.auth import require_role, get_current_guru, get_guru_or_device, get_current_siswa
from app.services.crypto import encrypt_embedding
from app.services.waktu import hari_ini

router = APIRouter(prefix="/siswa", tags=["siswa"])


# ---------- Schemas khusus router ini ----------

class SiswaIn(BaseModel):
    nis: str
    nama: str
    # Rombel — ID relasi ke tabel `kelas`. NULL = belum ada rombel.
    kelas_id: Optional[int] = None
    jurusan: str = "Teknik Elektronika"
    konsentrasi_id: Optional[int] = None
    # Opsional — kalau diisi, siswa ini bisa login Google di dashboard web
    # (role tetap "siswa", akses terbatas). Lihat POST /auth/login/google.
    email: Optional[EmailStr] = None


class SiswaOut(BaseModel):
    id: int
    nis: str
    nama: str
    kelas_id: Optional[int] = None
    kelas: str  # nama rombel hasil relasi — kontrak lama (kiosk/CSV/laporan)
    jurusan: str
    konsentrasi_id: Optional[int] = None
    enrolled: bool
    tanggal_enrollment: Optional[date] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class SiswaPindahKelasIn(BaseModel):
    """Body PATCH /siswa/{id} — pindah rombel (dipakai drag-and-drop di
    halaman Manajemen Kelas). `kelas_id` null = keluarkan dari rombel."""
    kelas_id: Optional[int] = None


def _validasi_kelas_id(db: Session, kelas_id: Optional[int]) -> None:
    if kelas_id is not None and not db.query(Kelas).filter(Kelas.id == kelas_id).first():
        raise HTTPException(status_code=422, detail=f"kelas_id {kelas_id} tidak ada")


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
    kelas_id: Optional[int] = None,
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
    q = db.query(Siswa).outerjoin(Kelas, Kelas.id == Siswa.kelas_id).filter(Siswa.aktif == True)
    # Kompat: kiosk & filter lama kirim `kelas` = NAMA. Resolve ke id.
    if kelas:
        target = db.query(Kelas.id).filter(Kelas.nama == kelas).scalar()
        if not target:
            return []  # nama kelas tak dikenal → tak ada siswa (bukan 500)
        q = q.filter(Siswa.kelas_id == target)
    if kelas_id is not None:
        # sentinel 0 = "belum ada rombel"
        q = q.filter(Siswa.kelas_id.is_(None)) if kelas_id == 0 else q.filter(Siswa.kelas_id == kelas_id)
    if enrolled is not None:
        q = q.filter(Siswa.enrolled == enrolled)
    return q.order_by(Kelas.nama.nullsfirst(), Siswa.nama).all()


@router.post("", response_model=SiswaOut)
def create_siswa(
    body: SiswaIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if db.query(Siswa).filter(Siswa.nis == body.nis).first():
        raise HTTPException(status_code=409, detail=f"NIS {body.nis} sudah terdaftar")
    if body.email and db.query(Siswa).filter(Siswa.email == body.email).first():
        raise HTTPException(status_code=409, detail=f"Email {body.email} sudah dipakai siswa lain")
    _validasi_kelas_id(db, body.kelas_id)
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
    if body.email and body.email != row.email:
        if db.query(Siswa).filter(Siswa.email == body.email).first():
            raise HTTPException(status_code=409, detail=f"Email {body.email} sudah dipakai siswa lain")
    _validasi_kelas_id(db, body.kelas_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{siswa_id}", response_model=SiswaOut)
def pindah_kelas_siswa(
    siswa_id: int,
    body: SiswaPindahKelasIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """Pindahkan siswa ke rombel lain (atau keluarkan dari rombel bila
    `kelas_id` null). Dipakai oleh drag-and-drop di halaman Manajemen Kelas."""
    row = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    _validasi_kelas_id(db, body.kelas_id)
    row.kelas_id = body.kelas_id
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


@router.delete("/{siswa_id}/hard")
def hard_delete_siswa(
    siswa_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """HAPUS PERMANEN siswa + SEMUA data terkait (absensi, dispensasi,
    embedding wajah). Berbeda dengan `DELETE /siswa/{id}` yang cuma
    menonaktifkan. Untuk membersihkan data uji — TIDAK bisa di-undo.
    Response memuat jumlah baris yang ikut terhapus."""
    row = db.query(Siswa).filter(Siswa.id == siswa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")

    n_absensi = db.query(Absensi).filter(Absensi.siswa_id == siswa_id).delete(synchronize_session=False)
    n_dispensasi = db.query(Dispensasi).filter(Dispensasi.siswa_id == siswa_id).delete(synchronize_session=False)
    n_embedding = db.query(FaceEmbedding).filter(FaceEmbedding.siswa_id == siswa_id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    print(
        f"AUDIT siswa.hard_delete siswa_id={siswa_id} nis={row.nis} "
        f"(absensi={n_absensi}, dispensasi={n_dispensasi}, embedding={n_embedding}) "
        f"oleh guru_id={guru.id} ({guru.email}) pada {datetime.utcnow().isoformat()}"
    )
    return {
        "status": "ok",
        "siswa_id": siswa_id,
        "terhapus": {"absensi": n_absensi, "dispensasi": n_dispensasi, "embedding": n_embedding},
    }


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
    Download template CSV untuk import massal siswa. Kolom: nis,nama,kelas_id,
    jurusan,konsentrasi_id. Kolom `kelas_id` diisi ID rombel dari menu Kelas
    (kosongkan bila belum ada rombel). Baris komentar di atas berisi daftar
    ID kelas yang tersedia sekarang.
    """
    output = io.StringIO()

    daftar_kelas = db.query(Kelas).filter(Kelas.aktif == True).order_by(Kelas.nama).all()
    for k in daftar_kelas:
        output.write(f"# kelas_id {k.id} = {k.nama}\n")

    writer = csv.writer(output)
    writer.writerow(["nis", "nama", "kelas_id", "jurusan", "konsentrasi_id"])

    # 3 baris contoh dari konsentrasi keahlian terdaftar (jika ada)
    konsentrasi = db.query(KonsentrasiKeahlian).order_by(KonsentrasiKeahlian.kode).limit(3).all()
    contoh_kelas_id = daftar_kelas[0].id if daftar_kelas else ""
    if konsentrasi:
        for k in konsentrasi:
            writer.writerow(["", "Contoh " + k.nama, contoh_kelas_id, k.nama, k.id])
    else:
        writer.writerow(["", "Contoh Siswa", contoh_kelas_id, "Teknik Elektronika", ""])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_siswa.csv"},
    )

@router.post("/import")
def import_siswa_csv(
    file: UploadFile = File(..., description="CSV kolom: nis,nama,kelas_id,jurusan,konsentrasi_id"),
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Impor massal dari CSV (export dari Google Sheets sekolah).
    Format kolom wajib: nis,nama — `kelas_id` opsional (ID rombel dari menu
    Kelas; kosong = belum ada rombel), `jurusan`/`konsentrasi_id` opsional.
    Baris yang diawali `#` (komentar daftar kelas di template) diabaikan.
    NIS yang sudah ada akan DILEWATI (tidak menimpa), supaya aman
    dijalankan berulang kali untuk menambah data baru saja.
    """
    content = file.file.read().decode("utf-8-sig")
    baris_bersih = [ln for ln in content.splitlines() if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(baris_bersih)))

    kelas_ids_valid = {row[0] for row in db.query(Kelas.id).all()}

    ditambahkan = dilewati = 0
    baris_error: list[str] = []

    for i, row in enumerate(reader, start=2):  # baris 1 = header
        nis = (row.get("nis") or "").strip()
        nama = (row.get("nama") or "").strip()
        kelas_id_raw = (row.get("kelas_id") or "").strip()
        jurusan = (row.get("jurusan") or "Teknik Elektronika").strip()
        konsentrasi_id_raw = (row.get("konsentrasi_id") or "").strip()
        konsentrasi_id = int(konsentrasi_id_raw) if konsentrasi_id_raw.isdigit() else None

        if not nis or not nama:
            baris_error.append(f"Baris {i}: kolom nis/nama kosong")
            continue

        kelas_id = None
        if kelas_id_raw:
            if not kelas_id_raw.isdigit() or int(kelas_id_raw) not in kelas_ids_valid:
                baris_error.append(f"Baris {i}: kelas_id '{kelas_id_raw}' tidak ada di daftar Kelas")
                continue
            kelas_id = int(kelas_id_raw)

        if db.query(Siswa).filter(Siswa.nis == nis).first():
            dilewati += 1
            continue

        db.add(Siswa(nis=nis, nama=nama, kelas_id=kelas_id, jurusan=jurusan, konsentrasi_id=konsentrasi_id))
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
    siswa.tanggal_enrollment = hari_ini()  # tanggal WITA
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
        db.query(Kelas.nama, func.count(Siswa.id))
        .select_from(Siswa)
        .outerjoin(Kelas, Kelas.id == Siswa.kelas_id)
        .filter(Siswa.aktif == True, Siswa.enrolled == False)
        .group_by(Kelas.nama)
        .all()
    )

    return {
        "total_siswa": total,
        "sudah_enroll": sudah,
        "belum_enroll": total - sudah,
        "persentase": round((sudah / total * 100), 1) if total else 0,
        "belum_enroll_per_kelas": {(k or "(tanpa rombel)"): v for k, v in belum_per_kelas},
    }


# ---------- Self-service siswa (login Google, role tetap "siswa") ----------
# Ditaruh terakhir & pakai prefix path "/saya" yang tidak mungkin bentrok
# dengan {siswa_id} (integer) di endpoint admin di atas.

@router.get("/saya", response_model=SiswaOut)
def profil_saya(siswa: Siswa = Depends(get_current_siswa)):
    """Profil siswa yang sedang login sendiri."""
    return siswa


class AbsensiSayaOut(BaseModel):
    record_id: str
    tanggal: date
    type: str
    jam_aktual: datetime
    status_kehadiran_otomatis: str
    status_kehadiran_final: Optional[str] = None
    catatan: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/saya/absensi", response_model=list[AbsensiSayaOut])
def absensi_saya(
    limit: int = 30,
    siswa: Siswa = Depends(get_current_siswa),
    db: Session = Depends(get_db),
):
    """Riwayat absensi milik siswa yang login sendiri — TIDAK bisa lihat
    data siswa lain (siswa_id diambil dari token, bukan dari query param)."""
    rows = (
        db.query(Absensi)
        .filter(Absensi.siswa_id == siswa.id)
        .order_by(Absensi.tanggal.desc(), Absensi.jam_aktual.desc())
        .limit(min(limit, 100))
        .all()
    )
    # record_id kolom UUID — dikonversi manual ke str, bukan mengandalkan
    # from_attributes (pydantic v2 tidak otomatis meng-cast UUID -> str).
    return [
        AbsensiSayaOut(
            record_id=str(r.record_id),
            tanggal=r.tanggal,
            type=r.type,
            jam_aktual=r.jam_aktual,
            status_kehadiran_otomatis=r.status_kehadiran_otomatis,
            status_kehadiran_final=r.status_kehadiran_final,
            catatan=r.catatan,
        )
        for r in rows
    ]
