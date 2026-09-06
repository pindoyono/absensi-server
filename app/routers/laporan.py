from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absensi, Siswa, Guru, JadwalOverride, Kelas
from app.auth import get_current_guru
from app.services.waktu import hari_ini

router = APIRouter(prefix="/laporan", tags=["laporan"])


def _jumlah_hari_sekolah(db: Session, dari: date, sampai: date) -> int:
    """Hari sekolah dalam rentang = SENIN–JUMAT, dikurangi tanggal yang ditandai
    libur lewat JadwalOverride sekolah-wide (jam_masuk / jam_pulang kosong).
    Dipakai untuk 'tanpa keterangan' di rekap — supaya akhir pekan & hari libur
    tidak dihitung sebagai alpa."""
    if sampai < dari:
        return 0
    libur = {
        o.tanggal for o in db.query(JadwalOverride).filter(
            JadwalOverride.tanggal >= dari,
            JadwalOverride.tanggal <= sampai,
            JadwalOverride.kelas_id.is_(None),
        ).all()
        if o.jam_masuk is None or o.jam_pulang is None
    }
    total = 0
    d = dari
    while d <= sampai:
        if d.weekday() < 5 and d not in libur:  # 0=Senin .. 4=Jumat
            total += 1
        d += timedelta(days=1)
    return total


@router.get("/rekap")
def rekap_kehadiran(
    kelas: Optional[str] = None,
    dari_tanggal: date = Query(...),
    sampai_tanggal: date = Query(...),
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    """
    Rekap per siswa untuk periode tertentu — dipakai halaman "Rekap
    kehadiran" di dashboard. Wali kelas otomatis dibatasi ke kelas yang
    diampu saja (role-based, bukan cuma UI-level filtering).
    """
    q = db.query(Siswa).filter(Siswa.aktif == True)
    if guru.role == "wali_kelas":
        wali_kelas_ids = [k.id for k in db.query(Kelas.id).filter(Kelas.wali_id == guru.id).all()]
        q = q.filter(Siswa.kelas_id.in_(wali_kelas_ids or [-1]))
        kelas = ",".join(
            k.nama for k in db.query(Kelas.nama).filter(Kelas.wali_id == guru.id).all()
        ) or "kelas diampu"
    elif kelas:
        kid = db.query(Kelas.id).filter(Kelas.nama == kelas).scalar()
        q = q.filter(Siswa.kelas_id == kid) if kid else q.filter(Siswa.id == -1)
    siswa_list = q.order_by(Siswa.nama).all()

    hari_sekolah = _jumlah_hari_sekolah(db, dari_tanggal, sampai_tanggal)
    hasil = []
    for s in siswa_list:
        rekaman = (
            db.query(Absensi)
            .filter(
                Absensi.siswa_id == s.id,
                Absensi.tanggal >= dari_tanggal,
                Absensi.tanggal <= sampai_tanggal,
                Absensi.type == "MASUK",
            )
            .all()
        )

        def status_final(r):
            return r.status_kehadiran_final or r.status_kehadiran_otomatis

        hadir = sum(1 for r in rekaman if status_final(r) == "NORMAL")
        terlambat = sum(1 for r in rekaman if status_final(r) == "TERLAMBAT")
        izin = sum(1 for r in rekaman if status_final(r) in ("IZIN", "SAKIT"))

        # Hari sekolah (Senin–Jumat, minus libur) − hari siswa punya record.
        # Untuk akurasi penuh perlu kalender libur lengkap; JadwalOverride
        # sekolah-wide sudah menutup kasus umum (libur nasional dll).
        tanpa_keterangan = max(hari_sekolah - len(rekaman), 0)

        hasil.append({
            "siswa_id": s.id,
            "nis": s.nis,
            "nama": s.nama,
            "kelas": s.kelas,
            "hadir": hadir,
            "terlambat": terlambat,
            "izin": izin,
            "tanpa_keterangan_estimasi": tanpa_keterangan,
        })

    return {
        "periode": {"dari": dari_tanggal, "sampai": sampai_tanggal},
        "kelas": kelas or "semua",
        "data": hasil,
    }


@router.get("/ringkasan-hari-ini")
def ringkasan_hari_ini(db: Session = Depends(get_db), guru: Guru = Depends(get_current_guru)):
    """Angka ringkas untuk kartu di bagian atas dashboard guru piket."""
    today = hari_ini()  # tanggal WITA

    total_siswa = db.query(Siswa).filter(Siswa.aktif == True).count()

    masuk_hari_ini = db.query(Absensi).filter(Absensi.tanggal == today, Absensi.type == "MASUK")

    sudah_masuk = masuk_hari_ini.count()
    tepat_waktu = masuk_hari_ini.filter(Absensi.status_kehadiran_otomatis == "NORMAL").count()
    terlambat = masuk_hari_ini.filter(Absensi.status_kehadiran_otomatis == "TERLAMBAT").count()

    return {
        "total_siswa": total_siswa,
        "sudah_masuk": sudah_masuk,
        "tepat_waktu": tepat_waktu,
        "terlambat": terlambat,
        "belum_masuk": total_siswa - sudah_masuk,
    }
