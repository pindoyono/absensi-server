from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Siswa, FaceEmbedding, Device
from app.routers.device import verify_api_key

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get("/sync")
def sync_embeddings(
    diperbarui_sejak: Optional[datetime] = None,
    db: Session = Depends(get_db),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    Dipanggil client (Windows/Android) untuk menarik/memperbarui cache
    embedding wajah siswa ke database lokal (SQLite), supaya matching
    tetap bisa jalan walau offline.

    Kirim `diperbarui_sejak` (timestamp terakhir kali client sync) untuk
    hanya menarik embedding yang berubah sejak itu — hindari transfer
    ulang seluruh 1000 embedding tiap kali sync.

    PENTING: embedding dikirim dalam bentuk terenkripsi apa adanya
    (tidak didekripsi di sini). Client menyimpannya di SQLite lokal
    yang juga terenkripsi (SQLCipher) — server tidak pernah mengirim
    embedding dalam bentuk plain melalui jaringan.
    """
    if not x_device_id:
        raise HTTPException(status_code=401, detail="Header X-Device-Id wajib diisi")

    device = db.query(Device).filter(Device.device_id == x_device_id, Device.aktif == True).first()
    if not device or not x_device_api_key or not verify_api_key(x_device_api_key, device.api_key_hash):
        raise HTTPException(status_code=401, detail="Device tidak valid")

    q = (
        db.query(Siswa, FaceEmbedding)
        .join(FaceEmbedding, FaceEmbedding.siswa_id == Siswa.id)
    )
    if diperbarui_sejak:
        q = q.filter(FaceEmbedding.diperbarui_pada > diperbarui_sejak)

    hasil = []
    for siswa, emb in q.all():
        hasil.append({
            "siswa_id": siswa.id,
            "nis": siswa.nis,
            "nama": siswa.nama,
            "kelas": siswa.kelas,
            "aktif": siswa.aktif,
            "embedding_encrypted": emb.embedding_encrypted.hex(),  # hex agar aman di JSON
            "model_version": emb.model_version,
            "diperbarui_pada": emb.diperbarui_pada,
        })

    return {
        "server_time": datetime.utcnow(),
        "jumlah": len(hasil),
        "data": hasil,
    }
