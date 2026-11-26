"""The live maps, made on the Home Assistant machine with numpy and Pillow only: the temperature maps, such as The
World (temperature now), W1L, a temperature sheet coloured by the current temperature; and the snow maps, The World
(snow and ice now), W1S, and Europe (snow and ice now), R1S, the political sheet with the day's snow and ice laid
over it from NOAA's IMS chart (artmode/snow.py; one chart a day, about 450 KB, looked for every three hours, shared
by every snow map; no chart, or none for a week: no snow, and the key says so). See snow_pictures.

A map is live when its <id>.live.json is found beside its pictures (the maps folder, my maps or the built-in maps,
artmode/files.py). All live maps colour from one fetch: the data is stored per source, not per map.

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
import urllib.error
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DATA = os.environ.get("ATLAS_DATA", "/data")
RETRY_S = 20 * 60                  # after a failed fetch, try again this much later (not every push)
TIMEOUT_S = 90
CACHE = {}                         # map id -> {"key", "pics": (day, night), "info"}
STATE = {}                         # source key -> {"tried", "error", "fetched", "valid"}
SOURCE_OF = {}                     # map id -> its source key
FETCH = None                       # tests: a function(url) -> bytes in place of the network


def _find(name):
    """The first readable copy of a live map's side file (<id>.live.json, <id>.climate.npz) in the map sources."""
    from . import files
    for _, p in files.candidates("", name, files.builtin_dirs()[0]):
        if os.path.isfile(p):
            return p
    return None


def is_live(map_id):
    return _find(f"{map_id}.live.json") is not None


