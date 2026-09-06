from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JadwalStandar, JadwalOverride, Guru, Device, Kelas
from app.auth import require_role, get_current_guru, get_guru_or_device
from app.services.waktu import hari_ini

router = APIRouter(prefix="/jadwal", tags=["jadwal"])


class JadwalStandarIn(BaseModel):
    hari: str  # SENIN..JUMAT
    kelas_id: Optional[int] = None  # NULL = berlaku semua kelas
    jam_masuk: time
    jam_pulang: time


class JadwalOverrideIn(BaseModel):
    tanggal: date
    kelas_id: Optional[int] = None
    kelas: Optional[str] = None  # kompat: nama kelas (di-resolve ke kelas_id)
    jam_masuk: Optional[time] = None
    jam_pulang: Optional[time] = None
    alasan: Optional[str] = None


class JadwalOverrideDeviceIn(BaseModel):
    """Body POST /jadwal/override — dipakai bersama oleh JWT guru maupun
    Device API Key (PRD_JADWAL_OVERRIDE_DEVICE). Untuk guru, jam boleh
    kosong (backward-compatible); untuk device wajib terisi (divalidasi
    manual di handler).

    Kelas bisa dikirim sebagai `kelas_id` (dashboard) ATAU `kelas` = nama
    (kiosk yang belum tahu tabel kelas). Nama yang tak dikenal diperlakukan
    sebagai NULL / berlaku semua kelas (jangan 500)."""
    tanggal: date
    kelas: Optional[str] = None
    kelas_id: Optional[int] = None
    jam_masuk: Optional[time] = None
    jam_pulang: Optional[time] = None
    alasan: Optional[str] = None
    client_id: Optional[str] = None  # UUID idempotency key dari device


HARI_VALID = {"SENIN", "SELASA", "RABU", "KAMIS", "JUMAT"}


def _kelas_nama(db: Session, kelas_id: Optional[int]) -> Optional[str]:
    if not kelas_id:
        return None
    return db.query(Kelas.nama).filter(Kelas.id == kelas_id).scalar()


def _resolve_kelas_id(db: Session, nama: Optional[str]) -> Optional[int]:
    """Nama kelas → id. Nama kosong / tak dikenal → None (school-wide)."""
    if not nama:
        return None
    return db.query(Kelas.id).filter(Kelas.nama == nama).scalar()


def _serialize_standar(db: Session, row: JadwalStandar) -> dict:
    return {
        "id": row.id,
        "hari": row.hari,
        "kelas_id": row.kelas_id,
        "kelas": _kelas_nama(db, row.kelas_id),
        "jam_masuk": row.jam_masuk,
        "jam_pulang": row.jam_pulang,
    }


def _serialize_override(db: Session, row: JadwalOverride) -> dict:
    return {
        "id": row.id,
        "tanggal": row.tanggal,
        "kelas_id": row.kelas_id,
        "kelas": _kelas_nama(db, row.kelas_id),
        "jam_masuk": row.jam_masuk,
        "jam_pulang": row.jam_pulang,
        "alasan": row.alasan,
        "client_id": row.client_id,
        "device_id": row.device_id,
        "sumber": row.sumber,
        "dibuat_oleh": row.dibuat_oleh,
        "dibuat_pada": row.dibuat_pada,
    }


@router.get("/standar")
def list_jadwal_standar(db: Session = Depends(get_db), guru: Guru = Depends(get_current_guru)):
    rows = db.query(JadwalStandar).order_by(JadwalStandar.hari).all()
    return [_serialize_standar(db, r) for r in rows]


@router.post("/standar")
def upsert_jadwal_standar(
    body: JadwalStandarIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    if body.hari not in HARI_VALID:
        raise HTTPException(status_code=400, detail=f"hari harus salah satu dari {HARI_VALID}")
    if body.kelas_id is not None and not db.query(Kelas).filter(Kelas.id == body.kelas_id).first():
        raise HTTPException(status_code=422, detail=f"kelas_id {body.kelas_id} tidak ada")

    existing = (
        db.query(JadwalStandar)
        .filter(JadwalStandar.hari == body.hari, JadwalStandar.kelas_id == body.kelas_id)
        .first()
    )
    if existing:
        existing.jam_masuk = body.jam_masuk
        existing.jam_pulang = body.jam_pulang
    else:
        db.add(JadwalStandar(**body.model_dump()))
    db.commit()
    return {"status": "ok"}


@router.delete("/standar/{standar_id}")
def delete_jadwal_standar(
    standar_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """Hapus satu baris jadwal standar. Dipakai untuk membuang jadwal khusus
    kelas tertentu sehingga kelas itu kembali mengikuti jadwal umum (kelas_id
    NULL). Menghapus baris umum berarti hari itu tak punya jadwal standar
    sama sekali (kiosk akan menganggap 'tidak ada sekolah')."""
    row = db.query(JadwalStandar).filter(JadwalStandar.id == standar_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jadwal standar tidak ditemukan")
    db.delete(row)
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
    rows = q.order_by(JadwalOverride.tanggal.desc()).all()
    return [_serialize_override(db, r) for r in rows]


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
            return _serialize_override(db, existing)

    # Kelas: dashboard kirim kelas_id; kiosk kirim nama. Nama tak dikenal → NULL.
    kelas_id = body.kelas_id if body.kelas_id is not None else _resolve_kelas_id(db, body.kelas)

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
        kelas_id=kelas_id,
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
    return _serialize_override(db, row)

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
    kelas_id = body.kelas_id if body.kelas_id is not None else _resolve_kelas_id(db, body.kelas)
    if kelas_id is not None and not db.query(Kelas).filter(Kelas.id == kelas_id).first():
        raise HTTPException(status_code=422, detail=f"kelas_id {kelas_id} tidak ada")
    for k, v in body.model_dump(exclude={"kelas"}).items():
        setattr(row, k, v)
    row.kelas_id = kelas_id
    row.dibuat_oleh = guru.id
    db.commit()
    db.refresh(row)
    return _serialize_override(db, row)

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
    today = hari_ini()  # tanggal WITA — server bisa jalan di UTC
    hari_nama = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", None, None][today.weekday()]

    kid = _resolve_kelas_id(db, kelas)  # kiosk kirim nama; None kalau tak dikenal

    override = (
        db.query(JadwalOverride)
        .filter(JadwalOverride.tanggal == today)
        .filter((JadwalOverride.kelas_id == kid) | (JadwalOverride.kelas_id.is_(None)))
        .order_by(JadwalOverride.kelas_id.desc().nullslast())  # kelas spesifik menang atas NULL
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
        .filter((JadwalStandar.kelas_id == kid) | (JadwalStandar.kelas_id.is_(None)))
        .order_by(JadwalStandar.kelas_id.desc().nullslast())
        .first()
    )
    if not standar:
        raise HTTPException(status_code=404, detail="Jadwal standar untuk hari/kelas ini belum diatur")

    return {"sumber": "standar", "jam_masuk": standar.jam_masuk, "jam_pulang": standar.jam_pulang}
