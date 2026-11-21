"""Where the add-on finds a map's files. Three sources, tried in this order for each file:

    maps folder   the add-on option `maps_folder`, for example a NAS share mounted in Home Assistant
                  at /share/atlas (`atlas.py render --sync` writes there)
    my maps       the add-on's own config folder, /config/maps inside the add-on, which is
                  addon_configs/<…>_atlas_frame/maps on the Samba share: unzip a map pack there
    pack          an installed map pack (artmode/packs.py: a licensed .atlaspack dropped into
                  /share/atlas_frame/packs, unpacked by the add-on into /data/packs)
    template      the copies built into the add-on (only The World, W1, in the public build)

A map that is not built in is shown only while an installed pack's licence covers it (`available`).

A file that is missing, unreadable or the wrong size in one source is skipped, with a note, so a
half-synced folder never breaks a push. With `maps_source: templates` only the built-in copies are
used.

Layout of the maps folder, of my maps and of an installed pack, as `atlas.py render --out` and packs.py write it:
    <id>_4k.png, <id>N_4k.png     the day and night maps, lossless (or .jpg; within a source the
                                  .png is tried first, so a lossless copy takes over from a JPEG)
    places/<id>.json              the map's places, label boxes and legend spot (artmode/places.py)
    grids/<id>.npz                the map's globe grid (artmode/grids.py)
"""
import os

EXTERNAL = os.environ.get("ATLAS_EXTERNAL", "")      # set by the service from `maps_folder`
OWN = os.environ.get("ATLAS_OWN", "/config/maps")    # my maps: the add-on's own config folder
TEMPLATES_ONLY = False                               # `maps_source: templates`: built-in copies only
SOURCES = {}            # what came from where in the last render: {"R1_4k": "maps folder", ...}
KINDS = {}              # which kind each picture was in the last render: {"R1_4k": "png", ...}
PICTURE_EXTS = (".png", ".jpg")     # lossless first
PROBLEMS = []           # files skipped in the last render, and why


def folders():
    """[(source, folder)] of the side-loaded sources in use, in the order to try: the maps folder, my maps, then the
    installed packs."""
    if TEMPLATES_ONLY:
        return []
    from . import packs
    return [(src, d) for src, d in (("maps folder", EXTERNAL), ("my maps", OWN)) if d] + packs.folders()


def candidates(sub, name, builtin_dir):
    """[(source, path)] in the order to try: the maps folder, my maps, then the built-in template."""
    out = [(src, os.path.join(d, sub, name) if sub else os.path.join(d, name)) for src, d in folders()]
    out.append(("template", os.path.join(builtin_dir, name)))
    return out


def picture_candidates(stem, builtin_dir):
    """[(source, path)] for a map picture ("R1_4k"): each source in order, its .png before its .jpg."""
    out = []
    for src, d in folders() + [("template", builtin_dir)]:
        out += [(src, os.path.join(d, stem + ext)) for ext in PICTURE_EXTS]
    return out


def builtin_dirs():
    """The built-in maps, grids and places folders (as artmode.render and artmode.places use them)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return (os.environ.get("ATLAS_MAPS", os.path.join(os.path.dirname(here), "renders")),
            os.environ.get("ATLAS_GRIDS", os.path.join(here, "grids")),
            os.environ.get("ATLAS_PLACES", os.path.join(here, "places")))


def built_in(map_id):
    """Whether the add-on itself carries the map (its day picture is among the built-in maps)."""
    maps = builtin_dirs()[0]
    return any(os.path.isfile(os.path.join(maps, f"{map_id}_4k{ext}")) for ext in PICTURE_EXTS)


def available(map_id):
    """Whether a map can be shown: built in, or covered by an installed pack's licence (artmode/packs.py); and its
    day and night pictures, places and grid each exist in some source. Only that they exist; a bad one is still
    skipped, with a note, when it is loaded."""
    from . import packs
    if not built_in(map_id) and not packs.licensed(map_id):
        return False
    maps, grids, places = builtin_dirs()
    need = [("places", f"{map_id}.json", places), ("grids", f"{map_id}.npz", grids)]
    pics = all(any(os.path.isfile(p) for _, p in picture_candidates(stem, maps))
               for stem in (f"{map_id}_4k", f"{map_id}N_4k"))
    return pics and all(any(os.path.isfile(p) for _, p in candidates(sub, name, d)) for sub, name, d in need)


def reset():
    SOURCES.clear()
    KINDS.clear()
    del PROBLEMS[:]