def meta(map_id):
    p = _find(f"{map_id}.live.json")
    if p is None:
        raise FileNotFoundError(f"{map_id}.live.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def is_snow(m):
    return m.get("kind") == "snow"


def source_key(m):
    """One name per data source and grid, so every live map on it shares a fetch (and its stored copy)."""
    s = m["source"]
    if is_snow(m):
        return "ims"
    return "gfs" if "ncep_global" in s["url"] else "src" + str(abs(hash((s["url"], s["land"], s["sea"]))) % 10 ** 8)


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


def _store_path(key):
    return os.path.join(DATA, "live", f"{key}.npz")


def field(map_id, now=None):
    """(land, sea, info) to colour by: the stored live data, fetched again once it is refresh_s old; the climate
    means when there is none or it is older than stale_s. info: {"source": "live"|"climate", "valid", "note"}."""
    now = time.time() if now is None else now
    m = meta(map_id)
    key = SOURCE_OF[map_id] = source_key(m)
    st = STATE.setdefault(key, {"tried": 0.0, "error": None, "fetched": 0.0, "valid": None})
    path = _store_path(key)
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
    z = np.load(_find(f"{map_id}.climate.npz"))
    return (z["land"].astype(np.float32), z["sea"].astype(np.float32),
            {"source": "climate", "valid": None, "note": st["error"] or "no live data yet"})


# --- snow (W1S, R1S): one NOAA IMS chart a day ---------------------------------------------
SNOW_BACK_DAYS = 4                 # the newest chart is looked for this many days back (it lands about 14 UTC)
SNOW_CHART = {}                    # "cls", "day": the chart held in memory (6144 x 6144 bytes, 38 MB)


def _day0(t):
    return float(int(t // 86400) * 86400)


def fetch_snow(now, have=None):
    """(classes, day start s) of the newest IMS chart newer than `have` (day start s), or None when there is none."""
    from . import snow
    for back in range(SNOW_BACK_DAYS + 1):
        day = _day0(now) - back * 86400
        if have is not None and day <= have:
            return None
        try:
            raw = _get(snow.url(day))
        except urllib.error.HTTPError as e:
            if e.code == 404:                        # not out yet: the day before
                continue
            raise
        return snow.parse(raw), day
    return None


def snow_field(map_id, now=None):
    """(chart classes or None, info) to lay the snow by: the newest chart, looked for once it is refresh_s since the
    last look; None when there is none, or the newest is older than stale_s (no snow drawn, the key says so)."""
    now = time.time() if now is None else now
    m = meta(map_id)
    key = SOURCE_OF[map_id] = source_key(m)
    st = STATE.setdefault(key, {"tried": 0.0, "error": None, "fetched": 0.0, "valid": None})
    path = _store_path(key)
    if st["valid"] is None and os.path.exists(path):         # after a restart: the chart fetched before
        try:
            with np.load(path) as z:
                st.update(fetched=float(z["fetched"]), valid=float(z["valid"]))
        except Exception as e:
            st["error"] = f"stored data: {e.__class__.__name__}"
    due = now - st["fetched"] >= m["refresh_s"] and now - st["tried"] >= RETRY_S
    if due:
        st["tried"] = now
        try:
            got = fetch_snow(now, st["valid"])
            st.update(fetched=now, error=None)
            if got is not None:
                cls, day = got
                os.makedirs(os.path.dirname(path), exist_ok=True)
                np.savez_compressed(path, cls=cls, valid=day, fetched=now)
                SNOW_CHART.update(cls=cls, day=day)
                st["valid"] = day
                print(f"live {map_id}: IMS snow chart of {time.strftime('%Y-%m-%d', time.gmtime(day))}", flush=True)
        except Exception as e:
            st["error"] = f"{e.__class__.__name__}: {e}"[:200]
            print(f"live {map_id}: snow chart fetch failed, {st['error']}", flush=True)
    if st["valid"] is not None and now - st["valid"] <= m["stale_s"]:
        if SNOW_CHART.get("day") != st["valid"] and os.path.exists(path):
            with np.load(path) as z:
                SNOW_CHART.update(cls=z["cls"], day=float(z["valid"]))
        if SNOW_CHART.get("day") == st["valid"]:
            return SNOW_CHART["cls"], {"source": "live", "valid": st["valid"], "note": st["error"]}
    return None, {"source": "none", "valid": st["valid"], "note": st["error"] or "no snow chart yet"}


def _snow_cover(cls, grid, size):
    """(snow, ice), each (H, W, 1) float32 0..1 at picture size `size` (W, H): the chart read at the map's grid,
    its cell positions put on a half-size raster first (smooth: the projection), then the cover read there and
    scaled up. South of the equator nothing (the chart is the Northern Hemisphere's)."""
    from . import snow
    v = grid.v
    lat = np.degrees(np.arcsin(np.clip(v[2], -1, 1)))
    lon = np.degrees(np.arctan2(v[1], v[0]))
    north = np.clip((lat + 1.0) / 2.0, 0, 1).astype(np.float32)      # fades out over the equator's two degrees
    c, r = snow.colrow(lon, np.maximum(lat, 0.0))
    half = (max(1, size[0] // 2), max(1, size[1] // 2))
    up = lambda a: np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").resize(half, Image.BILINEAR))
    chart = snow.Chart(cls)
    sn, ic = chart.cover_at(up(c).astype(np.float64), up(r).astype(np.float64))
    k = up(north)
    full = lambda a: np.asarray(Image.fromarray(np.ascontiguousarray(a * k, np.float32), "F").resize(size, Image.BILINEAR))[..., None]
    return full(sn), full(ic), chart


def _snow_stamp(info):
    if info["source"] == "live":
        return "IMS chart of " + time.strftime("%d %b %Y", time.gmtime(info["valid"])).lstrip("0")
    if info.get("valid"):
        return "No chart since " + time.strftime("%d %b", time.gmtime(info["valid"])).lstrip("0") + ": no snow shown"
    return "No snow chart yet: no snow shown"


def _mkm2(v):
    return f"{v / 1e6:.1f} million km²"


def draw_snow_legend(img, g, figures, stamp, fonts_dir):
    """The day's figures under the snow key's row names (w1_panels.snow_key lays them; figures: {row kind: [lines]})
    and the chart's date."""
    pic = Image.fromarray(img)
    d = ImageDraw.Draw(pic)
    ink = tuple(g["ink"])
    fv = ImageFont.truetype(os.path.join(fonts_dir, g["value_font"]), max(8, int(round(g["value_px"]))))
    fs = ImageFont.truetype(os.path.join(fonts_dir, g["place_font"]), max(8, int(round(g["stamp_px"]))))
    for row in g["rows"]:
        for i, text in enumerate(figures.get(row["kind"]) or []):
            l, t, r, b = d.textbbox((0, 0), text, font=fv)
            d.text((row["x"] - l, row["y"] + i * row.get("line", g["value_px"] * 1.3) - t), text, font=fv, fill=ink)
    bx0, by0, bx1, by1 = g["box"]
    l, t, r, b = d.textbbox((0, 0), stamp, font=fs)
    d.text((bx1 - g["stamp_pad"][0] - (r - l) - l, by1 - g["stamp_pad"][1] - (b - t) - t), stamp, font=fs, fill=ink)
    return np.asarray(pic)


def snow_pictures(map_id, grid, load, now=None):
    """(day, night) of a snow map: the political sheet with the chart's snow and ice laid over it (live_build.py's
    combined calibration: X is the cover, 0..1)."""
    from .layers import FONTS
    cls, info = snow_field(map_id, now)
    key = (info["source"], info["valid"])
    hit = CACHE.get(map_id)
    if hit and hit["key"] == key:
        return hit["pics"]
    m = meta(map_id)
    t0 = time.time()
    stamp = _snow_stamp(info)
    pics, cover, figures = [], None, {}
    for theme, stem in (("day", map_id), ("night", map_id + "N")):
        c11 = load(f"{stem}_4k")
        size = (c11.shape[1], c11.shape[0])
        if cls is None:
            img = np.ascontiguousarray(c11[..., :3])
        else:
            if cover is None:
                sn, ic, chart = _snow_cover(cls, grid, size)
                cover = (sn, ic)
                a_snow, a_ice, a_land = chart.areas()
                figures = {"snow": [_mkm2(a_snow), f"{100 * a_snow / max(a_land, 1):.0f} % of the northern land"],
                           "ice": [_mkm2(a_ice)]}
            x1, x2 = m["x"][theme]
            img = rebuild_combined(c11, load(f"{stem}_k_4k"), load(f"{map_id}_landw_4k"), x1, x2, *cover)
        pics.append(draw_snow_legend(img, m["legend"][theme], figures, stamp, FONTS))
    CACHE[map_id] = {"key": key, "pics": tuple(pics), "info": dict(info, stamp=stamp, seconds=round(time.time() - t0, 2))}
    print(f"live {map_id}: pictures rebuilt ({info['source']}) in {time.time() - t0:.1f}s", flush=True)
    return CACHE[map_id]["pics"]


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


def rebuild_combined(c11, c22, landw, x1, x2, xl, xs, rows=270):
    """The sheet from the compact calibration (live.json "format": "combined"): the base (land and sea at X1), one
    sheet with both at X2, and each pixel's land share (0..255, from the land and sea responses at build time).
    The colour a pixel takes is the land and sea fields mixed by that share; along a coast the share mixes them as
    the render does (within 2 levels of the three-sheet form)."""
    out = np.empty(c11.shape, np.uint8)
    d = 1.0 / (x2 - x1)
    for y in range(0, c11.shape[0], rows):
        sl = slice(y, y + rows)
        b = c11[sl].astype(np.float32)
        w = landw[sl, :, :1].astype(np.float32) / 255.0
        x = (xl[sl] - x1) * w + (xs[sl] - x1) * (1 - w)
        out[sl] = np.clip(b + x * (c22[sl] - b) * d + 0.5, 0, 255)
    return out


def _upscale(a, size):
    """(gh, gw, 3) -> (H, W, 3) float32, bilinear, one channel at a time."""
    return np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(a[..., i], np.float32), "F")
                                .resize(size, Image.BILINEAR)) for i in range(3)], -1)


def _deg(v):
    return f"{v:.0f}°".replace("-", "–")       # IM Fell has no minus sign


def spread(ys, gap, lo, hi):
    """Label tops for wanted tops `ys` (sorted), at least `gap` apart, kept inside [lo, hi]."""
    out = list(ys)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + gap)
    if out and out[-1] > hi:
        out[-1] = hi
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - gap)
    if out and out[0] < lo:
        out[0] = lo
        for i in range(1, len(out)):
            out[i] = max(out[i], out[i - 1] + gap)
    return out


