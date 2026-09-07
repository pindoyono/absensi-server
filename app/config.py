from pydantic_settings import BaseSettings, SettingsConfigDict

# Nilai default yang di-commit di repo (juga muncul di .env.example). Kalau
# salah satunya masih terpakai saat runtime = deployment belum mengisi .env,
# dan server TIDAK aman (JWT bisa dipalsukan / embedding pakai kunci publik).
# Dipakai oleh app.main untuk menolak boot di mode produksi.
DEFAULT_JWT_SECRET = "GANTI_DENGAN_SECRET_ACAK_YANG_PANJANG"
DEFAULT_FACE_KEY = "s6wnLcVDT-5on-ZSWvd9QZcrmLJ1PnYtjFXQZG_lWSw="
PLACEHOLDER_SECRETS = {
    DEFAULT_JWT_SECRET,
    DEFAULT_FACE_KEY,
    "ganti_dengan_string_acak_panjang_dan_rahasia",
    "ganti_dengan_hasil_generate_new_key",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://user:password@localhost:5432/absensi"

    # Domain email Google Workspace sekolah yang boleh login sebagai guru/admin.
    # Bisa lebih dari satu domain, dipisah koma. Ganti sesuai domain sekolah.
    allowed_email_domains: str = "smkxxx.sch.id"

    # URL publik server ini (tanpa trailing slash) — di-encode ke QR provisioning
    # device supaya kiosk yang memindai tahu harus konek ke mana. Lihat
    # app/services/device_claim.py.
    public_base_url: str = "https://absen.smkn2malinau.sch.id"

    # Dipakai untuk terbitkan & verifikasi JWT internal setelah login Google berhasil
    jwt_secret: str = "GANTI_DENGAN_SECRET_ACAK_YANG_PANJANG"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12  # 12 jam

    # Google OAuth client ID (dari Google Cloud Console, untuk verifikasi id_token)
    google_client_id: str = ""

    # Key enkripsi untuk face_embedding. Default di bawah HANYA untuk
    # development lokal (supaya app bisa langsung dijalankan tanpa setup) —
    # WAJIB diganti dengan key unik sebelum production, generate dengan:
    # python -c "from app.services.crypto import generate_new_key; print(generate_new_key())"
    face_encryption_key: str = "s6wnLcVDT-5on-ZSWvd9QZcrmLJ1PnYtjFXQZG_lWSw="

    # Secret statis untuk endpoint retensi data wajah (dipanggil cron OS,
    # bukan user login) — lihat app/routers/retensi.py. Kosong = endpoint
    # menolak semua request (aman-default, harus sengaja diisi di production).
    retensi_cron_secret: str = ""

    # Set APP_ENV=production di server produksi supaya app.main menolak boot
    # bila masih ada secret placeholder.
    app_env: str = "development"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in ("production", "prod")

    def secret_placeholder_errors(self) -> list[str]:
        """Daftar masalah konfigurasi keamanan yang fatal di produksi."""
        masalah: list[str] = []
        if self.jwt_secret in PLACEHOLDER_SECRETS or len(self.jwt_secret) < 32:
            masalah.append("JWT_SECRET masih placeholder / terlalu pendek (<32 char)")
        if self.face_encryption_key in PLACEHOLDER_SECRETS:
            masalah.append("FACE_ENCRYPTION_KEY masih placeholder — generate kunci Fernet unik")
        if not self.google_client_id:
            masalah.append("GOOGLE_CLIENT_ID kosong — login Google tidak akan berfungsi")
        if "user:password@localhost" in self.database_url:
            masalah.append("DATABASE_URL masih memakai kredensial contoh")
        return masalah

    @property
    def allowed_email_domain_list(self) -> list[str]:
        """Parse daftar domain dari env: dipisah koma, tanpa spasi/@."""
        return [
            d.strip().lstrip("@").lower()
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        ]


settings = Settings()
