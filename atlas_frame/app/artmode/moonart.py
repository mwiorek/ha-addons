"""The moon drawn from a picture of the full moon: any phase, shaded continuously across the
terminator, at its true apparent size. MOCK-UP (2026-11-16); replaces the inked phase symbol in
render.py once the look is chosen.

The base picture is assets/moon.png (the engraved moon, transparent outside the disc), or any
full-moon picture given as ATLAS_MOON or on the command line: a transparent one is cut by its own
edge, an opaque one by brightness against its dark background.

    python -m artmode.moonart [BASE] [OUT_FOLDER]          # phase strips, sizes beside Iceland, tonight on Europe
    python -m artmode.moonart --day [BASE] [OUT_FOLDER]    # the day finishes: ink rim, cool, warm

Size: the average moon is as wide as Iceland on the Europe map (198 px at 4K, AVG_DIAMETER), and
grows and shrinks with the moon's real distance (about 0.93 to 1.08), optionally exaggerated.
Two styles:
  "dimmed":  the dark part stays, faintly lit by earthshine, as the moon is seen in a dark sky
  "cut out": the dark part is gone; the lit part sits on the map like a cut paper moon
"""
import math
import os

import numpy as np
from PIL import Image

from . import ephem

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("ATLAS_MOON", os.path.join(os.path.dirname(HERE), "assets", "moon.png"))
AVG_DIAMETER = 198            # 4K px: Iceland's east-west width on the Europe map (R1)
EARTHSHINE = 0.13             # brightness of the dark part in the "dimmed" style
SOFT = 0.035                  # width of the terminator's soft edge, in units of the moon's radius


def load_base(path=BASE):
    """(RGB array, alpha array) of the moon disc, square and centred, from a full-moon picture."""
    src = Image.open(path)
    rgba = np.asarray(src.convert("RGBA")).astype(np.float32)
    im = rgba[..., :3]
    if src.mode in ("RGBA", "LA", "P") and rgba[..., 3].min() < 128:
        ys, xs = np.nonzero(rgba[..., 3] > 128)        # transparent outside: the disc is what is opaque
    else:
        lum = im.mean(2)
        ys, xs = np.nonzero(lum > max(25.0, lum.max() * 0.12))
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    r = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2
    x0, y0 = int(round(cx - r)), int(round(cy - r))
    side = int(round(2 * r))
    pad = np.zeros((side, side, 3), np.float32)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(im.shape[1], x0 + side), min(im.shape[0], y0 + side)
    pad[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = im[sy0:sy1, sx0:sx1]
    g = (np.arange(side) + 0.5) / side * 2 - 1
    gx, gy = np.meshgrid(g, g)
    alpha = np.clip((1 - np.hypot(gx, gy)) * side / 2 + 0.5, 0, 1)      # 1 px soft rim
    return pad, alpha


def sprite(base, diameter, k, limb_angle, style="dimmed"):
    """RGBA picture of the moon `diameter` px wide. k: lit fraction 0 (new) to 1 (full).
    limb_angle: screen direction of the bright limb (radians, y down), i.e. towards the sun."""
    rgb, alpha = base
    n = max(8, int(round(diameter)))
    rgb = np.asarray(Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).resize((n, n), Image.LANCZOS)).astype(np.float32)
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).resize((n, n), Image.LANCZOS)).astype(np.float32) / 255
    g = (np.arange(n) + 0.5) / n * 2 - 1
    x, y = np.meshgrid(g, g)
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    i = math.acos(max(-1.0, min(1.0, 2 * k - 1)))          # phase angle: 0 full, pi new
    ux, uy = math.cos(limb_angle), math.sin(limb_angle)
    sun = (math.sin(i) * ux, math.sin(i) * uy, math.cos(i))  # towards the sun, seen from the moon's centre
    light = x * sun[0] + y * sun[1] + z * sun[2]           # > 0 on the lit half of the sphere
    lit = np.clip((light + SOFT) / (2 * SOFT), 0, 1)
    lit = lit * lit * (3 - 2 * lit)
    if style == "cut out":
        out_rgb, out_a = rgb, alpha * lit
    else:
        out_rgb, out_a = rgb * (EARTHSHINE + (1 - EARTHSHINE) * lit)[..., None], alpha
    return Image.fromarray(np.dstack([out_rgb, out_a * 255]).clip(0, 255).astype(np.uint8), "RGBA")


