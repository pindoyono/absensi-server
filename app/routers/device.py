import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Device, Guru
from app.auth import require_role, get_current_guru
from app.services.device_auth import verify_device, hash_api_key, verify_api_key
from app.services.geo import jarak_meter
from app.services import device_claim

router = APIRouter(prefix="/device", tags=["device"])


class DeviceIn(BaseModel):
    device_id: str | None = None  # opsional — kosongkan untuk generate otomatis
    nama_lokasi: str
    platform: str  # 'windows' | 'android'


class DeviceUpdateIn(BaseModel):
    """Field device yang boleh diubah admin setelah didaftarkan.
    Semua opsional — hanya yang dikirim yang diubah."""
    nama_lokasi: str | None = None
    platform: str | None = None  # 'windows' | 'android'


class DeviceOut(BaseModel):
    device_id: str
    nama_lokasi: str
    platform: str
    aktif: bool
    last_seen_at: datetime | None = None
    dibuat_pada: datetime | None = None
    raw_api_key: str | None = None
    # PRD-observability-degradasi-offline-first §5.1: kesegaran data
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None
    health_dilaporkan_pada: datetime | None = None
    # Geofencing (lihat LokasiIn / endpoint /lokasi di bawah)
    lokasi_lat: float | None = None
    lokasi_lng: float | None = None
    radius_meter: int | None = None
    lokasi_valid_terakhir: bool | None = None
    lokasi_alasan_terakhir: str | None = None
    lokasi_dicek_pada: datetime | None = None

    class Config:
        from_attributes = True

class DeviceHealthIn(BaseModel):
    jadwal_jam_lalu: float | None = None
    dispensasi_jam_lalu: float | None = None


class ClaimQrOut(BaseModel):
    """Data untuk render QR provisioning device (dipakai dashboard)."""
    device_id: str
    token: str
    expires_at: datetime
    payload: str  # string JSON yang di-encode jadi QR


class ClaimIn(BaseModel):
    token: str


class ClaimOut(BaseModel):
    """Hasil tukar token — kiosk menyimpan ini sebagai konfigurasinya."""
    server: str
    device_id: str
    nama_lokasi: str | None = None
    api_key: str
    face_encryption_key: str


class LokasiIn(BaseModel):
    """Titik acuan geofencing untuk satu device — diisi admin lewat peta di dashboard."""
    lat: float
    lng: float
    radius_meter: int


class LokasiCekIn(BaseModel):
    """
    Dikirim kiosk secara berkala (bukan per-scan absensi — device tidak
    berpindah antar scan, dan minta fix GPS tiap scan terlalu lambat).

    `tersedia=False` berarti kiosk tidak bisa dapat lokasi sama sekali
    (izin ditolak / GPS mati / timeout) — lat/lng/mock diabaikan.
    `mock=True` berarti OS Android mendeteksi lokasi ini dari mock
    provider (`LocationCompat.isMock`) — lihat catatan keamanan di
    docs/API_CONTRACT.md bagian geofencing soal batas deteksi ini.
    """
    tersedia: bool
    lat: float | None = None
    lng: float | None = None
    akurasi_meter: float | None = None
    mock: bool = False


class LokasiCekOut(BaseModel):
    valid: bool
    alasan: str
    jarak_meter: float | None = None
    # Beda dengan `valid`: ini murni "apakah admin sudah pasang titik acuan
    # untuk device ini", lepas dari hasil cek jarak/mock/dsb. Dipakai client
    # untuk indikator ikon "lokasi sudah diatur atau belum" — string-matching
    # ke `alasan` terlalu rapuh untuk keperluan itu. Diisi di akhir
    # cek_lokasi_device(), default False di sini cuma supaya tiap cabang
    # if/elif di bawah tidak perlu menyebutkannya berulang.
    dikonfigurasi: bool = False


class LokasiKonfigOut(BaseModel):
    """Titik acuan geofencing device ini, apa adanya — dipakai client
    men-cache konfigurasi lokal supaya bisa validasi jarak sendiri (Haversine)
    saat offline, tanpa perlu round-trip ke POST /lokasi/cek. Endpoint ini
    device-auth (bukan admin) justru karena device-lah yang membutuhkannya."""
    lokasi_lat: float | None = None
    lokasi_lng: float | None = None
    radius_meter: int | None = None


