from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/absensi"

    # Domain email Google Workspace sekolah yang boleh login sebagai guru/admin.
    # Bisa lebih dari satu domain, dipisah koma. Ganti sesuai domain sekolah.
    allowed_email_domains: str = "smkxxx.sch.id"

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

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def allowed_email_domain_list(self) -> list[str]:
        """Parse daftar domain dari env: dipisah koma, tanpa spasi/@."""
        return [
            d.strip().lstrip("@").lower()
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        ]


settings = Settings()
