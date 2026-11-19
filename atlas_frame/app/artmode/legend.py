"""The home-weather legend: an engraved cartouche in a corner of the map with two small instruments,
a barometer dial with the old scale words and a compass rose with a fletched wind arrow, and the
air temperature between them. MOCK-UP (2026-11-16): sample readings, not yet wired to Home Assistant.

    python -m artmode.legend [out_folder]     # Europe with the legend by day and by night, and a
                                              # strip of the arrow from calm to storm
"""
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .layers import FONTS

SS = 2                                    # drawn at twice the size, then scaled down: clean lines

DAY = {"paper": (241, 233, 212, 247), "ink": (70, 50, 35), "faint": (150, 128, 100), "accent": (150, 48, 32)}
NIGHT = {"paper": (13, 18, 32, 236), "ink": (226, 214, 186), "faint": (120, 112, 96), "accent": (222, 182, 112)}

# the old aneroid dial, in hPa where the words stand (28 to 31 inches of mercury)
BARO_MIN, BARO_MAX = 950.0, 1050.0
BARO_WORDS = [(960, "Stormy"), (980, "Rain"), (1000, "Change"), (1020, "Fair"), (1040, "Very Dry")]
# Beaufort's scale with the names of the old wind charts; upper limits in m/s
BEAUFORT = [(0.5, "Calm"), (1.5, "Light Air"), (3.3, "Light Breeze"), (5.5, "Gentle Breeze"),
            (7.9, "Moderate Breeze"), (10.7, "Fresh Breeze"), (13.8, "Strong Breeze"),
            (17.1, "Moderate Gale"), (20.7, "Fresh Gale"), (24.4, "Strong Gale"),
            (28.4, "Whole Gale"), (32.6, "Storm"), (1e9, "Hurricane")]
POINTS = ["N", "N.b.E", "N.N.E", "N.E.b.N", "N.E", "N.E.b.E", "E.N.E", "E.b.N", "E", "E.b.S", "E.S.E",
          "S.E.b.E", "S.E", "S.E.b.S", "S.S.E", "S.b.E", "S", "S.b.W", "S.S.W", "S.W.b.S", "S.W",
          "S.W.b.W", "W.S.W", "W.b.S", "W", "W.b.N", "W.N.W", "N.W.b.W", "N.W", "N.W.b.N", "N.N.W", "N.b.W"]


def beaufort(speed):
    for force, (limit, name) in enumerate(BEAUFORT):
        if speed < limit:
            return force, name
    return 12, "Hurricane"


def point(bearing):
    """Compass point (of 16) for a bearing in degrees, written the old way: W.S.W."""
    p = POINTS[int((bearing % 360) / 11.25 + 0.5) % 32 // 2 * 2]
    return p + "." if len(p) > 1 else p


def baro_word(hpa):
    return min(BARO_WORDS, key=lambda w: abs(w[0] - hpa))[1]


def trend_word(change_3h):
    if change_3h is None:
        return None
    if change_3h <= -1.0:
        return "falling"
    if change_3h >= 1.0:
        return "rising"
    return "steady"


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _f(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), int(size * SS))


ROMAN, ITALIC, CAPS = "IMFeENrm28P.ttf", "IMFeENit28P.ttf", "IMFeENsc28P.ttf"


