from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import login, absensi, siswa, jadwal, laporan, device, embeddings, guru, dispensasi, spektrum, retensi

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
app.include_router(retensi.router)


@app.get("/health")
def health():
    return {"status": "ok"}
