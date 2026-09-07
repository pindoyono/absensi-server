import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import login, absensi, siswa, jadwal, laporan, device, embeddings, guru, dispensasi, spektrum, retensi, kelas

log = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Guard kesiapan produksi: jangan biarkan server jalan dengan secret
    # placeholder yang di-commit di repo (JWT bisa dipalsukan siapa saja,
    # embedding wajah terenkripsi dengan kunci publik).
    masalah = settings.secret_placeholder_errors()
    if masalah:
        pesan = "Konfigurasi keamanan belum lengkap:\n  - " + "\n  - ".join(masalah)
        if settings.is_production:
            raise RuntimeError(pesan + "\n\nSet nilainya di .env sebelum deploy (APP_ENV=production).")
        log.warning("%s\n(APP_ENV bukan production — server tetap jalan untuk dev.)", pesan)
    yield


app = FastAPI(
    title="API Absensi Face Recognition",
    description=(
        "Server pusat untuk sistem absensi offline-first SMK. "
        "Lihat docs/API_CONTRACT.md untuk panduan integrasi client Windows/Android."
    ),
    version="1.0.0",
    lifespan=lifespan,
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
app.include_router(retensi.router)
app.include_router(kelas.router)


@app.get("/health")
def health():
    return {"status": "ok"}
