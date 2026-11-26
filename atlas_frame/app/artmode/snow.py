"""The snow and ice of the Northern Hemisphere, as NOAA's Interactive Multisensor Snow and Ice Mapping System (IMS)
charts it every day: numpy only, so the add-on (artmode/live.py) and the map renderer (snowlayer.py) share it.

The 4 km chart (NSIDC G02156, about 450 KB gzipped, one a day, ready by about 14 UTC the day after) is a 6144 x 6144
grid of classes on a polar stereographic projection (WGS 84, true scale at 60 N, 80 W pointing down, 4000 m cells,
the pole in the middle):

    0 outside the hemisphere   1 open water   2 land without snow   3 sea or lake ice   4 snow-covered land

Coverage at a point is a fraction, not a class: the share of the land cells round it that carry snow, and of the
water cells that carry ice, each read bilinearly. Where the map's coast and the chart's disagree (a map land pixel
whose four chart cells are all water) the same shares are read from the chart averaged over 8 x 8 cells (32 km).
"""
import gzip
import math
import time

import numpy as np

N = 6144
CELL = 4000.0
HALF = N * CELL / 2                 # 12 288 km: the grid's corner, from the pole
A_WGS = 6378137.0
E_WGS = math.sqrt(1 - (6356752.314245 / A_WGS) ** 2)
LAT_TS, LON_0 = 60.0, -80.0
URL = "https://noaadata.apps.nsidc.org/NOAA/G02156/4km/{y}/ims{y}{doy:03d}_00UTC_4km_v1.3.asc.gz"
CREDIT = "NOAA IMS via NSIDC"
COARSE = 8                          # the fallback grid: 8 x 8 cells
AREA_KM2 = (CELL / 1000) ** 2


def url(day):
    """The chart of a day (a time.struct_time or seconds since the epoch, UTC)."""
    t = time.gmtime(day) if isinstance(day, (int, float)) else day
    return URL.format(y=t.tm_year, doy=t.tm_yday)


