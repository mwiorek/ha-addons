"""The World (temperature now), W1L: W1T's sheet coloured by the current temperature, made on the Home Assistant
machine with numpy and Pillow only.

Every two hours (W1L.live.json refresh_s) the 2 m air temperature (land) and the surface temperature (sea) of the
NOAA GFS model come from the PacIOOS ERDDAP server as OPeNDAP binary (.dods: a text header, then big-endian
float32), 0.5 degree, about 2 MB. The forecast step nearest the middle of the coming two hours is asked for.

The pictures are rebuilt only when the data changes. live_build.py ships, per theme, three renders of the sheet
with a constant colour X (C11: land and sea at X1; C21: land at X2; C12: sea at X2). The colour enters the render
linearly, so the sheet for any colour field is

    C11 + (X_land - X1) (C21 - C11) / (X2 - X1) + (X_sea - X1) (C12 - C11) / (X2 - X1)

with X worked out on the add-on's 960 x 540 grid and scaled up to 4K. Labels, borders and panels do not change
between the three renders, so the colour never touches the ink. The legend's places get the hour's values.

When the server cannot be reached the last data is kept; data more than stale_s old (or none at all) gives way
to the 1970-2000 means (W1L.climate.npz), and the legend says so. The data is kept in ATLAS_DATA (/data in the
add-on), so a restart does not fetch again.
"""
import io
import json
import math
import os
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LIVE = ("W1L",)                    # live map ids; each has <id>.live.json beside its pictures
DATA = os.environ.get("ATLAS_DATA", "/data")
RETRY_S = 20 * 60                  # after a failed fetch, try again this much later (not every push)
TIMEOUT_S = 90
CACHE = {}                         # map id -> {"key", "pics": (day, night), "info"}
STATE = {}                         # map id -> {"tried", "error", "fetched", "valid"}
FETCH = None                       # tests: a function(url) -> bytes in place of the network


def is_live(map_id):
    return map_id in LIVE


def _maps_dir():
    from . import files
    return files.builtin_dirs()[0]


def meta(map_id):
    with open(os.path.join(_maps_dir(), f"{map_id}.live.json"), encoding="utf-8") as f:
        return json.load(f)


# --- data --------------------------------------------------------------------------
def parse_dods(raw, names):
    """{name: (array, time s)} from an ERDDAP .dods answer for GRIDs named `names`, each [time][lat][lon]."""
    i = raw.index(b"\nData:\n")
    head, body = raw[:i].decode("latin-1"), memoryview(raw)[i + 7:]
    pos = 0

    def take(dt):
        nonlocal pos
        n = int(np.frombuffer(body[pos:pos + 4], ">u4")[0])
        pos += 8                                    # the count, twice
        size = n * np.dtype(dt).itemsize
        a = np.frombuffer(body[pos:pos + size], dt)
        pos += size
        return a
    out = {}
    for name in names:
        dims = head.split(f" {name}[", 1)[1].split(";", 1)[0]
        shape = [int(d.split("=")[1].strip().rstrip("]")) for d in dims.split("[")]
        a = take(">f4").reshape(shape[-2:])
        t = take(">f8")
        take(">f8")
        take(">f8")
        out[name] = (a.astype(np.float32), float(t[0]))
    return out


def _url(m, when):
    s = m["source"]
    t = time.strftime("%Y-%m-%dT%H:00:00Z", time.gmtime(when))
    (la0, la1), (lo0, lo1) = s["lat"], s["lon"]
    q = ",".join(f"{v}%5B({t})%5D%5B({la0:g}):1:({la1:g})%5D%5B({lo0:g}):1:({lo1:g})%5D" for v in (s["land"], s["sea"]))
    return f"{s['url']}?{q}"