def _upright(d, g, places, fp, s):
    """Places on an upright key (geometry orient "v"): a dot on the bar at the value, a leader out to the name on its
    right."""
    ink, paper = tuple(g["ink"]), tuple(g["paper"])
    lo, hi, x0, x1, yt, yb = g["lo"], g["hi"], g["x0"], g["x1"], g["y_top"], g["y_bot"]
    marks = sorted((yb - (yb - yt) * (min(max(v, lo), hi) - lo) / (hi - lo), f"{name} {_deg(v)}") for name, v in places)
    sizes = []
    for _, text in marks:
        l, t, r, b = d.textbbox((0, 0), text, font=fp)
        sizes.append((l, t, r - l, b - t))
    tops = spread([y - sz[3] / 2 for (y, _), sz in zip(marks, sizes)], g["row_h"], yt - g["row_h"] * 0.5, yb)
    right = g["box"][2] - 20 * s
    for (y, text), (l, t, tw, th), ty in zip(marks, sizes, tops):
        tx = min(g["label_x"], right - tw)
        d.text((tx - l, ty - t), text, font=fp, fill=ink)
        d.line([(x1, y), (x1 + 16 * s, y), (tx - 12 * s, ty + th / 2)], fill=ink, width=g["line"], joint="curve")
        cx, r_ = (x0 + x1) / 2, g["dot"]
        d.ellipse([cx - r_, y - r_, cx + r_, y + r_], fill=ink, outline=paper, width=g["line"])