@router.get("", response_model=list[DeviceOut])
def list_device(db: Session = Depends(get_db), guru: Guru = Depends(require_role("admin", "guru_piket"))):
    return db.query(Device).all()


def _generate_device_id(db: Session) -> str:
    """Generate device_id unik (Opsi B): dev-XXXXXXXX (8 karakter aman URL)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    for _ in range(10):  # hindari tabrakan unik yang sangat kecil kemungkinannya
        candidate = "dev-" + "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.query(Device).filter(Device.device_id == candidate).first():
            return candidate
    raise HTTPException(status_code=500, detail="Gagal generate device_id unik")


@router.post("/register")
def register_device(
    body: DeviceIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Daftarkan device baru. API key mentah HANYA ditampilkan sekali di
    response ini — server hanya menyimpan hash-nya (SHA-256). Admin harus
    menyalin device_id + api_key ini ke konfigurasi device (Windows/Android)
    saat setup. Kalau key hilang, harus regenerate (bukan bisa dilihat ulang).

    Opsi B: device_id otomatis di-generate (dev-XXXXXXXX) kalau tidak diisi.
    Admin tetap boleh override lewat field device_id (tetap divalidasi unik).
    """
    device_id = body.device_id
    if device_id:
        device_id = device_id.strip()
        if db.query(Device).filter(Device.device_id == device_id).first():
            raise HTTPException(status_code=409, detail="device_id sudah terdaftar")
    else:
        device_id = _generate_device_id(db)

    raw_key = secrets.token_urlsafe(32)
    row = Device(
        device_id=device_id,
        nama_lokasi=body.nama_lokasi,
        platform=body.platform,
        api_key_hash=hash_api_key(raw_key),
        raw_api_key=raw_key,
    )
    # Token QR provisioning — langsung dibuat supaya QR bisa ditampilkan
    # begitu device dibuat (lihat POST /device/claim + GET /device/{id}/claim-qr).
    claim_token, claim_expires = device_claim.buat_claim_token(row)
    db.add(row)
    db.commit()

    # face_encryption_key (Fernet key server) ikut dikirim di sini — sekali, lewat
    # HTTPS — supaya client Android/Windows auto-isi tanpa distribusi manual.
    # PRD_DUKUNGAN_CLIENT_ANDROID.md R-P1-1. Endpoint ini membocorkan kunci
    # enkripsi embedding: audit-log tiap panggilan.
    print(
        f"AUDIT device.register device_id={device_id} oleh guru_id={guru.id} "
        f"({guru.email}) pada {datetime.utcnow().isoformat()}"
    )
    return {
        "device_id": device_id,
        "api_key": raw_key,  # tampil SEKALI SAJA, simpan baik-baik
        "face_encryption_key": settings.face_encryption_key,
        "peringatan": "Simpan device_id & api_key ini sekarang — tidak akan ditampilkan lagi.",
        # QR provisioning: kiosk bisa scan alih-alih menyalin manual.
        "claim": {
            "token": claim_token,
            "expires_at": claim_expires.replace(tzinfo=timezone.utc).isoformat(),
            "payload": device_claim.payload_qr(claim_token),
        },
    }


