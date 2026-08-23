from app.services.crypto import encrypt_embedding, decrypt_embedding


def test_enkripsi_dekripsi_embedding_konsisten():
    original = [0.123, -0.456, 0.789, 1.0, -1.0] * 26  # 130 nilai, mirip embedding asli
    encrypted = encrypt_embedding(original)

    assert isinstance(encrypted, bytes)
    assert str(original).encode() not in encrypted  # bukan disimpan sebagai teks mentah

    decrypted = decrypt_embedding(encrypted)
    assert len(decrypted) == len(original)
    for a, b in zip(original, decrypted):
        assert abs(a - b) < 1e-5  # toleransi floating point


def test_embedding_terenkripsi_berbeda_tiap_kali():
    """Fernet menyertakan random IV, jadi hasil enkripsi dari data yang
    sama pun harus berbeda tiap kali — memastikan tidak ada pola yang
    bisa dianalisis dari ciphertext."""
    original = [0.1, 0.2, 0.3]
    e1 = encrypt_embedding(original)
    e2 = encrypt_embedding(original)
    assert e1 != e2
    assert decrypt_embedding(e1) == decrypt_embedding(e2)
