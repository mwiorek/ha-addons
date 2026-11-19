"""Data layers drawn on top of the lit map. A layer has a `name` and `draw(pic, ctx)`, where pic is
the 4K PIL image and ctx a render.Context (map, time, day weight, ink colours, and ctx.data).

ctx.data, filled by the service before rendering:
  "weather": readings at the map's places (artmode/sources.py), with their 4K dot and label box
  "home":    one reading from your own Home Assistant sensors, or None
  "boxes":   all city label boxes on the map (4K), to keep marks off the lettering

The look here is a first draft to try on the wall: small figures in the map's own ink beside each
city, a wind arrow, and a home reading. To add a data type: a source in sources.py that returns
readings, and a layer here that draws them.
"""
import math
import os

import numpy as np
from PIL import ImageDraw, ImageFont

from . import ephem

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.environ.get("ATLAS_FONTS", os.path.join(os.path.dirname(HERE), "assets", "fonts"))
PAPER = (236, 226, 200)          # halo on light ground
NIGHT = (13, 18, 32)             # halo on dark ground
BROWN = (84, 60, 42)             # ink on light ground
PALE = (226, 214, 186)           # ink on dark ground


def _font(size, italic=False):
    name = "IMFeENit28P.ttf" if italic else "IMFeENrm28P.ttf"
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def _colours(pic, x, y, w, h):
    """(ink, halo) for a mark over this part of the picture, chosen by how bright it is there, so
    figures read on day paper, night sea, twilight and panels alike (never a mid-tone blend)."""
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(pic.width, int(x + w) + 1), min(pic.height, int(y + h) + 1)
    if x1 <= x0 or y1 <= y0:
        return BROWN, PAPER
    light = float(np.asarray(pic.crop((x0, y0, x1, y1)).convert("L")).mean()) > 110
    return (BROWN, PAPER) if light else (PALE, NIGHT)


def _overlaps(r, boxes, pad=3):
    x, y, w, h = r
    return any(x < bx + bw + pad and bx < x + w + pad and y < by + bh + pad and by < y + h + pad
               for bx, by, bw, bh in boxes)


def _arrow(draw, x, y, speed, wind_from, ink, halo):
    """Arrow pointing where the wind blows to; longer for stronger wind (map north is up, close
    enough for a symbol)."""
    to = math.radians(wind_from + 180)
    length = 10 + min(speed, 15) * 2.0
    dx, dy = math.sin(to) * length, -math.cos(to) * length
    x0, y0, x1, y1 = x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2
    head = [(x1, y1),
            (x1 - 7 * math.sin(to + 0.45), y1 + 7 * math.cos(to + 0.45)),
            (x1 - 7 * math.sin(to - 0.45), y1 + 7 * math.cos(to - 0.45))]
    draw.line([(x0, y0), (x1, y1)], fill=halo, width=6)
    draw.polygon(head, fill=halo)
    draw.line([(x0, y0), (x1, y1)], fill=ink, width=2)
    draw.polygon(head, fill=ink)


def _spots(r, w, h):
    """Where a w x h mark for this place may go, best first: beside its name, then on rings
    round its dot (nearest ring first, east and west before north and south)."""
    dx, dy = r["dot"]
    out = []
    if r.get("box"):
        bx, by, bw, bh = r["box"]
        out += [(bx + bw + 8, by + (bh - h) / 2), (bx - w - 8, by + (bh - h) / 2),
                (bx + (bw - w) / 2, by + bh + 4), (bx + (bw - w) / 2, by - h - 4)]
    for radius in (22, 40, 60):
        for deg in (0, 180, 30, 150, 330, 210, 60, 120, 300, 240, 90, 270):
            a = math.radians(deg)
            cx, cy = dx + math.cos(a) * (radius + w / 2), dy - math.sin(a) * (radius + h / 2)
            out.append((cx - w / 2, cy - h / 2))
    return out


class Weather:
    """Temperature (and wind) beside each of the map's places, from Open-Meteo."""
    name = "weather"

    def __init__(self, show=("temperature", "wind"), size=30):
        self.show, self.font = set(show), _font(size)

    def draw(self, pic, ctx):
        draw = ImageDraw.Draw(pic)
        taken = list(ctx.data.get("boxes", []))
        for r in ctx.data.get("weather", []):
            if "dot" not in r:
                continue
            parts = []
            if "temperature" in self.show and "temperature" in r:
                parts.append(f"{r['temperature']:.0f}°")
            if "pressure" in self.show and "pressure" in r:
                parts.append(f"{r['pressure']:.0f}")
            text = "  ".join(parts)
            tw = draw.textlength(text, font=self.font) if text else 0
            wind = "wind" in self.show and r.get("wind_speed") is not None and r.get("wind_from") is not None
            w, h = tw + (40 if wind else 0), 34
            spots = _spots(r, w, h)
            for sx, sy in spots:
                if 0 <= sx and sx + w <= pic.width and 0 <= sy and sy + h <= pic.height \
                        and not _overlaps((sx, sy, w, h), taken):
                    break
            else:
                continue                                   # no free spot: leave this city out
            ink, halo = _colours(pic, sx, sy, w, h)
            if text:
                draw.text((sx, sy + h / 2), text, font=self.font, fill=ink, anchor="lm",
                          stroke_width=3, stroke_fill=halo)
            if wind:
                _arrow(draw, sx + tw + 22, sy + h / 2, r["wind_speed"], r["wind_from"], ink, halo)
            taken.append((sx, sy, w, h))


class Home:
    """Your own sensors at home: a ring on the spot and the full reading beside it, if home is on
    the map."""
    name = "home"

    def __init__(self, size=34):
        self.font, self.small = _font(size), _font(int(size * 0.8), italic=True)

    def draw(self, pic, ctx):
        r = ctx.data.get("home")
        if not r:
            return
        at = ctx.grid.locate(ephem.place_vec(r["lat"], r["lon"]))
        if not at:
            return
        x, y = at
        draw = ImageDraw.Draw(pic)
        ink, halo = _colours(pic, x - 16, y - 30, 360, 90)
        for rad, col, wid in ((13, halo, 6), (13, ink, 2)):
            draw.ellipse([x - rad, y - rad, x + rad, y + rad], outline=col, width=wid)
        lines = []
        if "temperature" in r:
            lines.append(f"{r['temperature']:.1f}°")
        if "pressure" in r:
            lines.append(f"{r['pressure']:.0f} hPa")
        if "wind_speed" in r:
            lines.append(f"{r['wind_speed']:.0f} m/s")
        tx, ty = x + 24, y - 22
        draw.text((tx, ty), "Home", font=self.small, fill=ink, stroke_width=3, stroke_fill=halo)
        draw.text((tx, ty + 34), "  ".join(lines), font=self.font, fill=ink, stroke_width=3, stroke_fill=halo)
        if r.get("wind_speed") is not None and r.get("wind_from") is not None:
            tw = draw.textlength("  ".join(lines), font=self.font)
            _arrow(draw, tx + tw + 26, ty + 52, r["wind_speed"], r["wind_from"], ink, halo)


ALL = {"weather": Weather, "home": Home}