class Legend:
    """Draws the cartouche at (x, y), w x h in 4K px. reading: temperature (deg C), pressure (hPa),
    pressure_change_3h (hPa), wind_speed (m/s), wind_from (deg). night: dark panel and pale ink."""

    def __init__(self, reading, place, when, tz="Europe/Stockholm", w=700, h=416):
        self.r, self.place, self.when, self.tz, self.w, self.h = reading, place, when, tz, w, h

    def image(self, night):
        c = NIGHT if night else DAY
        W, H = self.w * SS, self.h * SS
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        s = SS

        # the frame: a filled panel, a heavy outer rule and a fine inner one, small corner squares
        d.rectangle([0, 0, W - 1, H - 1], fill=c["paper"])
        d.rectangle([5 * s, 5 * s, W - 1 - 5 * s, H - 1 - 5 * s], outline=c["ink"], width=3 * s)
        d.rectangle([12 * s, 12 * s, W - 1 - 12 * s, H - 1 - 12 * s], outline=c["ink"], width=1 * s)
        for cx, cy in ((12, 12), (self.w - 13, 12), (12, self.h - 13), (self.w - 13, self.h - 13)):
            d.rectangle([(cx - 4) * s, (cy - 4) * s, (cx + 4) * s, (cy + 4) * s], fill=c["paper"][:3],
                        outline=c["ink"], width=s)

        # the heading
        local = self.when.astimezone(ZoneInfo(self.tz))
        mid = W / 2
        d.text((mid, 44 * s), f"Observations at {self.place}", font=_f(CAPS, 30), fill=c["ink"], anchor="mm")
        d.text((mid, 76 * s), f"{local:%A}, the {_ordinal(local.day)} of {local:%B}, at {local:%H}·{local:%M}",
               font=_f(ITALIC, 19), fill=c["ink"], anchor="mm")
        y_rule = 96 * s
        d.line([(60 * s, y_rule), (mid - 10 * s, y_rule)], fill=c["ink"], width=s)
        d.line([(mid + 10 * s, y_rule), (W - 60 * s, y_rule)], fill=c["ink"], width=s)
        d.polygon([(mid, y_rule - 5 * s), (mid + 6 * s, y_rule), (mid, y_rule + 5 * s), (mid - 6 * s, y_rule)],
                  fill=c["ink"])

        inst_y, R = 212 * s, 92 * s
        left, right = 150 * s, W - 150 * s
        self._barometer(d, c, left, inst_y, R)
        self._rose(d, c, right, inst_y, R)

        # the air, between the instruments
        if self.r.get("temperature") is not None:
            t = self.r["temperature"]
            txt = f"{t:.1f}".replace(".", "·").replace("-", "–")
            big, small = _f(ROMAN, 66), _f(ROMAN, 40)
            tw, dw = d.textlength(txt, font=big), d.textlength("°", font=small)
            x0 = mid - (tw + dw) / 2
            d.text((mid, inst_y - 46 * s), "the Air", font=_f(ITALIC, 22), fill=c["ink"], anchor="mm")
            d.text((x0, inst_y + 6 * s), txt, font=big, fill=c["ink"], anchor="lm")
            top = d.textbbox((x0, inst_y + 6 * s), txt, font=big, anchor="lm")[1]   # old-style figures sit low
            dtop = d.textbbox((0, 0), "°", font=small, anchor="lt")[1]
            d.text((x0 + tw + 2 * s, top - dtop), "°", font=small, fill=c["ink"], anchor="lt")
            d.text((mid, inst_y + 54 * s), "Celsius", font=_f(ITALIC, 18), fill=c["faint"], anchor="mm")
            if self.r.get("feels_like") is not None:
                fl = f"{self.r['feels_like']:.1f}".replace(".", "\u00b7").replace("-", "\u2013")
                d.text((mid, inst_y + 84 * s), f"feels like {fl}\u00b0", font=_f(ITALIC, 21), fill=c["ink"], anchor="mm")

        # the readings in words, under each instrument
        cap_y = inst_y + R + 38 * s
        if self.r.get("pressure") is not None:
            p = self.r["pressure"]
            tw = trend_word(self.r.get("pressure_change_3h"))
            d.text((left, cap_y), f"{p:.0f} hPa" + (f", {tw}" if tw else ""), font=_f(ITALIC, 20),
                   fill=c["ink"], anchor="mm")
        if self.r.get("wind_speed") is not None:
            force, name = beaufort(self.r["wind_speed"])
            line = name if force == 0 or self.r.get("wind_from") is None \
                else f"{name} from the {point(self.r['wind_from'])}"
            d.text((right, cap_y), line, font=_f(ITALIC, 20), fill=c["ink"], anchor="mm")
            speed = f"{self.r['wind_speed']:.1f}".replace(".", "\u00b7")
            d.text((right, cap_y + 26 * s), f"{speed} m/s", font=_f(ROMAN, 20), fill=c["ink"], anchor="mm")

        return im.resize((self.w, self.h), Image.LANCZOS)

    def _barometer(self, d, c, cx, cy, R):
        """Dial with a 240 degree scale from 950 to 1050 hPa, the five words, a tapered needle."""
        s = SS

        def ang(hpa):                                    # math angle, degrees, anticlockwise from east
            f = (min(max(hpa, BARO_MIN), BARO_MAX) - BARO_MIN) / (BARO_MAX - BARO_MIN)
            return math.radians(210 - 240 * f)

        def at(a, r):
            return cx + r * math.cos(a), cy - r * math.sin(a)

        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=c["ink"], width=2 * s)
        d.ellipse([cx - R + 6 * s, cy - R + 6 * s, cx + R - 6 * s, cy + R - 6 * s], outline=c["ink"], width=s)
        for v in range(950, 1051, 5):
            a = ang(v)
            r0 = R - (20 if v % 10 == 0 else 14) * s
            d.line([at(a, r0), at(a, R - 7 * s)], fill=c["ink"], width=(2 if v % 50 == 0 else 1) * s)
        p = self.r.get("pressure")
        now = baro_word(p) if p is not None else None
        for v, word in BARO_WORDS:
            x, y = at(ang(v), R - 42 * s)
            d.text((x, y), word, font=_f(ITALIC, 15), anchor="mm",
                   fill=c["accent"] if word == now else c["ink"])
        if p is None:
            return
        a = ang(p)
        tip, tail = at(a, R - 16 * s), at(a + math.pi, 20 * s)
        side = 4 * s
        px, py = -math.sin(a) * side, -math.cos(a) * side
        d.polygon([tip, (cx + px, cy + py), tail, (cx - px, cy - py)], fill=c["ink"])
        d.ellipse([cx - 7 * s, cy - 7 * s, cx + 7 * s, cy + 7 * s], fill=c["paper"][:3], outline=c["ink"], width=2 * s)

    def _rose(self, d, c, cx, cy, R):
        """Sixteen-point rose with the wind arrow flying downwind across it."""
        s = SS
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=c["ink"], width=2 * s)
        d.ellipse([cx - R + 6 * s, cy - R + 6 * s, cx + R - 6 * s, cy + R - 6 * s], outline=c["ink"], width=s)
        for i in range(32):
            b = math.radians(i * 11.25)
            r0 = R - (13 if i % 2 == 0 else 9) * s
            d.line([(cx + math.sin(b) * r0, cy - math.cos(b) * r0),
                    (cx + math.sin(b) * (R - 6 * s), cy - math.cos(b) * (R - 6 * s))], fill=c["ink"], width=s)

        def star(bearing, length, width, shade):
            """One point of the rose: a long diamond, half filled (the old engraver's shading)."""
            b, w = math.radians(bearing), width
            tip = (cx + math.sin(b) * length, cy - math.cos(b) * length)
            l = (cx + math.sin(b - math.pi / 2) * w, cy - math.cos(b - math.pi / 2) * w)
            r = (cx + math.sin(b + math.pi / 2) * w, cy - math.cos(b + math.pi / 2) * w)
            d.polygon([(cx, cy), l, tip], fill=c["ink"] if shade else c["paper"][:3], outline=c["ink"])
            d.polygon([(cx, cy), r, tip], fill=c["paper"][:3] if shade else c["ink"], outline=c["ink"])

        for bearing in (22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5):
            star(bearing, R * 0.48, 4 * s, True)
        for bearing in (45, 135, 225, 315):
            star(bearing, R * 0.62, 7 * s, True)
        for bearing in (0, 90, 180, 270):
            star(bearing, R * 0.80, 10 * s, True)
        f = _f(CAPS, 17)
        for bearing, letter in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
            b = math.radians(bearing)
            r = R + 13 * s
            d.text((cx + math.sin(b) * r, cy - math.cos(b) * r), letter, font=f, fill=c["ink"], anchor="mm")

        speed, frm = self.r.get("wind_speed"), self.r.get("wind_from")
        if speed is None or frm is None:
            return
        force, _ = beaufort(speed)
        if force == 0:                                   # calm: a ring round the centre, no arrow
            d.ellipse([cx - 14 * s, cy - 14 * s, cx + 14 * s, cy + 14 * s], outline=c["accent"], width=2 * s)
            return
        _arrow(d, cx, cy, (frm + 180) % 360, force, R, c["accent"], c["paper"][:3], s)