def _get(url):
    if FETCH is not None:
        return FETCH(url)
    req = urllib.request.Request(url, headers={"User-Agent": "atlas-frame"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read()


def fetch(map_id, now):
    """(land, sea) in deg C on the source grid and the data's valid time, from the network."""
    m = meta(map_id)
    s = m["source"]
    got = parse_dods(_get(_url(m, now + m["refresh_s"] / 2)), (s["land"], s["sea"]))
    (land, t), (sea, _) = got[s["land"]], got[s["sea"]]
    if list(land.shape) != s["grid"] or list(sea.shape) != s["grid"]:
        raise ValueError(f"grid {land.shape}, not {s['grid']}")
    k = 273.15 if s.get("units") == "K" else 0.0
    land, sea = land - k, sea - k
    for a in (land, sea):                           # fill values (land in the sea field) and holes: the nearest good
        a[~np.isfinite(a) | (a < -100) | (a > 100)] = np.nan
    return land, sea, t


def _store_path(map_id):
    return os.path.join(DATA, "live", f"{map_id}.npz")


def field(map_id, now=None):
    """(land, sea, info) to colour by: the stored live data, fetched again once it is refresh_s old; the climate
    means when there is none or it is older than stale_s. info: {"source": "live"|"climate", "valid", "note"}."""
    now = time.time() if now is None else now
    m = meta(map_id)
    st = STATE.setdefault(map_id, {"tried": 0.0, "error": None, "fetched": 0.0, "valid": None})
    path = _store_path(map_id)
    if st["valid"] is None and os.path.exists(path):         # after a restart: what was fetched before
        try:
            z = np.load(path)
            st.update(fetched=float(z["fetched"]), valid=float(z["valid"]))
        except Exception as e:
            st["error"] = f"stored data: {e.__class__.__name__}"
    due = now - st["fetched"] >= m["refresh_s"] and now - st["tried"] >= RETRY_S
    if due:
        st["tried"] = now
        try:
            land, sea, valid = fetch(map_id, now)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            np.savez(path, land=land, sea=sea, valid=valid, fetched=now)
            st.update(fetched=now, valid=valid, error=None)
            print(f"live {map_id}: GFS for {time.strftime('%Y-%m-%d %H:%MZ', time.gmtime(valid))}", flush=True)
        except Exception as e:
            st["error"] = f"{e.__class__.__name__}: {e}"[:200]
            print(f"live {map_id}: fetch failed, {st['error']}", flush=True)
    if st["valid"] is not None and abs(now - st["valid"]) <= m["stale_s"] and os.path.exists(path):
        z = np.load(path)
        return z["land"], z["sea"], {"source": "live", "valid": st["valid"], "note": st["error"]}
    z = np.load(os.path.join(_maps_dir(), f"{map_id}.climate.npz"))
    return (z["land"].astype(np.float32), z["sea"].astype(np.float32),
            {"source": "climate", "valid": None, "note": st["error"] or "no live data yet"})


def _fill(a):
    """NaNs replaced by the mean of their good neighbours, repeatedly (a few cells at most: fill values, poles)."""
    a = a.copy()
    for _ in range(50):
        bad = ~np.isfinite(a)
        if not bad.any():
            break
        p = np.pad(np.where(bad, 0, a), 1, mode="edge")
        c = np.pad((~bad).astype(np.float32), 1, mode="edge")
        sums = sum(np.roll(np.roll(p, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))[1:-1, 1:-1]
        cnt = sum(np.roll(np.roll(c, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))[1:-1, 1:-1]
        a = np.where(bad & (cnt > 0), sums / np.maximum(cnt, 1), a)
    return np.nan_to_num(a)


def sample(g, lon, lat):
    """Bilinear value of a 0.5 deg grid (lat 90..-90, lon 0..359.5) at lon/lat degrees (arrays)."""
    ny, nx = g.shape
    fy = np.clip((90 - lat) / 180 * (ny - 1), 0, ny - 1)
    fx = np.mod(lon, 360) / 360 * nx
    y0 = np.floor(fy).astype(int)
    x0 = np.floor(fx).astype(int)
    y1 = np.minimum(y0 + 1, ny - 1)
    x1 = (x0 + 1) % nx
    ty, tx = fy - y0, fx - x0
    x0 %= nx
    return ((g[y0, x0] * (1 - tx) + g[y0, x1] * tx) * (1 - ty) + (g[y1, x0] * (1 - tx) + g[y1, x1] * tx) * ty)


def ramp(v, stops):
    xs = np.array([s[0] for s in stops], np.float32)
    cs = np.array([s[1] for s in stops], np.float32)
    return np.stack([np.interp(v, xs, cs[:, i]) for i in range(3)], -1)


# --- pictures ----------------------------------------------------------------------
def colour_x(m, theme, temp):
    """The X the sheet was calibrated in, per channel, for temperatures `temp`: the day tint factor (relative to
    paper_ref) or the night ramp colour."""
    c = ramp(temp, m["stops"][theme])
    return c / np.array(m["paper_ref"], np.float32) if theme == "day" else c


def rebuild(c11, c21, c12, x1, x2, xl, xs, rows=270):
    """The sheet for colour fields xl, xs (H x W x 3, float32), in strips of `rows`."""
    out = np.empty(c11.shape, np.uint8)
    d = 1.0 / (x2 - x1)
    for y in range(0, c11.shape[0], rows):
        sl = slice(y, y + rows)
        b = c11[sl].astype(np.float32)
        v = b + (xl[sl] - x1) * (c21[sl] - b) * d + (xs[sl] - x1) * (c12[sl] - b) * d
        out[sl] = np.clip(v + 0.5, 0, 255)
    return out


def _upscale(a, size):
    """(gh, gw, 3) -> (H, W, 3) float32, bilinear, one channel at a time."""
    return np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(a[..., i], np.float32), "F")
                                .resize(size, Image.BILINEAR)) for i in range(3)], -1)


