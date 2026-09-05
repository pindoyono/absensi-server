"""app/services/waktu.py — "hari ini" harus mengikuti zona sekolah (WITA, UTC+8),
bukan zona server (sering UTC di container)."""
from datetime import datetime, timedelta, timezone

import app.services.waktu as waktu


def test_sekarang_aware_offset_wita():
    now = waktu.sekarang()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=8)


def test_hari_ini_pakai_wita_bukan_utc(monkeypatch):
    """Server UTC menunjuk 2026-09-05 23:30 → di WITA sudah 2026-09-06."""
    asli = datetime

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc = asli(2026, 9, 5, 23, 30, tzinfo=timezone.utc)
            return utc.astimezone(tz) if tz is not None else utc

    monkeypatch.setattr(waktu, "datetime", FakeDatetime)
    assert waktu.hari_ini().isoformat() == "2026-09-06"


def test_hari_ini_siang_wita_sama_dengan_utc(monkeypatch):
    """Siang WITA (05:00 UTC) → tanggal sama di kedua zona."""
    asli = datetime

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc = asli(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
            return utc.astimezone(tz) if tz is not None else utc

    monkeypatch.setattr(waktu, "datetime", FakeDatetime)
    assert waktu.hari_ini().isoformat() == "2026-09-06"
