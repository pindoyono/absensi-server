from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.routers import login, absensi, siswa, jadwal, laporan, device, embeddings, guru, dispensasi, spektrum
from app.database import get_db
from app.models import Device

app = FastAPI(
    title="API Absensi Face Recognition",
    description=(
        "Server pusat untuk sistem absensi offline-first SMK. "
        "Lihat docs/API_CONTRACT.md untuk panduan integrasi client Windows/Android."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://front.smkn2malinau.sch.id", "https://absen.smkn2malinau.sch.id"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login.router)
app.include_router(absensi.router)
app.include_router(siswa.router)
app.include_router(jadwal.router)
app.include_router(laporan.router)
app.include_router(device.router)
app.include_router(embeddings.router)
app.include_router(guru.router)
app.include_router(dispensasi.router)
app.include_router(spektrum.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status-kesehatan")
def status_kesehatan(db: Session = Depends(get_db)):
    """
    PRD-observability-degradasi-offline-first §5.2.
    Ringkasan kesehatan server untuk dashboard admin. Menampilkan
    status degradasi offline-first: device yang "diam-diam" basi
    (data jadwal/dispensasi tidak fresh) padahal online.
    """
    from datetime import datetime, timezone

    devices = db.query(Device).all()
    now = datetime.now(timezone.utc)
    device_status = []
    for d in devices:
        last_seen = d.last_seen_at
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        online = bool(last_seen and (now - last_seen).total_seconds() < 300)

        jadwal_jam = d.jadwal_jam_lalu
        dispensasi_jam = d.dispensasi_jam_lalu
        # None = belum pernah sync sama sekali (lebih parah dari basi)
        jadwal_basi = jadwal_jam is None or jadwal_jam > 24
        dispensasi_basi = dispensasi_jam is None or dispensasi_jam > 24
        basi_dan_online = online and (jadwal_basi or dispensasi_basi)

        device_status.append({
            "device_id": d.device_id,
            "nama_lokasi": d.nama_lokasi,
            "platform": d.platform,
            "aktif": d.aktif,
            "online": online,
            "last_seen_at": d.last_seen_at,
            "jadwal_jam_lalu": jadwal_jam,
            "dispensasi_jam_lalu": dispensasi_jam,
            "health_dilaporkan_pada": d.health_dilaporkan_pada,
            "jadwal_basi": jadwal_basi,
            "dispensasi_basi": dispensasi_basi,
            "basi_dan_online": basi_dan_online,
        })

    return {
        "server": "ok",
        "total_device": len(devices),
        "device_aktif": sum(1 for d in device_status if d["aktif"]),
        "device_online": sum(1 for d in device_status if d["online"]),
        "device_basi_dan_online": sum(1 for d in device_status if d["basi_dan_online"]),
        "devices": device_status,
    }