@router.post("/{device_id}/regenerate-key")
def regenerate_key(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")

    raw_key = secrets.token_urlsafe(32)
    device.api_key_hash = hash_api_key(raw_key)
    device.raw_api_key = raw_key
    db.commit()
    return {"device_id": device_id, "api_key": raw_key}


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: str,
    body: DeviceUpdateIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """Ubah metadata device (nama lokasi / platform). Tidak menyentuh api_key,
    geofencing, atau status aktif. Nama lokasi baru ikut terkirim saat kiosk
    provisioning ulang lewat QR (POST /device/claim)."""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")

    if body.nama_lokasi is not None:
        nama = body.nama_lokasi.strip()
        if not nama:
            raise HTTPException(status_code=422, detail="nama_lokasi tidak boleh kosong")
        device.nama_lokasi = nama
    if body.platform is not None:
        if body.platform not in ("windows", "android"):
            raise HTTPException(status_code=422, detail="platform harus 'windows' atau 'android'")
        device.platform = body.platform

    db.commit()
    db.refresh(device)
    print(
        f"AUDIT device.update device_id={device_id} oleh guru_id={guru.id} "
        f"({guru.email}) pada {datetime.utcnow().isoformat()}"
    )
    return device


@router.get("/{device_id}/claim-qr", response_model=ClaimQrOut)
def claim_qr_device(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """Buat token QR provisioning BARU untuk device (menimpa yang lama).
    Dashboard memanggil ini lalu me-render `payload` sebagai QR. Kiosk yang
    memindainya menukarnya lewat POST /device/claim."""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")

    token, expires = device_claim.buat_claim_token(device)
    db.commit()
    print(
        f"AUDIT device.claim_qr device_id={device_id} oleh guru_id={guru.id} "
        f"({guru.email}) pada {datetime.utcnow().isoformat()}"
    )
    return ClaimQrOut(
        device_id=device_id,
        token=token,
        expires_at=expires.replace(tzinfo=timezone.utc),  # UTC eksplisit untuk client
        payload=device_claim.payload_qr(token),
    )


@router.post("/claim", response_model=ClaimOut)
def claim_device(body: ClaimIn, db: Session = Depends(get_db)):
    """Tukar token QR (sekali-pakai) jadi kredensial device. TANPA auth —
    token acak 256-bit itu sendiri yang jadi bukti. Token langsung hangus
    setelah berhasil ditukar."""
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token kosong")

    device = db.query(Device).filter(Device.claim_token == token).first()
    if not device or not device_claim.token_masih_berlaku(device):
        raise HTTPException(status_code=404, detail="Token tidak valid atau sudah kedaluwarsa")

    device.claim_token = None
    device.claim_token_expires = None
    db.commit()
    print(
        f"AUDIT device.claim device_id={device.device_id} pada {datetime.utcnow().isoformat()}"
    )
    return ClaimOut(
        server=settings.public_base_url.rstrip("/"),
        device_id=device.device_id,
        nama_lokasi=device.nama_lokasi,
        api_key=device.raw_api_key,
        face_encryption_key=settings.face_encryption_key,
    )


@router.get("/{device_id}/lokasi", response_model=LokasiKonfigOut)
def get_lokasi_konfig_device(
    device_id: str,
    db: Session = Depends(get_db),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    Device menarik konfigurasi lokasinya SENDIRI (titik acuan + radius apa
    adanya, bukan hasil cek) supaya bisa di-cache lokal dan dipakai validasi
    jarak (Haversine) sendiri saat offline — lihat client-android
    GeoOffline.kt. Device-auth, bukan admin: yang butuh data ini justru
    device itu sendiri, bukan dashboard (dashboard sudah punya lewat
    GET /device biasa).
    """
    device = verify_device(db, device_id, x_device_api_key)
    return LokasiKonfigOut(
        lokasi_lat=device.lokasi_lat,
        lokasi_lng=device.lokasi_lng,
        radius_meter=device.radius_meter,
    )


@router.put("/{device_id}/lokasi", response_model=DeviceOut)
def atur_lokasi_device(
    device_id: str,
    body: LokasiIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    """
    Set/ubah titik acuan geofencing (pin di peta dashboard) + radius toleransi.
    Reset status cek terakhir — supaya dashboard tidak menampilkan status lama
    yang diukur terhadap titik lokasi yang sudah tidak berlaku.
    """
    if body.radius_meter <= 0:
        raise HTTPException(status_code=422, detail="radius_meter harus lebih dari 0")
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")

    device.lokasi_lat = body.lat
    device.lokasi_lng = body.lng
    device.radius_meter = body.radius_meter
    device.lokasi_valid_terakhir = None
    device.lokasi_alasan_terakhir = None
    device.lokasi_dicek_pada = None
    db.commit()
    db.refresh(device)
    return device


@router.post("/{device_id}/lokasi/cek", response_model=LokasiCekOut)
def cek_lokasi_device(
    device_id: str,
    body: LokasiCekIn,
    db: Session = Depends(get_db),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    Dipanggil kiosk secara berkala (lihat docstring LokasiCekIn). Kiosk-lah
    yang memutuskan blokir dirinya sendiri berdasarkan `valid` di response
    ini — server hanya menyimpan hasilnya untuk ditampilkan di dashboard
    (kolom `lokasi_valid_terakhir` dkk pada DeviceOut).

    Fail-closed: device TANPA lokasi diatur (lokasi_lat/lng NULL) dianggap
    TIDAK valid — admin wajib mengatur titik acuan dulu (PUT
    /device/{id}/lokasi) sebelum device itu bisa dipakai absen. Ini
    sengaja bukan opt-in lagi: kalau NULL dianggap valid, device baru yang
    belum sempat di-setup lokasinya diam-diam tidak pernah diproteksi.
    """
    device = verify_device(db, device_id, x_device_api_key)
    dikonfigurasi = device.lokasi_lat is not None and device.lokasi_lng is not None and device.radius_meter is not None

    if not dikonfigurasi:
        hasil = LokasiCekOut(valid=False, alasan="lokasi belum diatur untuk device ini — hubungi admin")
    elif not body.tersedia:
        hasil = LokasiCekOut(valid=False, alasan="lokasi tidak tersedia (izin ditolak / GPS mati)")
    elif body.mock:
        hasil = LokasiCekOut(valid=False, alasan="GPS palsu (mock location) terdeteksi")
    elif body.lat is None or body.lng is None:
        hasil = LokasiCekOut(valid=False, alasan="koordinat tidak dikirim")
    else:
        jarak = jarak_meter(device.lokasi_lat, device.lokasi_lng, body.lat, body.lng)
        if jarak <= device.radius_meter:
            hasil = LokasiCekOut(valid=True, alasan="dalam radius", jarak_meter=round(jarak, 1))
        else:
            hasil = LokasiCekOut(
                valid=False,
                alasan=f"di luar radius ({round(jarak)}m dari titik, batas {device.radius_meter}m)",
                jarak_meter=round(jarak, 1),
            )

    hasil.dikonfigurasi = dikonfigurasi
    device.lokasi_valid_terakhir = hasil.valid
    device.lokasi_alasan_terakhir = hasil.alasan
    device.lokasi_dicek_pada = datetime.utcnow()
    db.commit()
    return hasil


@router.delete("/{device_id}")
def deactivate_device(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    device.aktif = False
    db.commit()
    return {"status": "dinonaktifkan"}

@router.delete("/{device_id}/hard")
def hard_delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin")),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    db.delete(device)
    db.commit()
    return {"status": "dihapus permanen"}


# Ambang batas basi — HARUS sama dengan BATAS_STALE_JADWAL_JAM /
# BATAS_STALE_DISPENSASI_JAM di config client kiosk, supaya dashboard dan
# kiosk "sepakat" soal kapan data dianggap basi (PRD-tuntaskan-device-health §3).
BATAS_STALE_JADWAL_JAM = 6
BATAS_STALE_DISPENSASI_JAM = 2


@router.post("/{device_id}/health")
def report_device_health(
    device_id: str,
    body: DeviceHealthIn,
    db: Session = Depends(get_db),
    x_device_api_key: str | None = Header(default=None, alias="X-Device-Api-Key"),
):
    """
    PRD-observability-degradasi-offline-first §5.1.
    Client kiosk melaporkan kesegaran data jadwal & dispensasi.

    Butuh X-Device-Api-Key (sama seperti /absensi/sync, /embeddings/sync,
    /jadwal/efektif) -- TANPA ini, device_id bisa ditebak/dipalsukan untuk
    mengirim laporan kesehatan palsu.
    """
    verify_device(db, device_id, x_device_api_key)

    device = db.query(Device).filter(Device.device_id == device_id).first()
    device.jadwal_jam_lalu = body.jadwal_jam_lalu
    device.dispensasi_jam_lalu = body.dispensasi_jam_lalu
    device.health_dilaporkan_pada = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.get("/status-kesehatan")
def status_kesehatan_semua_device(
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    """
    PRD-tuntaskan-device-health §3. Dipakai dashboard — ringkasan kesehatan
    semua device aktif. Ambang batas sama dengan config client kiosk.
    """
    devices = db.query(Device).filter(Device.aktif == True).all()
    return [
        {
            "device_id": d.device_id,
            "nama_lokasi": d.nama_lokasi,
            "online_terakhir": d.last_seen_at,
            "health_dilaporkan_pada": d.health_dilaporkan_pada,
            "jadwal_jam_lalu": d.jadwal_jam_lalu,
            "dispensasi_jam_lalu": d.dispensasi_jam_lalu,
            "jadwal_bermasalah": (d.jadwal_jam_lalu or 999) > BATAS_STALE_JADWAL_JAM,
            "dispensasi_bermasalah": (d.dispensasi_jam_lalu or 999) > BATAS_STALE_DISPENSASI_JAM,
            "belum_pernah_lapor": d.health_dilaporkan_pada is None,
        }
        for d in devices
    ]
