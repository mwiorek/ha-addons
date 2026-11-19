"""Where the sun and the moon are overhead, and how much of the moon is lit. Pure math, no numpy.

All positions are Earth-fixed unit vectors (x towards lon 0 on the equator, z to the north pole),
so the height of a body above any place is one dot product with that place's vector.
"""
import math
from datetime import datetime, timezone

RAD = math.pi / 180


def _days(t):
    """Days since J2000.0 (2000-01-01 12:00 UTC)."""
    return t.timestamp() / 86400 + 2440587.5 - 2451545.0


def _gmst(n):
    return (280.46061837 + 360.98564736629 * n) % 360 * RAD


def _vec(lat, lon):
    c = math.cos(lat)
    return (c * math.cos(lon), c * math.sin(lon), math.sin(lat))


def _equatorial(lam, beta, n):
    """Ecliptic longitude/latitude (rad) -> right ascension, declination (rad)."""
    eps = (23.439 - 0.0000004 * n) * RAD
    ra = math.atan2(math.sin(lam) * math.cos(eps) - math.tan(beta) * math.sin(eps), math.cos(lam))
    dec = math.asin(math.sin(beta) * math.cos(eps) + math.cos(beta) * math.sin(eps) * math.sin(lam))
    return ra, dec


def sun(t):
    """Subsolar point as (lat, lon) in radians. Same series as daynight.subsolar (~0.01 deg)."""
    n = _days(t)
    L, g = (280.460 + 0.9856474 * n) * RAD, (357.528 + 0.9856003 * n) * RAD
    lam = L + (1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) * RAD
    ra, dec = _equatorial(lam, 0.0, n)
    return dec, ra - _gmst(n)


def moon(t):
    """Sublunar point as (lat, lon) in radians: the main terms of the lunar theory (Meeus 47),
    good to about 0.3 deg, a fraction of the moon's drawn size on any of the maps."""
    n = _days(t)
    Lp = 218.316 + 13.176396 * n          # mean longitude
    Mp = (134.963 + 13.064993 * n) * RAD  # moon's mean anomaly
    F = (93.272 + 13.229350 * n) * RAD    # argument of latitude
    D = (297.850 + 12.190749 * n) * RAD   # mean elongation from the sun
    M = (357.529 + 0.98560028 * n) * RAD  # sun's mean anomaly
    lam = (Lp + 6.289 * math.sin(Mp) + 1.274 * math.sin(2 * D - Mp) + 0.658 * math.sin(2 * D)
           + 0.214 * math.sin(2 * Mp) - 0.186 * math.sin(M) - 0.114 * math.sin(2 * F)) * RAD
    beta = (5.128 * math.sin(F) + 0.281 * math.sin(Mp + F) + 0.278 * math.sin(Mp - F)
            + 0.173 * math.sin(2 * D - F)) * RAD
    ra, dec = _equatorial(lam, beta, n)
    return dec, ra - _gmst(n)


MEAN_DISTANCE = 385000.56          # km, the series' mean


def moon_distance(t):
    """Earth-moon distance in km (centre to centre): the largest terms of the lunar theory
    (Meeus 47), good to a few hundred km, well under 1 % of the moon's apparent size."""
    n = _days(t)
    Mp = (134.963 + 13.064993 * n) * RAD
    F = (93.272 + 13.229350 * n) * RAD
    D = (297.850 + 12.190749 * n) * RAD
    M = (357.529 + 0.98560028 * n) * RAD
    return (MEAN_DISTANCE - 20905.355 * math.cos(Mp) - 3699.111 * math.cos(2 * D - Mp)
            - 2955.968 * math.cos(2 * D) - 569.925 * math.cos(2 * Mp) + 48.888 * math.cos(M)
            - 3.149 * math.cos(2 * F) + 246.158 * math.cos(2 * D - 2 * Mp)
            - 152.138 * math.cos(2 * D - M - Mp) - 170.733 * math.cos(2 * D + Mp)
            - 204.586 * math.cos(2 * D - M) - 129.620 * math.cos(M - Mp) + 108.743 * math.cos(D)
            + 104.755 * math.cos(M + Mp) + 10.321 * math.cos(2 * D - 2 * F) + 79.661 * math.cos(Mp - 2 * F)
            - 34.782 * math.cos(4 * D - Mp) - 23.210 * math.cos(3 * Mp) - 21.636 * math.cos(4 * D - 2 * Mp)
            + 24.208 * math.cos(2 * D + M - Mp) + 30.824 * math.cos(2 * D + M))


def moon_size(t):
    """The moon's apparent size against its average: about 0.93 at apogee, 1.07 at perigee."""
    return MEAN_DISTANCE / moon_distance(t)


def sun_vec(t):
    return _vec(*sun(t))


def moon_vec(t):
    return _vec(*moon(t))


def lit_fraction(t):
    """Share of the moon's disc that is lit, 0 (new) to 1 (full). The sun is ~400 times further
    than the moon, so the phase angle is 180 deg minus the sun-moon angle seen from the earth."""
    s, m = sun_vec(t), moon_vec(t)
    cos_psi = sum(a * b for a, b in zip(s, m))
    return (1 - cos_psi) / 2


def place_vec(lat_deg, lon_deg):
    return _vec(lat_deg * RAD, lon_deg * RAD)


def elevation(body_vec, place):
    """Angle of a body above the horizon of a place (both unit vectors), radians (geocentric)."""
    return math.asin(max(-1.0, min(1.0, sum(a * b for a, b in zip(body_vec, place)))))


def azimuth(body_vec, lat_deg, lon_deg):
    """Compass direction of a body from a place, radians, 0 = north, pi/2 = east."""
    la, lo = lat_deg * RAD, lon_deg * RAD
    east = (-math.sin(lo), math.cos(lo), 0.0)
    north = (-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la))
    e = sum(a * b for a, b in zip(body_vec, east))
    nn = sum(a * b for a, b in zip(body_vec, north))
    return math.atan2(e, nn) % (2 * math.pi)


def utc(s):
    """'2026-11-16T15:30' (UTC) -> aware datetime."""
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc)
