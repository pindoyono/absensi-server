"""
Enkripsi data sensitif (face embedding) sebelum disimpan ke database.

Menggunakan Fernet (symmetric encryption, AES-128-CBC + HMAC) dari
library `cryptography` — dipilih karena portable (tidak terikat ke
ekstensi database tertentu seperti pgcrypto), mudah diaudit, dan
key management-nya eksplisit lewat environment variable.

PENTING: FACE_ENCRYPTION_KEY di .env harus digenerate sekali saat
setup awal dan TIDAK BOLEH HILANG — kalau key hilang, seluruh data
embedding yang tersimpan tidak bisa didekripsi lagi (harus enrollment
ulang semua siswa). Simpan backup key di tempat aman terpisah dari
database (misal password manager sekolah), bukan cuma di server yang
sama dengan database.
"""
import struct

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet = Fernet(settings.face_encryption_key.encode())


def encrypt_embedding(embedding: list[float]) -> bytes:
    """Ubah vector embedding (list of float) jadi bytes terenkripsi."""
    raw = struct.pack(f"{len(embedding)}f", *embedding)
    return _fernet.encrypt(raw)


def decrypt_embedding(encrypted: bytes) -> list[float]:
    """Kebalikan dari encrypt_embedding — dipakai saat proses matching."""
    try:
        raw = _fernet.decrypt(encrypted)
    except InvalidToken:
        raise ValueError("Gagal dekripsi embedding — key salah atau data korup")
    n_floats = len(raw) // 4
    return list(struct.unpack(f"{n_floats}f", raw))


def generate_new_key() -> str:
    """Helper untuk generate FACE_ENCRYPTION_KEY baru saat setup awal.
    Jalankan sekali: python -c "from app.services.crypto import generate_new_key; print(generate_new_key())"
    lalu salin hasilnya ke .env"""
    return Fernet.generate_key().decode()
