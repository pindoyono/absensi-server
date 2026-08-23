from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Absensi, Siswa, Guru
from app.auth import get_current_guru

router = APIRouter(prefix="/laporan", tags=["laporan"])


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
    if guru.role == "wali_kelas":
        kelas = guru.kelas_diampu

    q = db.query(Siswa).filter(Siswa.aktif == True)
    if kelas:
        q = q.filter(Siswa.kelas == kelas)
    siswa_list = q.order_by(Siswa.nama).all()

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

        total_hari_sekolah = (sampai_tanggal - dari_tanggal).days + 1
        tanpa_keterangan = max(total_hari_sekolah - len(rekaman), 0)
        # catatan: ini estimasi kasar (asumsi semua hari dlm rentang = hari sekolah).
        # Untuk akurasi penuh, exclude hari libur — lihat catatan di docs/API_CONTRACT.md

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
    today = date.today()

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
