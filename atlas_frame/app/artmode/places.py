"""Per map, the places data can be shown at: the map's own labelled cities, largest first, with their
dot and label box in 4K pixels. Built once with the repo (needs geo.py); read at run time as JSON.

    python -m artmode.places            # all 17 maps -> artmode/places/<id>.json

Each file: {"map": id, "places": [{"name", "lat", "lon", "pop", "dot": [x, y],
"box": [x, y, w, h]}], "boxes": [[x, y, w, h], ...]} where `boxes` are the ink boxes of every
label on the map (cities, countries, seas, rivers...), so a layer can keep its marks off the
lettering. Labels are taken as the map was drawn: the saved layout with its fixes
(compose.final_items, read only).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

OUT = os.path.join(HERE, "places")
PER_MAP = 14            # anchor places per map (the World gets more: it is the overview)
SCALE = 0.5             # layouts are in 8K pixels, pictures are 4K


def build(view_id, out=None):
    """Write <out>/<view_id>.json (default artmode/places/); returns (path, number of places)."""
    import compose
    import geo
    import labels
    view = geo.VIEWS[view_id]
    recipe = os.path.join(REPO, "maps", f"{view_id}.json")
    R = json.load(open(recipe, encoding="utf-8"))
    _, reserved = compose.ornament_layer(R, view, "en")
    reserved = list(reserved)
    import ornament_sheet
    if ornament_sheet.tier_of(view_id, ornament_sheet.load_rules()) == "T0":     # W1: its fixed ornaments
        import obstacles
        reserved += obstacles.for_view(view, R, map_id=view_id).reserved()
    lay = labels.load_layout(os.path.join(REPO, "maps", f"{view_id}.layout.en.json"))
    items, _ = compose.final_items(R, recipe, lay, reserved, True, "en", readonly=True)
    items = [i for i in items if not i.get("hidden") and not i.get("dropped") and i.get("lines")]
    names = json.load(open(os.path.join(REPO, "labels", "en.json"), encoding="utf-8"))
    cities = [c for c in items if c.get("kind") == "city" and c.get("dot")]

    def box(c):
        """The name's ink box as [x, y, w, h] in 4K px (labels.item_boxes, without the dot)."""
        if c.get("x") is None or not c.get("lines"):
            return None
        x0, y0, x1, y1 = labels.item_boxes(dict(c, dot=None))[0][:4]
        return [round(x0 * SCALE, 1), round(y0 * SCALE, 1), round((x1 - x0) * SCALE, 1), round((y1 - y0) * SCALE, 1)]
    boxes = []
    for it in items:                  # every label's ink: a run (country, sea, river) is a box per letter
        try:
            bs = labels.item_boxes(dict(it, dot=None))
        except Exception:             # an item kind item_boxes cannot measure: it keeps no box
            continue
        for b in bs:
            x0, y0, x1, y1 = b[:4]
            boxes.append([round(x0 * SCALE, 1), round(y0 * SCALE, 1), round((x1 - x0) * SCALE, 1), round((y1 - y0) * SCALE, 1)])
    places = []
    for c in sorted(cities, key=lambda c: -(c.get("pop") or 0)):
        x, y = c["dot"][0], c["dot"][1]
        if not (0 <= x < view.w and 0 <= y < view.h):
            continue
        lon, lat, ok = view.inverse(x, y)
        if not bool(ok):
            continue
        places.append({
            "name": names.get(c["key"], " ".join(c.get("lines", [c["key"].split(":", 1)[-1]]))),
            "lat": round(float(lat), 4), "lon": round(float(lon), 4), "pop": c.get("pop"),
            "dot": [round(x * SCALE, 1), round(y * SCALE, 1)],
            "box": box(c),
        })
        if len(places) >= (2 * PER_MAP if view_id == "W1" else PER_MAP):
            break
    ornaments = [[round(r[0] * SCALE, 1), round(r[1] * SCALE, 1), round((r[2] - r[0]) * SCALE, 1),
                  round((r[3] - r[1]) * SCALE, 1)] for r in reserved]
    out = out or OUT
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{view_id}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"map": view_id, "places": places, "boxes": boxes, "ornaments": ornaments,
                   "legend_at": legend_spot(boxes, ornaments)}, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    return path, len(places)


def legend_spot(boxes, ornaments, size=None, W=3840, H=2160, margin=80, gap=30):
    """Top-left corner (4K px) for the weather legend: clear of the map's ornaments, inside the
    margin the ornaments keep, covering the least lettering; corners first. None if nothing fits."""
    if size is None:
        from .legend import SIZE as size
    w, h = size

    def hits(x, y, rects, pad):
        return [(rx, ry, rw, rh) for rx, ry, rw, rh in rects
                if x < rx + rw + pad and rx < x + w + pad and y < ry + rh + pad and ry < y + h + pad]

    xs = [margin + i * (W - 2 * margin - w) / 12 for i in range(13)]
    ys = [margin + i * (H - 2 * margin - h) / 8 for i in range(9)]
    cands = [(x, y) for x in xs for y in (ys[0], ys[-1])] + [(x, y) for y in ys[1:-1] for x in (xs[0], xs[-1])]
    best = None
    for x, y in cands:
        if hits(x, y, ornaments, gap):
            continue
        covered = sum((min(x + w, bx + bw) - max(x, bx)) * (min(y + h, by + bh) - max(y, by))
                      for bx, by, bw, bh in hits(x, y, boxes, 0))
        corner = x in (xs[0], xs[-1]) and y in (ys[0], ys[-1])
        score = covered + (0 if corner else 3000)
        if best is None or score < best[0]:
            best = (score, [round(x), round(y)])
    return best[1] if best else None


def load(map_id, folder=None):
    """The places file of a map: from the maps folder (artmode/files.py) when it has a readable one,
    else the built-in one; an empty set if neither exists."""
    from . import files
    builtin = folder or os.environ.get("ATLAS_PLACES", OUT)
    for src, path in files.candidates("places", f"{map_id}.json", builtin):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            files.SOURCES[f"{map_id} places"] = src
            return d
        except (OSError, ValueError) as e:
            files.PROBLEMS.append(f"{map_id} places from {src}: {e.__class__.__name__}")
    return {"map": map_id, "places": [], "boxes": [], "ornaments": [], "legend_at": None}


if __name__ == "__main__":
    import daynight
    for i in sys.argv[1:] or [s[0] for s in daynight.SLIDES]:
        path, n = build(i)
        print(f"{i:4s} {n:2d} places")