def _deg(v):
    return f"{v:.0f}°".replace("-", "–")       # IM Fell has no minus sign


def draw_legend(img, g, places, stamp, fonts_dir):
    """The live places over the legend's bar (as w1_panels.legend_panel lays them) and the time stamp."""
    pic = Image.fromarray(img)
    d = ImageDraw.Draw(pic)
    ink, paper = tuple(g["ink"]), tuple(g["paper"])
    fp = ImageFont.truetype(os.path.join(fonts_dir, g["place_font"]), max(8, int(round(g["place_px"]))))
    fs = ImageFont.truetype(os.path.join(fonts_dir, g["place_font"]), max(8, int(round(g["stamp_px"]))))
    s = g["place_px"] / 36.0
    lo, hi, x0, x1, by, bh = g["lo"], g["hi"], g["x0"], g["x1"], g["by"], g["bh"]
    marks = sorted((x0 + (x1 - x0) * (min(max(v, lo), hi) - lo) / (hi - lo), f"{name} {_deg(v)}") for name, v in places)
    row_end = [-1e9, -1e9]
    for x, text in marks:
        l, t, r, b = d.textbbox((0, 0), text, font=fp)
        tw, th = r - l, b - t
        tx = min(max(x - tw / 2, x0 - g["edge"]), x1 + g["edge"] - tw)
        row = 0 if tx > row_end[0] + g["sep"] else 1
        row_end[row] = tx + tw
        ty = by - g["gap"] - g["row_h"] * (row + 1)
        d.text((tx - l, ty - t), text, font=fp, fill=ink)
        d.line([(x, ty + th + 4 * s), (x, by + bh * 0.5)], fill=ink, width=g["line"])
        r_ = g["dot"]
        d.ellipse([x - r_, by + bh * 0.5 - r_, x + r_, by + bh * 0.5 + r_], fill=ink, outline=paper, width=g["line"])
    bx0, by0, bx1, by1 = g["box"]
    l, t, r, b = d.textbbox((0, 0), stamp, font=fs)
    d.text((bx1 - g["stamp_pad"][0] - (r - l) - l, by1 - g["stamp_pad"][1] - (b - t) - t), stamp, font=fs, fill=ink)
    return np.asarray(pic)


def _stamp(info, m):
    if info["source"] == "live":
        return "GFS, " + time.strftime("%d %b %H:%M UTC", time.gmtime(info["valid"])).lstrip("0")
    return "No live data: the 1970 to 2000 average"


def pictures(map_id, grid, load, now=None):
    """(day, night) 4K RGB arrays of the live map, rebuilt only when the data changes. grid: render.Grid of the
    map; load(name): a picture as an array (render._load_map)."""
    from .layers import FONTS
    land, sea, info = field(map_id, now)
    key = (info["source"], info["valid"])
    hit = CACHE.get(map_id)
    if hit and hit["key"] == key:
        return hit["pics"]
    m = meta(map_id)
    t0 = time.time()
    land, sea = _fill(land), _fill(sea)
    v = grid.v                                           # 3 x gh x gw unit vectors
    lat = np.degrees(np.arcsin(np.clip(v[2], -1, 1)))
    lon = np.degrees(np.arctan2(v[1], v[0]))
    tl, ts = sample(land, lon, lat), sample(sea, lon, lat)
    places = [(name, float(sample(land if kind == "land" else sea, np.array([plon]), np.array([plat]))[0]))
              for name, plon, plat, kind in m["places"]]
    stamp = _stamp(info, m)
    pics = []
    for theme, stem in (("day", map_id), ("night", map_id + "N")):
        c11 = load(f"{stem}_4k")
        size = (c11.shape[1], c11.shape[0])
        x1, x2 = m["x"][theme]
        xl = _upscale(colour_x(m, theme, tl), size)
        xs = _upscale(colour_x(m, theme, ts), size)
        img = rebuild(c11, load(f"{stem}_land_4k"), load(f"{stem}_sea_4k"), x1, x2, xl, xs)
        pics.append(draw_legend(img, m["legend"][theme], places, stamp, FONTS))
    CACHE[map_id] = {"key": key, "pics": tuple(pics), "info": dict(info, stamp=stamp, seconds=round(time.time() - t0, 2))}
    print(f"live {map_id}: pictures rebuilt from {info['source']} data in {time.time() - t0:.1f}s", flush=True)
    return CACHE[map_id]["pics"]


def status(map_id):
    """For the sensor: where the colours came from, and when."""
    c, st = CACHE.get(map_id, {}), STATE.get(map_id, {})
    return {"source": (c.get("info") or {}).get("source"), "stamp": (c.get("info") or {}).get("stamp"),
            "fetched": st.get("fetched") or None, "error": st.get("error")}
