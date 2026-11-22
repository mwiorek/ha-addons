"""One Art Mode picture: a 4K map lit by the sun of a given moment, with the moon, as JPEG bytes.
Needs only numpy and Pillow, the day and night 4K JPEGs, and the map's grid (artmode/grids.py).

    python -m artmode.render R1 2026-11-16T15:30 [--mode follow|home|day|night] [-o out.jpg] [--time]

Modes: follow (each spot lit by its own sun), home (the whole map lit by the sun at home: Home
Assistant's location in the add-on, Stockholm by default), day and night (held). The moon is drawn where it is overhead, with its lit side towards the sun, and its
ground track for 12 hours either side; on maps it is not over, it stands in the sky along the top
as seen from the centre of that map, while it is up there.
"""
import argparse
import io
import math
import os
import time

import numpy as np
from PIL import Image

from . import ephem, files

HERE = os.path.dirname(os.path.abspath(__file__))
MAPS = os.environ.get("ATLAS_MAPS", os.path.join(os.path.dirname(HERE), "renders"))
GRIDS = os.environ.get("ATLAS_GRIDS", os.path.join(HERE, "grids"))
W, H = 3840, 2160
HOME = (59.33, 18.07)                     # Stockholm, as daynight.HOME
DAY_EL, NIGHT_EL = 4.0, -6.0              # full day above +4 deg of sun, full night below -6 (end of civil twilight): the mid-fade sits on the real sunrise/sunset (-0.83)
LO, SPAN = math.sin(math.radians(NIGHT_EL)), math.sin(math.radians(DAY_EL)) - math.sin(math.radians(NIGHT_EL))
MOON_R = 30                               # 4K px
INK = np.array([239, 230, 207], np.float32)       # lit moon
DARK = np.array([29, 39, 64], np.float32)         # unlit moon, the night map's sea
RIM = np.array([226, 214, 186], np.float32)       # the night map's label ink: rim and track at night
BROWN = np.array([84, 60, 42], np.float32)        # dark ink on the day map's paper: rim and track by day
CHUNK = 270                               # rows blended at a time: keeps memory near 30 MB


def _smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _load_grid(map_id):
    """The map's grid: from the first source with a good one (artmode/files.py)."""
    for src, path in files.candidates("grids", f"{map_id}.npz", GRIDS):
        if not os.path.exists(path):
            continue
        try:
            z = np.load(path)
            if z["v"].shape[0] != 3 or z["ok"].shape != z["v"].shape[1:]:
                raise ValueError("unexpected shape")
            files.SOURCES[f"{map_id} grid"] = src
            return z
        except Exception as e:
            files.PROBLEMS.append(f"{map_id} grid from {src}: {e.__class__.__name__}")
    raise FileNotFoundError(f"no grid for {map_id}")


def _load_map(name):
    """A 4K map picture ("R1_4k") as an RGB array: from the first source (artmode/files.py) with a
    complete one of the right size, its lossless .png before its .jpg."""
    for src, path in files.picture_candidates(name, MAPS):
        if not os.path.exists(path):
            continue
        try:
            im = Image.open(path)
            im.load()
            if im.size != (W, H):
                raise ValueError(f"{im.size[0]} x {im.size[1]}, not {W} x {H}")
            files.SOURCES[name] = src
            files.KINDS[name] = os.path.splitext(path)[1][1:]
            return np.asarray(im.convert("RGB"))
        except Exception as e:
            files.PROBLEMS.append(f"{os.path.basename(path)} from {src}: {e.__class__.__name__}: {e}")
    raise FileNotFoundError(f"no picture {name}")


