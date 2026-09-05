"""Jarak antar koordinat GPS — dipakai validasi geofencing per device."""
import math

BUMI_RADIUS_METER = 6_371_000


def jarak_meter(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Jarak great-circle (formula Haversine) dalam meter."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return BUMI_RADIUS_METER * c