def draw_legend(img, g, places, stamp, fonts_dir):
    """The live places over the legend's bar (as w1_panels.legend_panel lays them) and the time stamp."""
    pic = Image.fromarray(img)
    d = ImageDraw.Draw(pic)
    ink, paper = tuple(g["ink"]), tuple(g["paper"])
    fp = ImageFont.truetype(os.path.join(fonts_dir, g["place_font"]), max(8, int(round(g["place_px"]))))
    fs = ImageFont.truetype(os.path.join(fonts_dir, g["place_font"]), max(8, int(round(g["stamp_px"]))))
    s = g["place_px"] / 36.0
    if g.get("orient") == "v":
        _upright(d, g, places, fp, s)
        bx0, by0, bx1, by1 = g["box"]
        l, t, r, b = d.textbbox((0, 0), stamp, font=fs)
        d.text((bx1 - g["stamp_pad"][0] - (r - l) - l, by1 - g["stamp_pad"][1] - (b - t) - t), stamp, font=fs, fill=ink)
        return np.asarray(pic)
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
    if is_snow(meta(map_id)):
        return snow_pictures(map_id, grid, load, now)
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
        if m.get("format") == "combined":               # a regional map's compact calibration (live_build.py)
            img = rebuild_combined(c11, load(f"{stem}_k_4k"), load(f"{map_id}_landw_4k"), x1, x2, xl, xs)
        else:
            img = rebuild(c11, load(f"{stem}_land_4k"), load(f"{stem}_sea_4k"), x1, x2, xl, xs)
        pics.append(draw_legend(img, m["legend"][theme], places, stamp, FONTS))
    CACHE[map_id] = {"key": key, "pics": tuple(pics), "info": dict(info, stamp=stamp, seconds=round(time.time() - t0, 2))}
    print(f"live {map_id}: pictures rebuilt from {info['source']} data in {time.time() - t0:.1f}s", flush=True)
    return CACHE[map_id]["pics"]


def status(map_id):
    """For the sensor: where the colours came from, and when."""
    c, st = CACHE.get(map_id, {}), STATE.get(SOURCE_OF.get(map_id, ""), {})
    return {"source": (c.get("info") or {}).get("source"), "stamp": (c.get("info") or {}).get("stamp"),
            "fetched": st.get("fetched") or None, "error": st.get("error")}