def _arrow(d, cx, cy, toward, force, R, ink, halo, s):
    """The old wind-chart arrow across the rose, flying `toward` (bearing): a barbed head, a slim
    shaft and hatched feathers at the tail. Stronger wind: a longer arrow, more feathers, a heavier
    head."""
    b = math.radians(toward)
    ux, uy = math.sin(b), -math.cos(b)                   # along the flight, screen y down
    vx, vy = -uy, ux                                     # across it
    length = R * (1.15 + 0.06 * min(force, 12))          # whole arrow; centred on the rose
    hx, hy = cx + ux * length / 2, cy + uy * length / 2  # tip
    tx, ty = cx - ux * length / 2, cy - uy * length / 2  # tail end
    head = (12 + 1.2 * force) * s
    barb = (6 + 0.5 * force) * s
    notch = head * 0.45
    base = (hx - ux * head, hy - uy * head)
    poly = [(hx, hy),
            (base[0] + vx * barb, base[1] + vy * barb),
            (hx - ux * (head - notch), hy - uy * (head - notch)),
            (base[0] - vx * barb, base[1] - vy * barb)]
    w = max(2, round(1.2 + force * 0.18)) * s
    d.line([(tx, ty), (hx - ux * head * 0.5, hy - uy * head * 0.5)], fill=halo, width=w + 4 * s)
    d.line([(tx, ty), (hx - ux * head * 0.5, hy - uy * head * 0.5)], fill=ink, width=w)
    d.polygon(poly, fill=ink, outline=halo)
    pairs = max(1, min(6, math.ceil(force / 2)))         # a pair of feathers per two forces
    for i in range(pairs):
        ox, oy = tx + ux * (4 + i * 8) * s, ty + uy * (4 + i * 8) * s
        for side in (1, -1):
            fx = ox + (-ux * 0.8 + vx * side * 0.6) * 15 * s
            fy = oy + (-uy * 0.8 + vy * side * 0.6) * 15 * s
            d.line([(ox, oy), (fx, fy)], fill=ink, width=2 * s)


