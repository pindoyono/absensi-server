"""Rate limiter sederhana berbasis memori (sliding window).

Cukup untuk melindungi endpoint sensitif dari spam/brute-force bot pada
deployment 1–beberapa worker. TIDAK dibagi antar proses/worker — kalau
nanti pakai banyak worker atau butuh jaminan kuat, ganti ke slowapi+Redis.

Pemakaian::

    from app.services.rate_limit import batasi

    @router.post("/login/google", dependencies=[Depends(batasi("login", 10, 60))])
    def login_google(...): ...
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # X-Forwarded-For diisi reverse proxy (nginx/Caddy). Ambil IP paling kiri.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def batasi(nama: str, maks: int, per_detik: int):
    """Dependency: maksimal `maks` request per `per_detik` detik per IP untuk
    grup `nama`. Lewat batas → HTTP 429."""

    def _dep(request: Request):
        ip = _client_ip(request)
        key = f"{nama}:{ip}"
        sekarang = time.monotonic()
        batas_bawah = sekarang - per_detik
        with _lock:
            q = _hits[key]
            while q and q[0] < batas_bawah:
                q.popleft()
            if len(q) >= maks:
                retry = max(1, int(q[0] + per_detik - sekarang) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Terlalu banyak permintaan, coba lagi nanti.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(sekarang)
            # Jaga dict tidak tumbuh tanpa batas: buang key yang sudah kosong
            # sesekali (murah, hanya saat key ini kebetulan jadi 1 entri).
            if len(_hits) > 5000:
                for k in [k for k, v in list(_hits.items()) if not v]:
                    _hits.pop(k, None)

    return Depends(_dep)


def _reset_untuk_test() -> None:
    with _lock:
        _hits.clear()
