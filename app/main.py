from fastapi import FastAPI

from app.routers import login, absensi, siswa, jadwal, laporan, device, embeddings

app = FastAPI(
    title="API Absensi Face Recognition",
    description=(
        "Server pusat untuk sistem absensi offline-first SMK. "
        "Lihat docs/API_CONTRACT.md untuk panduan integrasi client Windows/Android."
    ),
    version="1.0.0",
)

app.include_router(login.router)
app.include_router(absensi.router)
app.include_router(siswa.router)
app.include_router(jadwal.router)
app.include_router(laporan.router)
app.include_router(device.router)
app.include_router(embeddings.router)


@app.get("/health")
def health():
    return {"status": "ok"}