# day finishes for the cut-out moon on the paper: (dark tone, light tone) the engraving is re-toned
# between, or None to keep its own colours
FINISH = {"rim": None,
          "cool": ((52, 64, 92), (246, 250, 255)),        # blue-white, brighter and colder than the paper
          "warm": ((96, 70, 28), (255, 238, 178))}        # pale gold
RIM_INK = (70, 50, 35)                                   # the day map's dark brown ink


def tint(moon, dark, light):
    """Re-tone an RGBA moon between two colours by its brightness (alpha kept)."""
    a = np.asarray(moon).astype(np.float32)
    lum = (a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)) / 255
    lum = np.clip((lum - 0.15) / 0.8, 0, 1)              # stretch: the engraving's paper becomes the light tone
    rgb = np.array(dark, np.float32) + lum[..., None] * (np.array(light, np.float32) - np.array(dark, np.float32))
    return Image.fromarray(np.dstack([rgb, a[..., 3]]).clip(0, 255).astype(np.uint8), "RGBA")


def inked(moon, width=2.2, colour=RIM_INK):
    """Draw a fine ink line round the moon's visible shape (limb and terminator alike), outside it."""
    from PIL import ImageFilter
    a = moon.split()[3]
    pad = int(width) + 3
    canvas = Image.new("RGBA", (moon.width + 2 * pad, moon.height + 2 * pad), (0, 0, 0, 0))
    big = Image.new("L", canvas.size, 0)
    big.paste(a, (pad, pad))
    grown = big.filter(ImageFilter.MaxFilter(2 * int(round(width)) + 1)).filter(ImageFilter.GaussianBlur(0.6))
    line = np.clip(np.asarray(grown, np.float32) - np.asarray(big, np.float32), 0, 255).astype(np.uint8)
    ink = Image.new("RGBA", canvas.size, colour + (0,))
    ink.putalpha(Image.fromarray(line))
    canvas.alpha_composite(ink)
    canvas.alpha_composite(moon, (pad, pad))
    return canvas


def day_moon(base, d, k, limb_angle, finish="rim"):
    """The moon on the day side of a map: cut out, then finished with an ink rim or re-toned."""
    m = sprite(base, d, k, limb_angle, "cut out")
    if finish == "rim":
        return inked(m)
    return tint(m, *FINISH[finish])


def diameter(t, exaggerate=1.0):
    """Moon diameter in 4K px at time t: true apparent size (exaggerate=1), or its swing around the
    average multiplied (exaggerate=3 makes a 7 % larger moon 21 % larger)."""
    return AVG_DIAMETER * (1 + (ephem.moon_size(t) - 1) * exaggerate)


