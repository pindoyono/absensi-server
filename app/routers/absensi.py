import uuid
from datetime import datetime, timedelta, date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absensi, Device, Dispensasi, JadwalStandar, JadwalOverride, Siswa, Kelas
from app.schemas import (
    SyncRequest, SyncResponse, SyncResultItem,
    ApprovalRequest,
)
from app.auth import get_current_guru, require_role
from app.models import Guru
from app.services.device_auth import verify_device
from app.services.waktu import hari_ini

router = APIRouter(prefix="/absensi", tags=["absensi"])

BATAS_AWAL_MASUK_JAM = 2  # absen masuk dibuka 2 jam sebelum jam masuk standar

# Catatan: helper verifikasi device sebelumnya berupa fungsi private
# `_verify_device` di file ini. Dipindahkan ke app/services/device_auth.py
# (`verify_device`) supaya bisa dipakai bersama oleh POST /device/{id}/health
# tanpa impor lintas-router ke simbol bertanda underscore.


def _ambil_jadwal_efektif(db: Session, kelas_id: int | None, tanggal) -> dict | None:
    """Ambil jam masuk/pulang untuk kelas pada tanggal tertentu.
    Cek override dulu, lalu fallback ke jadwal standar.
    Return dict {jam_masuk: time, jam_pulang: time} atau None kalau tidak ada jadwal."""
    if isinstance(tanggal, datetime):
        tanggal = tanggal.date()
    hari_nama = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", None, None][tanggal.weekday()]

    override = (
        db.query(JadwalOverride)
        .filter(JadwalOverride.tanggal == tanggal)
        .filter((JadwalOverride.kelas_id == kelas_id) | (JadwalOverride.kelas_id.is_(None)))
        .order_by(JadwalOverride.kelas_id.desc().nullslast())
        .first()
    )
    if override and override.jam_masuk and override.jam_pulang:
        return {"jam_masuk": override.jam_masuk, "jam_pulang": override.jam_pulang}

    if not hari_nama:
        return None  # weekend / bukan hari sekolah

    standar = (
        db.query(JadwalStandar)
        .filter(JadwalStandar.hari == hari_nama)
        .filter((JadwalStandar.kelas_id == kelas_id) | (JadwalStandar.kelas_id.is_(None)))
        .order_by(JadwalStandar.kelas_id.desc().nullslast())
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
        verify_device(db, rec.device_id, x_device_api_key)

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
            # PENTING: ambil kelas siswa yang SEBENARNYA -- jadwal bisa
            # berbeda per kelas (lihat JadwalStandar/JadwalOverride yang
            # punya kolom `kelas`), jangan selalu pakai jadwal sekolah-wide.
            kelas_id_siswa = db.query(Siswa.kelas_id).filter(Siswa.id == rec.siswa_id).scalar()
            jadwal_efektif = _ambil_jadwal_efektif(db, kelas_id_siswa, rec.tanggal)
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
                # Tandai saja — record TIDAK ditolak karena mock. Guru piket
                # meninjau lewat /absensi/perlu-verifikasi (lihat filter di sana).
                lokasi_mock=rec.lokasi_mock,
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
    """Daftar absensi hari ini yang belum di-approve dan perlu ditinjau guru
    piket: status otomatisnya bukan NORMAL, ATAU ditandai lokasi mock (fake
    GPS) oleh client. Record lokasi_mock tetap tersimpan (tidak ditolak) —
    di sinilah guru piket melihat & memutuskannya."""
    rows = (
        db.query(Absensi)
        .filter(
            Absensi.tanggal == hari_ini(),
            Absensi.status_kehadiran_final.is_(None),
            or_(
                Absensi.status_kehadiran_otomatis != "NORMAL",
                Absensi.lokasi_mock.is_(True),
            ),
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


@router.delete("/{record_id}")
def hapus_absensi(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """Hapus PERMANEN satu record absensi (koreksi kesalahan / bersihkan data
    uji). Admin-only. Setelah dihapus, constraint UNIQUE(siswa_id, tanggal,
    type) bebas lagi sehingga siswa bisa absen ulang untuk slot itu. Audit-log."""
    row = db.query(Absensi).filter(Absensi.record_id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Record absensi tidak ditemukan")

    jejak = f"siswa_id={row.siswa_id} tanggal={row.tanggal} type={row.type} status={row.status_kehadiran_otomatis}"
    db.delete(row)
    db.commit()
    print(
        f"AUDIT absensi.hapus record_id={record_id} ({jejak}) "
        f"oleh guru_id={guru.id} ({guru.email}) pada {datetime.utcnow().isoformat()}"
    )
    return {"status": "ok", "record_id": record_id}


@router.get("/list")
def list_absensi(
    dari_tanggal: date_cls | None = Query(default=None, description="Filter awal rentang tanggal"),
    sampai_tanggal: date_cls | None = Query(default=None, description="Filter akhir rentang tanggal"),
    kelas: str | None = Query(default=None, description="Filter kelas siswa"),
    type: str | None = Query(default=None, description="Filter jenis absen: MASUK | PULANG"),
    siswa_id: int | None = Query(default=None, description="Filter per siswa"),
    status: str | None = Query(default=None, description="Filter status kehadiran final"),
    cari: str | None = Query(default=None, description="Pencarian bebas: nama/NIS siswa"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    """
    Daftar detail record absensi untuk halaman "Absensi" di dashboard.
    Query terfilter + terpaginate, join dengan siswa untuk menampilkan
    nama/NIS/kelas. Wali kelas otomatis dibatasi ke kelas yang diampu.
    """
    wali_kelas_ids: list[int] | None = None
    if guru.role == "wali_kelas":
        wali_kelas_ids = [k.id for k in db.query(Kelas.id).filter(Kelas.wali_id == guru.id).all()]
        kelas = None  # abaikan filter nama, dibatasi ke kelas yang diampu

    q = (
        db.query(Absensi, Siswa)
        .join(Siswa, Siswa.id == Absensi.siswa_id)
    )

    if wali_kelas_ids is not None:
        q = q.filter(Siswa.kelas_id.in_(wali_kelas_ids or [-1]))
    if dari_tanggal:
        q = q.filter(Absensi.tanggal >= dari_tanggal)
    if sampai_tanggal:
        q = q.filter(Absensi.tanggal <= sampai_tanggal)
    if kelas:
        kid = db.query(Kelas.id).filter(Kelas.nama == kelas).scalar()
        q = q.filter(Siswa.kelas_id == kid) if kid else q.filter(Absensi.siswa_id == -1)
    if type:
        q = q.filter(Absensi.type == type)
    if siswa_id:
        q = q.filter(Absensi.siswa_id == siswa_id)
    if status:
        # status efektif = final kalau sudah di-approve, selain itu otomatis
        q = q.filter(
            or_(
                Absensi.status_kehadiran_final == status,
                and_(
                    Absensi.status_kehadiran_final.is_(None),
                    Absensi.status_kehadiran_otomatis == status,
                ),
            )
        )
    if cari:
        like = f"%{cari}%"
        q = q.filter(or_(Siswa.nama.ilike(like), Siswa.nis.ilike(like)))

    total = q.count()
    rows = (
        q.order_by(Absensi.tanggal.desc(), Absensi.jam_aktual.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for absensi, siswa in rows:
        status_efektif = absensi.status_kehadiran_final or absensi.status_kehadiran_otomatis
        data.append({
            "record_id": str(absensi.record_id),
            "siswa_id": siswa.id,
            "nis": siswa.nis,
            "nama": siswa.nama,
            "kelas": siswa.kelas,
            "tanggal": absensi.tanggal,
            "type": absensi.type,
            "jam_aktual": absensi.jam_aktual,
            "status_kehadiran_otomatis": absensi.status_kehadiran_otomatis,
            "status_kehadiran_final": absensi.status_kehadiran_final,
            "status_efektif": status_efektif,
            "catatan": absensi.catatan,
            "device_id": absensi.device_id,
            "lokasi_mock": absensi.lokasi_mock,
            "approved_by": absensi.approved_by,
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "data": data,
    }
