from datetime import datetime, timedelta, date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absensi, Device, Dispensasi, JadwalStandar, JadwalOverride
from app.schemas import (
    SyncRequest, SyncResponse, SyncResultItem,
    ApprovalRequest,
)
from app.auth import get_current_guru, require_role
from app.models import Guru
from app.routers.device import verify_api_key

router = APIRouter(prefix="/absensi", tags=["absensi"])

BATAS_AWAL_MASUK_JAM = 2  # absen masuk dibuka 2 jam sebelum jam masuk standar


def _verify_device(db: Session, device_id: str, x_device_api_key: str | None) -> Device:
    """
    Setiap request dari client (Windows/Android) wajib menyertakan header
    `X-Device-Api-Key` berisi api_key mentah yang diberikan saat registrasi
    device (lihat POST /device/register). Server membandingkan hash-nya,
    bukan menyimpan/membandingkan key mentah.
    """
    device = db.query(Device).filter(Device.device_id == device_id, Device.aktif == True).first()
    if not device:
        raise HTTPException(status_code=401, detail=f"Device '{device_id}' tidak terdaftar/nonaktif")

    if not x_device_api_key or not verify_api_key(x_device_api_key, device.api_key_hash):
        raise HTTPException(status_code=401, detail="API key device tidak valid")

    device.last_seen_at = datetime.utcnow()
    return device


def _ambil_jadwal_efektif(db: Session, kelas: str | None, tanggal) -> dict | None:
    """Ambil jam masuk/pulang untuk kelas pada tanggal tertentu.
    Cek override dulu, lalu fallback ke jadwal standar.
    Return dict {jam_masuk: time, jam_pulang: time} atau None kalau tidak ada jadwal."""
    if isinstance(tanggal, datetime):
        tanggal = tanggal.date()
    hari_nama = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", None, None][tanggal.weekday()]

    override = (
        db.query(JadwalOverride)
        .filter(JadwalOverride.tanggal == tanggal)
        .filter((JadwalOverride.kelas == kelas) | (JadwalOverride.kelas.is_(None)))
        .order_by(JadwalOverride.kelas.desc().nullslast())
        .first()
    )
    if override and override.jam_masuk and override.jam_pulang:
        return {"jam_masuk": override.jam_masuk, "jam_pulang": override.jam_pulang}

    if not hari_nama:
        return None  # weekend / bukan hari sekolah

    standar = (
        db.query(JadwalStandar)
        .filter(JadwalStandar.hari == hari_nama)
        .filter((JadwalStandar.kelas == kelas) | (JadwalStandar.kelas.is_(None)))
        .order_by(JadwalStandar.kelas.desc().nullslast())
        .first()
    )
    if not standar:
        return None

    return {"jam_masuk": standar.jam_masuk, "jam_pulang": standar.jam_pulang}


def _validasi_jendela_waktu(db: Session, rec, jadwal_efektif: dict) -> str | None:
    """Validasi jendela waktu absen. Return None kalau valid,
    atau pesan alasan penolakan (status "ditolak_kebijakan")."""
    jam_masuk = jadwal_efektif["jam_masuk"]
    jam_pulang = jadwal_efektif["jam_pulang"]
    waktu_aktual = rec.jam_aktual.time()

    if rec.type == "MASUK":
        earliest = (
            datetime.combine(rec.tanggal, jam_masuk)
            - timedelta(hours=BATAS_AWAL_MASUK_JAM)
        ).time()
        if waktu_aktual < earliest:
            return f"Absen masuk belum dibuka (mulai {earliest.strftime('%H:%M')})"

    if rec.type == "PULANG" and waktu_aktual < jam_pulang:
        ada_dispensasi = db.query(Dispensasi).filter(
            Dispensasi.siswa_id == rec.siswa_id,
            Dispensasi.tanggal == rec.tanggal,
            Dispensasi.jenis == "PULANG_CEPAT",
        ).first()
        if not ada_dispensasi:
            return (
                f"Belum waktunya pulang (mulai {jam_pulang.strftime('%H:%M')}), "
                f"tidak ada dispensasi"
            )

    return None



