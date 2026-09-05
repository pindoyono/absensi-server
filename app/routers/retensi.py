from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import FaceEmbedding, Siswa

router = APIRouter(prefix="/admin/retensi", tags=["retensi"])

# 3 tahun (siklus SMK) + 1 bulan buffer, dihitung sejak embedding PERTAMA
# kali dibuat (FaceEmbedding.dibuat_pada) — bukan sejak siswa dinonaktifkan.
# Ini jaring pengaman otomatis: kalau admin lupa menonaktifkan siswa yang
# lulus/keluar, data wajahnya tetap punya batas umur maksimum.
BATAS_UMUR_HARI = 365 * 3 + 30

# Jeda antara siswa DINONAKTIFKAN (client mulai menerima aktif=false lewat
# GET /embeddings/sync) dan embedding-nya BENAR-BENAR dihapus dari server.
# Tanpa jeda ini, kiosk yang kebetulan sedang offline saat baris dihapus
# tidak akan pernah menerima sinyal "aktif=false" (baris sudah lenyap dari
# hasil JOIN di /embeddings/sync) dan cache lokalnya jadi yatim selamanya.
JEDA_HAPUS_PERMANEN_HARI = 7


def _verifikasi_secret(x_retensi_secret: str | None) -> None:
    if not settings.retensi_cron_secret:
        raise HTTPException(status_code=503, detail="RETENSI_CRON_SECRET belum dikonfigurasi di server")
    if x_retensi_secret != settings.retensi_cron_secret:
        raise HTTPException(status_code=401, detail="X-Retensi-Secret tidak valid")


@router.post("/bersihkan-wajah")
def bersihkan_wajah_kedaluwarsa(
    db: Session = Depends(get_db),
    x_retensi_secret: str | None = Header(default=None, alias="X-Retensi-Secret"),
):
    """
    Batasi retensi data wajah maksimum ~3 tahun 1 bulan sejak enrollment
    pertama. Dipanggil berkala oleh cron OS (lihat docs/DEPLOYMENT.md),
    bukan oleh admin lewat dashboard — makanya pakai secret statis, bukan
    JWT guru.

    Dua fase per pemanggilan (aman dijalankan ulang tiap hari):
    1. Siswa AKTIF yang embedding-nya sudah lewat umur → nonaktifkan
       (aktif=False) + bump `diperbarui_pada`, supaya kiosk menerima
       sinyal "aktif=false" pada sync berikutnya (mekanisme yang sama
       dengan DELETE /siswa/{id} manual).
    2. Siswa yang SUDAH nonaktif (dari fase 1, run sebelumnya, ATAU
       dinonaktifkan manual oleh admin) dan embedding-nya sudah lewat
       umur DAN sudah melewati jeda propagasi → embedding dihapus
       permanen dari server. Baris `siswa` & riwayat absensi TIDAK
       disentuh (tetap ada untuk laporan/arsip sekolah).
    """
    _verifikasi_secret(x_retensi_secret)

    sekarang = datetime.utcnow()
    batas_umur = sekarang - timedelta(days=BATAS_UMUR_HARI)
    batas_jeda = sekarang - timedelta(days=JEDA_HAPUS_PERMANEN_HARI)

    # Fase 1 — nonaktifkan siswa aktif yang embedding-nya sudah kedaluwarsa.
    kandidat_nonaktif = (
        db.query(Siswa, FaceEmbedding)
        .join(FaceEmbedding, FaceEmbedding.siswa_id == Siswa.id)
        .filter(Siswa.aktif == True, FaceEmbedding.dibuat_pada < batas_umur)
        .all()
    )
    for siswa, emb in kandidat_nonaktif:
        siswa.aktif = False
        emb.diperbarui_pada = sekarang
    db.commit()

    # Fase 2 — hapus permanen embedding siswa nonaktif yang sudah lewat jeda
    # propagasi DAN memang sudah kedaluwarsa umurnya (bukan siswa yang
    # dinonaktifkan admin karena alasan lain sebelum umurnya tercapai).
    kandidat_hapus = (
        db.query(FaceEmbedding)
        .join(Siswa, Siswa.id == FaceEmbedding.siswa_id)
        .filter(
            Siswa.aktif == False,
            FaceEmbedding.dibuat_pada < batas_umur,
            FaceEmbedding.diperbarui_pada < batas_jeda,
        )
        .all()
    )
    jumlah_dihapus = len(kandidat_hapus)
    siswa_id_dihapus = [emb.siswa_id for emb in kandidat_hapus]
    for emb in kandidat_hapus:
        db.delete(emb)
    db.commit()

    return {
        "status": "ok",
        "dinonaktifkan": len(kandidat_nonaktif),
        "dihapus_permanen": jumlah_dihapus,
        "siswa_id_dihapus_permanen": siswa_id_dihapus,
        "batas_umur_hari": BATAS_UMUR_HARI,
    }