def demo(base_path, out):
    import io
    from PIL import ImageDraw, ImageFont
    from .layers import FONTS
    from . import render
    os.makedirs(out, exist_ok=True)
    base = load_base(base_path)
    font = ImageFont.truetype(os.path.join(FONTS, "IMFeENit28P.ttf"), 26)
    caps = ImageFont.truetype(os.path.join(FONTS, "IMFeENsc28P.ttf"), 30)
    night = Image.open(os.path.join(render.MAPS, "R1N_4k.jpg")).convert("RGB")
    day = Image.open(os.path.join(render.MAPS, "R1_4k.jpg")).convert("RGB")

    # 1. the phases, both styles, on the night sea and on the day paper
    phases = [(0.02, "new"), (0.18, "crescent"), (0.5, "first quarter"), (0.82, "gibbous"), (1.0, "full"),
              (0.82, "gibbous"), (0.5, "last quarter"), (0.18, "crescent")]
    cell, pad = 230, 30
    rows = [("dimmed", night, (40, 260)), ("cut out", night, (40, 260)), ("dimmed", day, (40, 260)), ("cut out", day, (40, 260))]
    strip = Image.new("RGB", (len(phases) * cell + 2 * pad, len(rows) * (cell + 40) + 60), (0, 0, 0))
    for r, (style, bg, (sx, sy)) in enumerate(rows):
        y = 40 + r * (cell + 40)
        strip.paste(bg.crop((sx, sy, sx + strip.width, sy + cell + 40)), (0, y))
        d = ImageDraw.Draw(strip)
        light_bg = bg is day
        ink = (70, 50, 35) if light_bg else (226, 214, 186)
        d.text((pad, y + 6), f"{style}, on the {'day' if light_bg else 'night'} map", font=font, fill=ink)
        for c, (k, name) in enumerate(phases):
            waning = c > 4
            m = sprite(base, AVG_DIAMETER, k, math.pi if waning else 0.0, style)
            x = pad + c * cell + (cell - m.width) // 2
            strip.paste(m, (x, y + 30), m)
            d.text((pad + c * cell + cell // 2, y + 30 + m.height + 2), name, font=font, fill=ink, anchor="mt")
    strip.save(os.path.join(out, "moon_phases.jpg"), quality=92)

    # 2. sizes beside Iceland: farthest, average, closest of 2025-26, true and with the swing x3
    t_far, t_near = ephem.utc("2025-11-20T03:00"), ephem.utc("2026-12-24T09:00")
    pic = night.copy()
    d = ImageDraw.Draw(pic)
    ix, iy = 1061, 224                                    # Iceland's middle on the Europe map, 4K
    d.text((ix + 330, iy - 150), "beside Iceland: apogee, average, perigee", font=caps, fill=(226, 214, 186))
    for row, ex in enumerate((1.0, 3.0)):
        y = iy + 200 + row * 300
        d.text((ix - 520, y), "true size" if ex == 1 else "swing × 3", font=caps, fill=(226, 214, 186), anchor="lm")
        for col, (label, dia) in enumerate((("apogee", diameter(t_far, ex)), ("average", AVG_DIAMETER),
                                            ("perigee", diameter(t_near, ex)))):
            m = sprite(base, dia, 1.0, 0.0)
            cx = ix - 200 + col * 330
            pic.paste(m, (int(cx - m.width / 2), int(y - m.height / 2)), m)
            d.text((cx, y + 130), f"{label} {m.width} px", font=font, fill=(226, 214, 186), anchor="mt")
    pic.crop((300, 0, 2000, 1000)).save(os.path.join(out, "moon_sizes.jpg"), quality=92)

    # 3. tonight on Europe: the real phase, size and sky position (as render.py places the sky moon)
    t = ephem.utc("2026-11-16T15:30")
    pic = Image.open(io.BytesIO(render.render("R1", t))).convert("RGB")
    g = render.Grid("R1")
    m_vec, s_vec = ephem.moon_vec(t), ephem.sun_vec(t)
    seen = ephem.place_vec(*g.centre)
    alt = ephem.elevation(m_vec, seen)
    az = math.degrees(ephem.azimuth(m_vec, *g.centre))
    x = 3840 * (0.10 + 0.80 * min(1, max(0, (az - 45) / 270)))
    y = 2160 * (0.20 - 0.12 * min(1, alt / math.radians(60)))
    saz, salt = ephem.azimuth(s_vec, *g.centre), ephem.elevation(s_vec, seen)
    sx = 3840 * (0.10 + 0.80 * min(1.5, max(-0.5, (math.degrees(saz) - 45) / 270)))
    sy = 2160 * (0.20 - 0.12 * salt / math.radians(60))
    m = sprite(base, diameter(t), ephem.lit_fraction(t), math.atan2(sy - y, sx - x))
    pic.paste(m, (int(x - m.width / 2), int(y - m.height / 2)), m)
    pic.save(os.path.join(out, "moon_tonight_R1.jpg"), quality=92)
    pic.crop((int(x) - 500, max(0, int(y) - 300), int(x) + 500, int(y) + 300)).save(os.path.join(out, "moon_tonight_crop.jpg"), quality=92)
    print(f"tonight 15:30 UTC: lit {ephem.lit_fraction(t):.2f}, {ephem.moon_distance(t):.0f} km, "
          f"{diameter(t):.0f} px, altitude {math.degrees(alt):.0f} deg from the map's centre")




def demo_day(base_path, out):
    """The three day finishes side by side on the day map, with the dimmed night moon for reference."""
    from PIL import ImageDraw, ImageFont
    from .layers import FONTS
    from . import render
    os.makedirs(out, exist_ok=True)
    base = load_base(base_path)
    font = ImageFont.truetype(os.path.join(FONTS, "IMFeENit28P.ttf"), 26)
    caps = ImageFont.truetype(os.path.join(FONTS, "IMFeENsc28P.ttf"), 28)
    day = Image.open(os.path.join(render.MAPS, "R1_4k.jpg")).convert("RGB")
    night = Image.open(os.path.join(render.MAPS, "R1N_4k.jpg")).convert("RGB")
    phases = [(0.18, 0.0, "crescent"), (0.5, 0.0, "first quarter"), (0.82, 0.0, "gibbous"),
              (1.0, 0.0, "full"), (0.82, math.pi, "gibbous, waning"), (0.3, math.pi, "crescent, waning")]
    rows = [("day: cut out, ink rim", "rim"), ("day: cool, blue-white", "cool"), ("day: warm, pale gold", "warm"),
            ("night: dimmed (for reference)", None)]
    cell, x0, y0 = 250, 140, 640                     # the open North Atlantic on Europe, 4K
    sheet = Image.new("RGB", (len(phases) * cell + 60, len(rows) * 300), (0, 0, 0))
    for r, (title, finish) in enumerate(rows):
        bg = night if finish is None else day
        sheet.paste(bg.crop((x0, y0, x0 + sheet.width, y0 + 300)), (0, r * 300))
        d = ImageDraw.Draw(sheet)
        ink = (226, 214, 186) if finish is None else (70, 50, 35)
        d.text((30, r * 300 + 12), title, font=caps, fill=ink)
        for c, (k, ang, name) in enumerate(phases):
            m = sprite(base, AVG_DIAMETER, k, ang, "dimmed") if finish is None else day_moon(base, AVG_DIAMETER, k, ang, finish)
            cx = 30 + c * cell + cell // 2
            sheet.paste(m, (cx - m.width // 2, r * 300 + 150 - m.height // 2 + 10), m)
            d.text((cx, r * 300 + 268), name, font=font, fill=ink, anchor="mm")
    sheet.save(os.path.join(out, "moon_day_finishes.jpg"), quality=93)

    # in context: the same gibbous moon in each finish over the day map, at true size
    ctx = day.crop((200, 120, 2600, 1020)).copy()
    for i, finish in enumerate(("rim", "cool", "warm")):
        m = day_moon(base, AVG_DIAMETER, 0.82, math.pi, finish)
        cx = 420 + i * 760
        ctx.paste(m, (cx - m.width // 2, 330 - m.height // 2), m)
        ImageDraw.Draw(ctx).text((cx, 470), {"rim": "ink rim", "cool": "cool", "warm": "warm"}[finish],
                                 font=caps, fill=(70, 50, 35), anchor="mm")
    ctx.save(os.path.join(out, "moon_day_in_context.jpg"), quality=93)


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if a != "--day"]
    run = demo_day if "--day" in sys.argv else demo
    run(args[0] if args else BASE, args[1] if len(args) > 1 else ".")