def parse(raw):
    """The class grid (uint8, N x N, row 0 the chart's top: the side 100 E faces) from the gzipped or plain ASCII
    chart: a header, then N rows of N digits, the first row the bottom."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    rows = [r for r in raw.replace(b"\r", b"").split(b"\n") if len(r) == N]
    if len(rows) != N:
        raise ValueError(f"IMS chart: {len(rows)} rows of {N}, not {N}")
    a = np.frombuffer(b"".join(rows), np.uint8).reshape(N, N) - 48
    if a.max() > 4:
        raise ValueError("IMS chart: a class over 4")
    return np.ascontiguousarray(a[::-1])


def _t(phi):
    s = np.sin(phi)
    return np.tan(np.pi / 4 - phi / 2) / ((1 - E_WGS * s) / (1 + E_WGS * s)) ** (E_WGS / 2)


def colrow(lon, lat):
    """Fractional (col, row) on the chart of lon/lat degrees (arrays); cell centres at whole numbers. The southern
    hemisphere comes out far off the grid (or as inf at the south pole): read as nothing."""
    phi_c = math.radians(LAT_TS)
    mc = math.cos(phi_c) / math.sqrt(1 - (E_WGS * math.sin(phi_c)) ** 2)
    tc = float(_t(np.float64(phi_c)))
    phi = np.radians(np.clip(np.asarray(lat, np.float64), -89.9, 90.0))
    lam = np.radians(np.asarray(lon, np.float64) - LON_0)
    rho = A_WGS * mc * _t(phi) / tc
    x, y = rho * np.sin(lam), -rho * np.cos(lam)
    return (x + HALF) / CELL - 0.5, (HALF - y) / CELL - 0.5


def _corners(n, c, r):
    """Bilinear corners and weights for fractional (c, r) on an n x n grid: (ok, r0, c0, [w00, w01, w10, w11])."""
    ok = (c >= 0) & (r >= 0) & (c <= n - 1) & (r <= n - 1)
    c = np.where(ok, c, 0)
    r = np.where(ok, r, 0)
    c0 = np.minimum(np.floor(c).astype(np.int32), n - 2)
    r0 = np.minimum(np.floor(r).astype(np.int32), n - 2)
    tc, tr = (c - c0).astype(np.float32), (r - r0).astype(np.float32)
    return ok, r0, c0, ((1 - tc) * (1 - tr), tc * (1 - tr), (1 - tc) * tr, tc * tr)


PARTS = {"snow": (4,), "land": (2, 4), "ice": (3,), "water": (1, 3)}


class Chart:
    """One day's chart, ready to be read at any lon/lat. Only the class grid is kept (38 MB) and a coarse share per
    part (8 x 8 cells); a point's shares are read from the classes at its four corners."""

    def __init__(self, cls):
        self.cls = cls
        k = COARSE
        self.coarse = {}
        for name, ks in PARTS.items():
            m = np.isin(cls, ks)
            self.coarse[name] = m.reshape(N // k, k, N // k, k).mean((1, 3), dtype=np.float32)
            del m

    def _read(self, c, r):
        """{part: bilinear share} at fractional cells, from the fine classes and from the coarse grid."""
        ok, r0, c0, w = _corners(N, c, r)
        fine = {n: np.zeros(c.shape, np.float32) for n in PARTS}
        for (dr, dc), wt in zip(((0, 0), (0, 1), (1, 0), (1, 1)), w):
            k = self.cls[r0 + dr, c0 + dc]
            for n, ks in PARTS.items():
                fine[n] += wt * np.isin(k, ks)
        kk = COARSE
        cc, rr = (c + 0.5) / kk - 0.5, (r + 0.5) / kk - 0.5
        okc, r0c, c0c, wc = _corners(N // kk, cc, rr)
        coarse = {}
        for n in PARTS:
            g = self.coarse[n]
            coarse[n] = np.where(okc, sum(wt * g[r0c + dr, c0c + dc] for (dr, dc), wt in
                                          zip(((0, 0), (0, 1), (1, 0), (1, 1)), wc)), 0).astype(np.float32)
            fine[n] = np.where(ok, fine[n], 0)
        return fine, coarse

    @staticmethod
    def _share(fine, coarse, part, whole):
        p, w, pc, wc = fine[part], fine[whole], coarse[part], coarse[whole]
        return np.where(w > 0.05, p / np.maximum(w, 1e-6),
                        np.where(wc > 0.01, pc / np.maximum(wc, 1e-6), 0)).astype(np.float32)

    def cover(self, lon, lat):
        """(snow, ice): the snow share of the land and the ice share of the water at lon/lat (arrays), 0..1."""
        return self.cover_at(*colrow(lon, lat))

    def cover_at(self, c, r):
        """(snow, ice) at fractional chart cells (colrow's output)."""
        c, r = np.asarray(c, np.float64), np.asarray(r, np.float64)
        fine, coarse = self._read(c, r)
        return self._share(fine, coarse, "snow", "land"), self._share(fine, coarse, "ice", "water")

    def areas(self):
        """(snow km2, ice km2, land km2: snowed or not) of the whole chart, each cell weighted by its true area (the
        projection's scale)."""
        rr, cc = np.mgrid[0:N:16, 0:N:16]
        x, y = (cc + 8 - N / 2) * CELL, (N / 2 - rr - 8) * CELL
        rho = np.hypot(x, y)
        phi_c = math.radians(LAT_TS)
        mc = math.cos(phi_c) / math.sqrt(1 - (E_WGS * math.sin(phi_c)) ** 2)
        tc = float(_t(np.float64(phi_c)))
        t = rho * tc / (A_WGS * mc)
        phi = np.pi / 2 - 2 * np.arctan(t)                      # first guess; a few fixed-point steps for the ellipsoid
        for _ in range(5):
            s = np.sin(phi)
            phi = np.pi / 2 - 2 * np.arctan(t * ((1 - E_WGS * s) / (1 + E_WGS * s)) ** (E_WGS / 2))
        m = np.cos(phi) / np.sqrt(1 - (E_WGS * np.sin(phi)) ** 2)
        k = rho / (A_WGS * m)                                   # the scale factor (no block centre is the pole)
        w = AREA_KM2 / np.maximum(k, 1e-6) ** 2                # true km2 of one cell in each 16 x 16 block
        blocks = lambda m_: m_.reshape(N // 16, 16, N // 16, 16).sum((1, 3))
        snow, ice = float((blocks(self.cls == 4) * w).sum()), float((blocks(self.cls == 3) * w).sum())
        return snow, ice, snow + float((blocks(self.cls == 2) * w).sum())