class Grid:
    def __init__(self, map_id):
        z = _load_grid(map_id)
        self.v = z["v"].astype(np.float32) / 32767       # 3 x GH x GW
        self.ok = z["ok"]
        self.gh, self.gw = self.ok.shape
        # angle between neighbouring cells across the middle: how close a point must be to count as on the map
        c = self.v[:, self.gh // 2, self.gw // 2 - 1:self.gw // 2 + 1]
        self.cell = math.acos(min(1.0, float((c[:, 0] * c[:, 1]).sum())))
        m = self.v[:, self.gh // 2, self.gw // 2]                 # the map's centre: where its sky is seen from
        self.centre = (math.degrees(math.asin(max(-1.0, min(1.0, float(m[2]))))),
                       math.degrees(math.atan2(float(m[1]), float(m[0]))))

    def _spacing(self, j, i):
        """Angle (radians) between this grid cell and its farthest direct neighbour: how far apart
        the samples are here. It varies a lot across a map (the World's cells are much wider at 60
        degrees than at the equator), so the on-map test uses it locally."""
        c, worst = self.v[:, j, i], 0.0
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            jj, ii = j + dj, i + di
            if 0 <= jj < self.gh and 0 <= ii < self.gw:
                worst = max(worst, math.acos(min(1.0, float((c * self.v[:, jj, ii]).sum()))))
        return worst

    def weight(self, s):
        """Day weight 0..1 on the grid for the sun direction s."""
        return _smooth((self.v[0] * s[0] + self.v[1] * s[1] + self.v[2] * s[2] - LO) / SPAN)

    def locate(self, p):
        """4K pixel (x, y) of the globe point p (unit vector), or None if it is not on this map."""
        d = self.v[0] * p[0] + self.v[1] * p[1] + self.v[2] * p[2]
        d = np.where(self.ok, d, -2)
        j, i = np.unravel_index(int(np.argmax(d)), d.shape)
        if d[j, i] < math.cos(self._spacing(j, i) * 1.5):
            return None
        return (i + 0.5) * W / self.gw, (j + 0.5) * H / self.gh


def _lit(day, night, w):
    """night + (day - night) * w, with w upscaled from the grid to 4K, in strips."""
    wimg = Image.fromarray(w.astype(np.float32), "F").resize((W, H), Image.BICUBIC)
    wbig = np.asarray(wimg)
    out = np.empty((H, W, 3), np.uint8)
    for y in range(0, H, CHUNK):
        n = night[y:y + CHUNK].astype(np.float32)
        out[y:y + CHUNK] = np.clip(n + (day[y:y + CHUNK] - n) * np.clip(wbig[y:y + CHUNK, :, None], 0, 1) + 0.5, 0, 255)
    return out


def _ink(day):
    """Rim and track colour for a spot that is `day` (0..1) lit: pale ink at night, brown by day."""
    return RIM * (1 - day) + BROWN * day


def _disc(img, x, y, k, angle, day):
    """Draw the moon at 4K pixel (x, y) as a phase symbol: k = lit fraction, angle = screen direction
    of the bright limb (radians, y down), day = how lit the map is there (sets the rim's ink).
    Supersampled 4x for clean edges."""
    r, ss = MOON_R, 4
    half = r + 3
    x0, y0 = int(round(x)) - half, int(round(y)) - half
    if x0 < 0 or y0 < 0 or x0 + 2 * half >= W or y0 + 2 * half >= H:
        return
    n = 2 * half * ss
    g = (np.arange(n) + 0.5) / ss - half + (int(round(x)) - x)
    gx, gy = np.meshgrid(g, (np.arange(n) + 0.5) / ss - half + (int(round(y)) - y))
    ca, sa = math.cos(angle), math.sin(angle)
    u, v = gx * ca + gy * sa, -gx * sa + gy * ca          # u points at the sun
    rr = u * u + v * v
    inside = rr <= r * r
    lit = inside & (u >= (1 - 2 * k) * np.sqrt(np.maximum(r * r - v * v, 0)))
    rim = (rr <= (r + 1.5) ** 2) & ~inside

    def down(m):
        return m.reshape(2 * half, ss, 2 * half, ss).mean((1, 3))[..., None].astype(np.float32)

    a_in, a_lit, a_rim = down(inside), down(lit), down(rim)
    patch = img[y0:y0 + 2 * half, x0:x0 + 2 * half].astype(np.float32)
    col = DARK * (a_in - a_lit) + INK * a_lit                 # colour where the disc is
    patch = patch * (1 - a_in) + col
    rim_a = 0.6 + 0.3 * day                                   # the rim carries the shape on light paper
    patch = patch * (1 - rim_a * a_rim) + rim_a * _ink(day) * a_rim
    img[y0:y0 + 2 * half, x0:x0 + 2 * half] = np.clip(patch + 0.5, 0, 255).astype(np.uint8)


def _dot(img, x, y, alpha, color, r=2.2):
    xi, yi = int(x), int(y)
    if not (4 <= xi < W - 4 and 4 <= yi < H - 4):
        return
    gy, gx = np.mgrid[yi - 3:yi + 4, xi - 3:xi + 4]
    a = (alpha * np.clip(r + 0.5 - np.hypot(gx + 0.5 - x, gy + 0.5 - y), 0, 1))[..., None]
    img[yi - 3:yi + 4, xi - 3:xi + 4] = (img[yi - 3:yi + 4, xi - 3:xi + 4] * (1 - a) + color * a).astype(np.uint8)


def _toward(grid, p, q, step=0.01):
    """Screen direction (radians, y down) from globe point p towards globe point q."""
    a = grid.locate(p)
    pq = [b - (sum(x * y for x, y in zip(p, q))) * a_ for a_, b in zip(p, q)]    # q minus its part along p
    norm = math.sqrt(sum(c * c for c in pq)) or 1.0
    p2 = [a_ * math.cos(step) + c / norm * math.sin(step) for a_, c in zip(p, pq)]
    b = grid.locate(p2)
    if a is None or b is None or (a == b):
        return 0.0
    return math.atan2(b[1] - a[1], b[0] - a[0])


_BASE = []


def _moon_base():
    """The engraved moon (assets/moon.png, or ATLAS_MOON), loaded once; None if it is missing."""
    if not _BASE:
        from . import moonart
        try:
            _BASE.append(moonart.load_base())
        except (OSError, ValueError):
            _BASE.append(None)
    return _BASE[0]


def _paste_moon(pic, t, k, at, day):
    """The engraved moon at its true size and phase: dimmed (earthshine) on the night side, cut out
    and re-toned blue-white on the day side, cross-faded through twilight by the day weight under it."""
    from . import moonart
    x, y, angle = at
    base, d = _moon_base(), moonart.diameter(t)
    layers_ = []
    if day < 1:
        layers_.append((moonart.sprite(base, d, k, angle, "dimmed"), 1 - day))
    if day > 0:
        layers_.append((moonart.day_moon(base, d, k, angle, "cool"), day))
    for sp, weight in layers_:
        if weight < 1:
            a = sp.split()[3].point(lambda v, w=weight: int(v * w))
            sp.putalpha(a)
        pic.paste(sp, (int(round(x - sp.width / 2)), int(round(y - sp.height / 2))), sp)


class Context:
    """What a data layer gets to draw with (artmode/layers.py)."""

    def __init__(self, map_id, t, grid, w, data):
        self.map_id, self.t, self.grid, self.w, self.data = map_id, t, grid, w, data

    def dayness(self, x, y):
        """How lit the map is at 4K pixel (x, y), 0 night to 1 day."""
        g = self.grid
        return float(self.w[min(g.gh - 1, max(0, int(y * g.gh / H))), min(g.gw - 1, max(0, int(x * g.gw / W)))])

    def ink(self, x, y):
        """Ink colour (r, g, b) that reads on the map at (x, y): brown on day paper, pale at night."""
        return tuple(int(c) for c in _ink(self.dayness(x, y)))


LAYER_ERRORS = []                          # filled by the last render(): layers that failed and were left out


def encode(pic, kind="jpg", quality=95):
    """The picture as file bytes: "png" lossless (fast setting: the files go over the LAN, not the
    internet), or "jpg" at `quality` with full-resolution colour (4:4:4), which keeps thin coloured
    lettering and borders sharp."""
    buf = io.BytesIO()
    if kind == "png":
        pic.save(buf, "PNG", compress_level=1)
    else:
        pic.save(buf, "JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


def render(map_id, t, mode="follow", quality=95, **kw):
    """JPEG bytes of render_image(...)."""
    return encode(render_image(map_id, t, mode, **kw), "jpg", quality)


def render_image(map_id, t, mode="follow", home=HOME, layers=(), data=None):
    """The picture (PIL image) of map_id at time t (aware datetime). home = (lat, lon) for the
    home-light mode; layers draw data on top (artmode/layers.py), each given a Context with `data`."""
    LAYER_ERRORS.clear()
    grid = Grid(map_id)
    s = ephem.sun_vec(t)
    if mode == "follow":
        w = grid.weight(s)
    else:
        if mode == "home":
            wh = float(_smooth((math.sin(ephem.elevation(s, ephem.place_vec(*home))) - LO) / SPAN))
        else:
            wh = 1.0 if mode == "day" else 0.0
        w = np.full((grid.gh, grid.gw), wh, np.float32)

    from . import live
    live_pics = live.pictures(map_id, grid, _load_map) if live.is_live(map_id) else None

    def load(f):                        # a live map's two sheets are coloured by the hour's data (artmode/live.py)
        return live_pics[f.endswith("N_4k")] if live_pics is not None else _load_map(f)
    if w.min() >= 1:
        img = load(f"{map_id}_4k").copy()
    elif w.max() <= 0:
        img = load(f"{map_id}N_4k").copy()
    else:
        img = _lit(load(f"{map_id}_4k"), load(f"{map_id}N_4k"), w)

    m = ephem.moon_vec(t)
    k = ephem.lit_fraction(t)
    here = grid.locate(m)
    moon_at = None                      # (x, y, bright-limb angle) once placed

    def dayness(x, y):
        return float(w[min(grid.gh - 1, int(y * grid.gh / H)), min(grid.gw - 1, int(x * grid.gw / W))])

    if here:
        # ground track: where the moon is overhead 12 h before and after, a dot every 20 minutes
        for minutes in range(-720, 721, 20):
            if abs(minutes) < 60:
                continue
            q = grid.locate(ephem.moon_vec(t.fromtimestamp(t.timestamp() + minutes * 60, t.tzinfo)))
            if q:
                _dot(img, q[0], q[1], 0.55, _ink(dayness(*q)))
        moon_at = (here[0], here[1], _toward(grid, m, s))
    else:
        # in the sky along the top, as seen from the map's centre: east on the left, west on the right
        here_ = grid.centre
        seen = ephem.place_vec(*here_)
        alt = ephem.elevation(m, seen)
        if alt > 0:
            az = math.degrees(ephem.azimuth(m, *here_))
            x = W * (0.10 + 0.80 * min(1, max(0, (az - 45) / 270)))
            y = H * (0.20 - 0.12 * min(1, alt / math.radians(60)))
            # the bright limb faces the sun's direction in the same sky
            saz = ephem.azimuth(s, *here_)
            salt = ephem.elevation(s, seen)
            sx = W * (0.10 + 0.80 * min(1.5, max(-0.5, (math.degrees(saz) - 45) / 270)))
            sy = H * (0.20 - 0.12 * salt / math.radians(60))
            moon_at = (x, y, math.atan2(sy - y, sx - x))

    if moon_at and _moon_base() is None:     # no moon picture: the inked phase symbol
        _disc(img, moon_at[0], moon_at[1], k, moon_at[2], dayness(moon_at[0], moon_at[1]))
    pic = Image.fromarray(img)
    if moon_at and _moon_base() is not None:
        _paste_moon(pic, t, k, moon_at, dayness(moon_at[0], moon_at[1]))
    if layers:
        ctx = Context(map_id, t, grid, w, data or {})
        for layer in layers:
            try:
                layer.draw(pic, ctx)
            except Exception as e:      # a broken layer is left out; the map still goes up
                LAYER_ERRORS.append(f"{getattr(layer, 'name', 'layer')} left out: {e.__class__.__name__}: {e}")
    return pic


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("map")
    a.add_argument("when", help="UTC, e.g. 2026-11-16T15:30")
    a.add_argument("--mode", default="follow", choices=["follow", "home", "day", "night"])
    a.add_argument("-o", "--out")
    a.add_argument("--time", action="store_true", help="print how long it took")
    o = a.parse_args()
    t0 = time.perf_counter()
    data = render(o.map, ephem.utc(o.when), o.mode)
    dt = time.perf_counter() - t0
    if o.out:
        open(o.out, "wb").write(data)
    print(f"{o.map} {o.when} {o.mode}: {len(data) / 1e6:.1f} MB" + (f", {dt:.2f} s" if o.time else ""))