class LegendLayer:
    """The legend as a map layer (artmode/layers.py): drawn at ctx.data["legend_at"] (the map's
    free corner, from artmode/places.py) with ctx.data["legend"] = {"reading", "place", "tz"}."""
    name = "legend"

    def draw(self, pic, ctx):
        at, info = ctx.data.get("legend_at"), ctx.data.get("legend")
        if not at or not info:
            return
        lg = Legend(info["reading"], info["place"], ctx.t, tz=info.get("tz") or "Europe/Stockholm")
        place_on(pic, lg, int(at[0]), int(at[1]))


SIZE = (700, 416)                         # the legend's size in 4K px (Legend's default w, h)


def place_on(pic, legend, x, y):
    """Composite the legend onto the 4K picture at (x, y), dark or light by what is under it."""
    under = np.asarray(pic.crop((x, y, x + legend.w, y + legend.h)).convert("L")).mean()
    panel = legend.image(night=under < 110)
    pic.paste(panel, (x, y), panel)


def demo(out):
    from . import ephem, render
    import io
    os.makedirs(out, exist_ok=True)
    sample = {"temperature": 4.2, "pressure": 1004.0, "pressure_change_3h": -2.1,
              "wind_speed": 9.4, "wind_from": 247.0}
    for name, when in (("night", "2026-11-16T14:40"), ("day", "2026-11-16T10:00")):
        t = ephem.utc(when)
        pic = Image.open(io.BytesIO(render.render("R1", t)))
        lg = Legend(sample, "Stockholm", t)
        place_on(pic, lg, 3840 - 80 - lg.w, 80)
        pic.save(os.path.join(out, f"legend_R1_{name}.jpg"), quality=92)
        pic.crop((3840 - 80 - lg.w - 40, 40, 3840 - 40, 80 + lg.h + 40)).save(os.path.join(out, f"legend_{name}_crop.png"))
    # the arrow from calm to storm, on day paper
    strip = Image.new("RGB", (6 * 240, 260), DAY["paper"][:3])
    for i, (speed, label) in enumerate(((0.2, "0"), (2.5, "2"), (6.5, "4"), (12, "6"), (19, "8"), (30, "11"))):
        cell = Legend({"wind_speed": speed, "wind_from": 247.0}, "", ephem.utc("2026-11-16T10:00"), w=240, h=260)
        im = Image.new("RGBA", (240 * SS, 260 * SS), DAY["paper"])
        dd = ImageDraw.Draw(im)
        cell._rose(dd, DAY, 120 * SS, 120 * SS, 80 * SS)
        dd.text((120 * SS, 235 * SS), f"force {label}: {beaufort(speed)[1]}", font=_f(ITALIC, 16), fill=DAY["ink"], anchor="mm")
        strip.paste(im.resize((240, 260), Image.LANCZOS).convert("RGB"), (i * 240, 0))
    strip.save(os.path.join(out, "legend_arrows.png"))


if __name__ == "__main__":
    import sys
    demo(sys.argv[1] if len(sys.argv) > 1 else ".")