@router.post("/sync", response_model=SyncResponse)
def sync_absensi(
    body: SyncRequest,
    db: Session = Depends(get_db),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    Endpoint utama yang dipanggil client (Windows/Android) saat online untuk
    mengirim batch record absensi yang tersimpan lokal.

    Idempotent: aman dipanggil berkali-kali dengan record_id yang sama
    (misal karena retry setelah timeout) — hasilnya tetap konsisten.

    Anti-duplikasi 2 lapis:
    1. record_id (UUID dari client) sebagai primary key -> retry aman
    2. UNIQUE (siswa_id, tanggal, type) -> mencegah 2 record MASUK/PULANG
       di hari yang sama untuk siswa yang sama, walau record_id beda
       (misal 2 device berbeda kirim absen untuk siswa yang sama)
    """
    hasil: list[SyncResultItem] = []
    disimpan = duplikat = gagal = 0

    for rec in body.records:
        _verify_device(db, rec.device_id, x_device_api_key)

        # Savepoint per-record: kalau 1 record gagal, tidak menggagalkan
        # seluruh batch — record lain dalam batch tetap diproses.
        savepoint = db.begin_nested()
        try:
            existing = db.execute(
                select(Absensi).where(Absensi.record_id == rec.record_id)
            ).scalar_one_or_none()

            if existing is not None:
                # record_id sudah pernah masuk sebelumnya -> ini retry, bukan data baru
                savepoint.rollback()
                hasil.append(SyncResultItem(
                    record_id=rec.record_id, status="duplikat_diabaikan",
                    pesan="record_id sudah pernah disinkronkan",
                ))
                duplikat += 1
                continue

            # Validasi jendela waktu (server sebagai wasit akhir)
            # Client menolak lebih awal, tapi server tetap validasi ulang.
            jadwal_efektif = _ambil_jadwal_efektif(db, None, rec.tanggal)
            if jadwal_efektif:
                penolakan = _validasi_jendela_waktu(db, rec, jadwal_efektif)
                if penolakan:
                    savepoint.rollback()
                    hasil.append(SyncResultItem(
                        record_id=rec.record_id,
                        status="ditolak_kebijakan",
                        pesan=penolakan,
                    ))
                    continue

            row = Absensi(
                record_id=rec.record_id,
                siswa_id=rec.siswa_id,
                tanggal=rec.tanggal,
                type=rec.type,
                jam_aktual=rec.jam_aktual,
                status_kehadiran_otomatis=rec.status_kehadiran_otomatis,
                catatan=rec.catatan,
                device_id=rec.device_id,
            )
            db.add(row)
            savepoint.commit()

            hasil.append(SyncResultItem(record_id=rec.record_id, status="disimpan"))
            disimpan += 1

        except IntegrityError:
            # Constraint UNIQUE(siswa_id, tanggal, type) yang menolak —
            # artinya siswa ini SUDAH punya record MASUK/PULANG hari itu
            # dengan record_id yang berbeda (dikirim device lain, dsb).
            savepoint.rollback()
            hasil.append(SyncResultItem(
                record_id=rec.record_id, status="duplikat_diabaikan",
                pesan="siswa sudah punya record jenis ini untuk tanggal tsb",
            ))
            duplikat += 1

        except Exception as e:
            savepoint.rollback()
            hasil.append(SyncResultItem(record_id=rec.record_id, status="gagal", pesan=str(e)))
            gagal += 1

    db.commit()

    return SyncResponse(
        total=len(body.records), disimpan=disimpan, duplikat=duplikat, gagal=gagal, hasil=hasil,
    )


@router.get("/perlu-verifikasi")
def list_perlu_verifikasi(
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Daftar absensi hari ini yang status otomatisnya bukan NORMAL
    dan belum di-approve — ini yang ditampilkan di dashboard guru piket."""
    from datetime import date
    rows = (
        db.query(Absensi)
        .filter(
            Absensi.tanggal == date.today(),
            Absensi.status_kehadiran_otomatis != "NORMAL",
            Absensi.status_kehadiran_final.is_(None),
        )
        .all()
    )
    return rows


@router.post("/{record_id}/approve")
def approve_absensi(
    record_id: str,
    body: ApprovalRequest,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Guru piket meng-approve/mengubah status final absensi (lihat 8.2 di
    dokumen arsitektur — status otomatis tetap sementara sampai diverifikasi)."""
    from datetime import datetime

    row = db.query(Absensi).filter(Absensi.record_id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Record absensi tidak ditemukan")

    row.status_kehadiran_final = body.status_kehadiran_final
    row.catatan = body.catatan or row.catatan
    row.approved_by = guru.id
    row.approved_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "record_id": record_id}
