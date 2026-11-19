"""Where the add-on finds a map's files. Three sources, tried in this order for each file:

    maps folder   the add-on option `maps_folder`, for example a NAS share mounted in Home Assistant
                  at /share/atlas (`atlas.py render --sync` writes there)
    my maps       the add-on's own config folder, /config/maps inside the add-on, which is
                  addon_configs/<…>_atlas_frame/maps on the Samba share: unzip a map pack there
    template      the copies built into the add-on (only The World, W1, in the public build)

A file that is missing, unreadable or the wrong size in one source is skipped, with a note, so a
half-synced folder never breaks a push. With `maps_source: templates` only the built-in copies are
used.

Layout of the maps folder and of my maps, as `atlas.py render --out` and map_pack.sh write it:
    <id>_4k.jpg, <id>N_4k.jpg     the day and night maps
    places/<id>.json              the map's places, label boxes and legend spot (artmode/places.py)
    grids/<id>.npz                the map's globe grid (artmode/grids.py)
"""
import os

EXTERNAL = os.environ.get("ATLAS_EXTERNAL", "")      # set by the service from `maps_folder`
OWN = os.environ.get("ATLAS_OWN", "/config/maps")    # my maps: the add-on's own config folder
TEMPLATES_ONLY = False                               # `maps_source: templates`: built-in copies only
SOURCES = {}            # what came from where in the last render: {"R1_4k.jpg": "maps folder", ...}
PROBLEMS = []           # files skipped in the last render, and why


def folders():
    """[(source, folder)] of the side-loaded sources in use, in the order to try."""
    if TEMPLATES_ONLY:
        return []
    return [(src, d) for src, d in (("maps folder", EXTERNAL), ("my maps", OWN)) if d]


def candidates(sub, name, builtin_dir):
    """[(source, path)] in the order to try: the maps folder, my maps, then the built-in template."""
    out = [(src, os.path.join(d, sub, name) if sub else os.path.join(d, name)) for src, d in folders()]
    out.append(("template", os.path.join(builtin_dir, name)))
    return out


def builtin_dirs():
    """The built-in maps, grids and places folders (as artmode.render and artmode.places use them)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return (os.environ.get("ATLAS_MAPS", os.path.join(os.path.dirname(here), "renders")),
            os.environ.get("ATLAS_GRIDS", os.path.join(here, "grids")),
            os.environ.get("ATLAS_PLACES", os.path.join(here, "places")))


def available(map_id):
    """Whether a map can be shown: its day and night pictures, places and grid each exist in some
    source. Only that they exist; a bad one is still skipped, with a note, when it is loaded."""
    maps, grids, places = builtin_dirs()
    need = [("", f"{map_id}_4k.jpg", maps), ("", f"{map_id}N_4k.jpg", maps),
            ("places", f"{map_id}.json", places), ("grids", f"{map_id}.npz", grids)]
    return all(any(os.path.isfile(p) for _, p in candidates(sub, name, d)) for sub, name, d in need)


def reset():
    SOURCES.clear()
    del PROBLEMS[:]
