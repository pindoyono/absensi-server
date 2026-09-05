"""Waktu "sekolah" — semua logika bisnis berbasis tanggal HARUS pakai ini.

Server sering jalan di zona UTC (default container), sedangkan sekolah ada
di WITA (UTC+8). `date.today()` polos akan menganggap masih "kemarin" tiap
hari jam 00:00–08:00 WITA — bikin jadwal/override, validasi jendela absen
pagi, dan laporan harian meleset. Pakai `hari_ini()` / `sekarang()` di sini.

Offset tetap +08:00: seluruh Indonesia (WIB/WITA/WIT) tidak pernah memakai
DST sejak 1964, jadi tak perlu database zona waktu (`tzdata`) — aman di
Windows/container minimal sekalipun.
"""
from datetime import date, datetime, timedelta, timezone

# WITA — Malinau, Kalimantan Utara. Ganti jam bila sekolah pindah zona.
ZONA_SEKOLAH = timezone(timedelta(hours=8), "WITA")


def sekarang() -> datetime:
    """Waktu sekarang di zona sekolah (aware)."""
    return datetime.now(ZONA_SEKOLAH)


def hari_ini() -> date:
    """Tanggal hari ini menurut zona sekolah — pengganti `date.today()`."""
    return sekarang().date()
