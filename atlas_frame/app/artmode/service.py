"""The add-on's loop: every few minutes, render the next map, lit for the moment, and hand it to the
outputs: the picture files (option `output_files`, artmode/outputs.py) always, and the Frame while it
is in Art Mode. Controls are Home Assistant helpers (ha-addon/atlas_frame/atlas_frame_package.yaml);
the add-on reports back on sensor.atlas_frame and fires `atlas_frame_rendered` after each push.

    python -m artmode.service          # in the add-on; reads /data/options.json

Each push: render the next map in the rotation (sun, moon, data layers), write it to every output
file, then (Frame in Art Mode) upload it, select it, and delete the add-on's own earlier uploads. It
never wakes a TV in standby, never pushes to the TV while it shows anything but Art Mode, and never
deletes pictures it did not upload.
"""
import json
import os
import re
import time
import traceback
from datetime import datetime, timezone

from . import clockmap, files, layers, legend, outputs, packs, places, render, sources

DATA = os.environ.get("ATLAS_DATA", "/data")
TICK = 5                    # seconds between looks at the controls
ART_POLL = 15               # seconds between asking the TV whether it is in Art Mode
RETRY = 60                  # seconds before trying again after a failed push

MODES = {"Follow the sun": "follow", "Home light": "home", "Hold day": "day", "Hold dark": "night"}
ALL_MAPS = ["W1", "W1P", "W1T", "W1L", "W1S", "W1G", "W1C", "W1U", "W1Z", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
            "R13", "R14", "R15", "R16"]
DEFAULT_MAPS = list(ALL_MAPS)          # the rotation when the helper names none; the forms below join only by name
NAMES = {"W1": "The World", "W1P": "The World (population)", "W1T": "The World (temperature)", "W1L": "The World (temperature now)", "W1S": "The World (snow and ice now)", "W1G": "The World (economic output)", "W1C": "The World (GDP per person)", "W1U": "The World (land cover)", "R1": "Europe", "R2": "Asia", "R3": "Africa", "R4": "North America",
         "R5": "South America", "R6": "Oceania", "R7": "Scandinavia", "R8": "Northern Africa",
         "R9": "The Middle East", "R10": "East Asia", "R11": "United States", "R12": "Southern Europe",
         "R13": "Southern Africa", "R14": "Indian Subcontinent", "R15": "British Isles",
         "R16": "Central America"}
# side-loaded forms of a map: <id>P (population), <id>T (temperature), <id>L (temperature now)
FORMS = {"P": "population", "T": "temperature", "L": "temperature now"}
for _r in [m for m in ALL_MAPS if m.startswith("R")]:
    for _f, _what in FORMS.items():
        NAMES[_r + _f] = f"{NAMES[_r]} ({_what})"
ALL_MAPS += [m + f for m in ALL_MAPS if m.startswith("R") for f in FORMS]
# snow and ice now, laid over the political map (artmode/live.py, NOAA IMS): Europe only among the regions
SNOW_REGIONS = ["R1"]
for _r in SNOW_REGIONS:
    NAMES[_r + "S"] = f"{NAMES[_r]} (snow and ice now)"
ALL_MAPS += [r + "S" for r in SNOW_REGIONS]
# The World (clock): W1Z in the rotation shows the version for today's clocks (artmode/clockmap.py); the versions
# themselves can be named too
NAMES.update(clockmap.NAMES)
ALL_MAPS += list(clockmap.VARIANTS)

# words for sets of maps in the helper, so the rotation need not spell out every id: `world,regions,-R11`
_REGIONS = [m for m in DEFAULT_MAPS if m.startswith("R")]
GROUPS = {
    "WORLD": [m for m in DEFAULT_MAPS if m.startswith("W")],
    "REGIONS": _REGIONS,
    "POPULATION": ["W1P"] + [r + "P" for r in _REGIONS],
    "TEMPERATURE": ["W1T"] + [r + "T" for r in _REGIONS],
    "LIVE": ["W1L"] + [r + "L" for r in _REGIONS],
    "SNOW": ["W1S"] + [r + "S" for r in SNOW_REGIONS],
    "GDP": ["W1G", "W1C"],                       # the two economic Worlds: output per area, GDP per person
    "CLOCK": [clockmap.AUTO],
}
GROUPS["ALL"] = [m for m in ALL_MAPS if m not in clockmap.VARIANTS]
GROUP_HELP = {"all": "every map (the clock as W1Z)", "installed": "every map whose files are installed now",
              "<place>:<versions>": "a row of the matrix, e.g. R7:BPT (B the map, P population, T temperature, "
                                    "L temperature now, S snow and ice now, G economic output, C GDP per person, U land cover, Z clock)",
              "pack:<id>": "the maps of an installed map pack", "-<id or word>": "leave those out",
              **{k.lower(): ", ".join(v) for k, v in GROUPS.items() if k != "ALL"}}

# the rotation as a matrix, for the dashboard card (ha-addon/atlas_frame/www/atlas-frame-card.js): one row per place,
# one column per version, written `W1:BL R7:BPT` (W1 and W1L; R7, R7P and R7T); B is the map itself
PLACES = ["W1"] + _REGIONS
VERSIONS = {"B": "Map", "P": "Population", "T": "Temperature", "L": "Temperature now", "S": "Snow now", "G": "Economic output",
            "C": "GDP per person", "U": "Land cover", "Z": "Clock"}


def cell(place, version):
    """The map id of one cell, or None where that version of the place does not exist."""
    m = place if version == "B" else place + version
    return m if m in ALL_MAPS and m not in clockmap.VARIANTS else None


def _row(word):
    """`R7:BPT` -> [R7, R7P, R7T]; None if the word is not a row of the matrix or names a cell that does not exist."""
    place, _, versions = word.partition(":")
    if place not in PLACES or not versions:
        return None
    ids = [cell(place, v) for v in versions if v in VERSIONS]
    if len(ids) != len(versions) or None in ids:
        return None
    return ids


def expand(text, available, pack_maps=None):
    """The helper's text as a rotation: ids and words (GROUPS, `installed`, `pack:<id>`), separated by commas or
    spaces, any case; `-X` leaves X out wherever it appears. Returns (maps, named, unknown): the maps in order
    without repeats, the ids named one by one (only those are reported when not installed), and the words that
    matched nothing. `available(id)`: whether a map's files are there; `pack_maps`: {pack id: [map ids]}."""
    packs_up = {k.upper(): v for k, v in (pack_maps or {}).items()}

    def one(word):
        if word in ALL_MAPS:
            return [word]
        if ":" in word and not word.startswith("PACK:"):
            return _row(word)
        if word in GROUPS:
            return GROUPS[word]
        if word == "INSTALLED":
            return [m for m in GROUPS["ALL"]
                    if (clockmap.available(available) if m == clockmap.AUTO else available(m))]
        if word.startswith("PACK:") and word[5:] in packs_up:
            ids = [m for m in packs_up[word[5:]] if m in ALL_MAPS]
            return [clockmap.AUTO if m in clockmap.VARIANTS else m for m in ids]   # the clock as one entry
        return None

    maps, named, unknown, drop = [], [], [], set()
    for raw in re.split(r"[,\s]+", text or ""):
        word = raw.strip().upper()
        if not word or word == "-":
            continue
        out = word.startswith("-")
        ids = one(word.lstrip("-"))
        if ids is None:
            unknown.append(raw.strip())
        elif out:
            drop.update(ids)
        else:
            maps += [m for m in dict.fromkeys(ids) if m not in maps]
            if (word in ALL_MAPS or ":" in word and not word.startswith("PACK:")) and not out:
                named += [m for m in ids if m not in named]
    return [m for m in maps if m not in drop], [m for m in named if m not in drop], unknown

# the helpers, and what the add-on does when one is missing
H_ON, H_MODE, H_MINUTES = "input_boolean.atlas_frame_on", "input_select.atlas_frame_mode", "input_number.atlas_frame_minutes"
H_MAPS, H_NEXT = "input_text.atlas_frame_maps", "input_button.atlas_frame_next"
H_WEATHER, H_HOME = "input_boolean.atlas_frame_weather", "input_boolean.atlas_frame_home_readings"
H_LEGEND = "input_boolean.atlas_frame_legend"
STATUS = "sensor.atlas_frame"
EVENT = "atlas_frame_rendered"
DEFAULT_OUTPUT = "/share/atlas_frame/latest.jpg"
DEFAULTS = {H_ON: "on", H_MODE: "Follow the sun", H_MINUTES: "2", H_MAPS: ",".join(DEFAULT_MAPS),
            H_NEXT: "", H_WEATHER: "off", H_HOME: "off", H_LEGEND: "on"}


def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


class Controls:
    """The helpers' current values (defaults where a helper does not exist)."""

    def __init__(self, raw, available=None, pack_maps=None):
        self.raw = raw
        self.on = raw[H_ON] == "on"
        self.mode = MODES.get(raw[H_MODE], "follow")
        try:
            self.minutes = max(1.0, float(raw[H_MINUTES]))
        except ValueError:
            self.minutes = 2.0
        maps, self.named, self.unknown = expand(raw[H_MAPS], available or files.available, pack_maps)
        self.maps = maps or list(DEFAULT_MAPS)
        self.next = raw[H_NEXT]
        self.weather, self.home = raw[H_WEATHER] == "on", raw[H_HOME] == "on"
        self.legend = raw[H_LEGEND] == "on"

    def key(self):
        """What changes the picture: a change pushes a new one at once."""
        return (self.mode, tuple(self.maps), self.weather, self.home, self.legend)


class Store:
    """What survives a restart: the rotation position and the ids of our uploads on the TV."""

    def __init__(self, path):
        self.path = path
        try:
            self.d = json.load(open(path))
        except (OSError, ValueError):
            self.d = {}
        self.d.setdefault("index", -1)
        self.d.setdefault("uploaded", [])

    def save(self):
        tmp = self.path + ".tmp"
        json.dump(self.d, open(tmp, "w"))
        os.replace(tmp, self.path)


class Service:
    def __init__(self, hass, frame, options, store, clock=time.time, renderer=render.render_image,
                 weather=None, home=None, place=None, tz=None, files_out=()):
        self.hass, self.frame, self.opt, self.store = hass, frame, options, store   # frame: None = no TV
        self.files_out = list(files_out)    # outputs.FileOutput, written on every push
        self.clock, self.renderer = clock, renderer
        self.weather = weather or sources.OpenMeteo()
        self.home = home                    # (lat, lon), from Home Assistant at start
        self.place = options.get("legend_place") or place or "Home"      # the legend's heading
        self.tz = tz or "Europe/Stockholm"
        self.home_weather = sources.HomeWeather(hass, options.get("weather_entity") or "weather.forecast_home",
                                                store.d.setdefault("pressure", []))
        self.art = None                     # True / False / None (no answer)
        self.art_at = -1e9
        self.last_push = -1e9
        self.retry_at = 0
        self.seen_next = None
        self.seen_key = None
        self.status = {}
        self._have = {}                     # map id -> files there; looked at again on each push and pack change

    def have(self, map_id):
        if map_id not in self._have:
            self._have[map_id] = files.available(map_id)
        return self._have[map_id]

    # ---- reading the world ----
    def controls(self):
        raw = {}
        for entity, default in DEFAULTS.items():
            try:
                st = self.hass.state(entity)
            except Exception:
                st = None
            raw[entity] = str(st["state"]) if st else default
        pack_maps = {pid: i["licence"].get("maps", []) for pid, i in packs.INSTALLED.items()}
        return Controls(raw, self.have, pack_maps)

    def poll_art(self, now):
        if now - self.art_at < ART_POLL:
            return self.art
        self.art_at = now
        try:
            self.art = self.frame.art_mode()
        except Exception as e:              # off, standby or unreachable: leave it alone
            if self.art is not None:
                log(f"TV not answering ({e.__class__.__name__}); waiting")
            self.art = None
        return self.art

    # ---- one step ----
    def tick(self):
        now = self.clock()
        try:                                # licensed map packs dropped in (or taken out) since the last look
            if packs.scan():
                self._have.clear()
                log("maps installed: " + ", ".join(m for m in ALL_MAPS if self.have(m)))
        except Exception as e:
            log(f"map packs: {e}")
        c = self.controls()
        if c.legend and self.home_weather.due(now):   # the barometer's tendency needs samples, TV on or off
            try:                            # of the pressure the legend shows: your sensor's when you have one
                self.home_weather.sample(now, (self.home_sensors() or {}).get("pressure"))
            except Exception:
                pass
        if not c.on:
            return self.report("off", c)
        was = self.art
        art = self.poll_art(now) if self.frame else None
        to_tv = self.frame is not None and art is True
        if not to_tv and not self.files_out:
            return self.report("TV off" if art is None else "waiting for Art Mode", c)
        why = None
        if to_tv and was is not True:
            why = "Art Mode came on"
        elif self.seen_next is not None and c.next != self.seen_next:
            why = "next map"
        elif self.seen_key is not None and c.key() != self.seen_key:
            why = "controls changed"
        elif now - self.last_push >= c.minutes * 60:
            why = "time"
        self.seen_next, self.seen_key = c.next, c.key()
        if why and now >= self.retry_at:
            self.push(c, now, why, to_tv)
        return self.report(NAMES.get(self.status.get("map_id"), "waiting"), c)

    def installed(self, c):
        """The rotation as it can be shown now: the chosen maps whose files are all there (W1 is built
        in; the others are side-loaded), looked at again on every push so a map dropped into my maps
        or the maps folder joins at its turn. W1 if none of them is there."""
        have = [m for m in c.maps if (clockmap.available(self.have) if m == clockmap.AUTO else self.have(m))]
        missing = [m for m in c.maps if m not in have and m in c.named]   # a word's maps not there: just skipped
        self.status.update(maps_available=have or ["W1"],
                           maps_missing=(f"{', '.join(missing)} not installed: add them to the add-on's "
                                         "maps folder (DOCS, Maps)") if missing else None)
        return have or ["W1"]

    def push(self, c, now, why, to_tv=True):
        s = self.store
        self._have.clear()                  # a fresh look at the files on every push
        c = self.controls() if "INSTALLED" in c.raw[H_MAPS].upper() else c
        rotation = self.installed(c)
        s.d["index"] = (s.d["index"] + 1) % len(rotation)
        t = datetime.fromtimestamp(now, timezone.utc)
        map_id = clockmap.resolve(rotation[s.d["index"]], t, self.opt.get("clock_version"), files.available)
        files.reset()
        try:
            data, lay, notes = self.data_for(map_id, c)
            pic = self.renderer(map_id, t, c.mode, home=self.home or render.HOME, layers=lay, data=data)
            quality = int(self.opt.get("jpeg_quality") or 95)
            encoded = {}

            def as_(kind):                  # each encoding made once per push, only if wanted
                if kind not in encoded:
                    encoded[kind] = render.encode(pic, kind, quality)
                return encoded[kind]
            if self.renderer is render.render_image and render.LAYER_ERRORS:
                notes = "; ".join([n for n in [notes] + render.LAYER_ERRORS if n])
            if files.PROBLEMS:              # a side-loaded file skipped: the next source's copy was used
                notes = "; ".join([n for n in [notes] + files.PROBLEMS if n])
            pics = {k: f"{map_id}{n}_4k" for k, n in (("day", ""), ("night", "N"))}
            source = {k: f"{files.SOURCES[s]} ({files.KINDS.get(s)})" if s in files.SOURCES else None
                      for k, s in pics.items()}
            source.update(places=files.SOURCES.get(f"{map_id} places"), grid=files.SOURCES.get(f"{map_id} grid"))
            written, failed = [], []
            for out in self.files_out:      # one unwritable file never stops the others or the TV
                try:
                    out.write(as_(out.kind))
                    written.append(out)
                except Exception as e:
                    failed.append(f"{out.path}: {e.__class__.__name__}: {e}")
            if failed and not written and not to_tv:
                raise OSError("; ".join(failed))
            cid = None
            if to_tv:
                cid = self.frame.upload(as_("jpg"))
                if cid not in s.d["uploaded"]:
                    s.d["uploaded"].append(cid)
                s.save()                    # record it before anything else can fail
                self.frame.select(cid)
                self.cleanup(keep=cid)
            self.last_push, self.retry_at = now, 0
            self.status.update(map_id=map_id, pushed_at=t.isoformat(timespec="seconds"),
                               error="; ".join(failed) or None, notes=notes or None,
                               files_from={k: v for k, v in source.items() if v})
            from . import live
            if live.is_live(map_id):            # the live map: where its colours came from, and when
                self.status["live"] = live.status(map_id)
            where = [o.path for o in written] + ([f"TV as {cid}"] if cid else [])
            sizes = ", ".join(f"{k} {len(v) / 1e6:.1f} MB" for k, v in encoded.items())
            log(f"{map_id} {NAMES[map_id]} ({c.mode}, {why}) {sizes} to {', '.join(where)}")
            self.announce(map_id, c, t, written, cid)
        except Exception as e:
            s.d["index"] = (s.d["index"] - 1) % len(rotation)  # the same map again next time
            self.retry_at = now + RETRY
            self.status.update(error=f"{e.__class__.__name__}: {e}")
            log(f"push failed: {e}\n{traceback.format_exc(limit=3)}")
        s.save()

    def home_sensors(self):
        """Your own sensors at home (option home_sensors), in deg C, hPa and m/s, or None. The home dot and the
        legend both show these, so the two agree with each other and with the sensors themselves."""
        try:
            return sources.home_reading(self.hass, self.home or render.HOME, self.opt.get("home_sensors", {}))
        except Exception:
            return None

    def data_for(self, map_id, c):
        """Data and layers for this map, from the switched-on sources. A source that fails is left
        out of this picture (noted in the status), never blocking the push."""
        data, lay, notes = {}, [], []
        if c.weather:
            try:
                pl = places.load(map_id)
                data["weather"] = self.weather.readings(map_id, pl["places"], now=self.clock())
                data["boxes"] = pl["boxes"]
                lay.append(layers.Weather(show=self.opt.get("weather_show", ["temperature", "wind"])))
            except Exception as e:
                notes.append(f"weather left out: {e.__class__.__name__}")
        if c.home:
            try:
                r = self.home_sensors()
                if r:
                    data["home"] = r
                    lay.append(layers.Home())
                else:
                    notes.append("no home sensors set in the add-on options")
            except Exception as e:
                notes.append(f"home readings left out: {e.__class__.__name__}")
        if c.legend:
            try:
                spot = places.load(map_id).get("legend_at")
                if spot is None:
                    notes.append("no free corner for the legend on this map")
                else:
                    data["legend_at"] = spot
                    data["legend"] = {"reading": self.home_weather.reading(self.clock(), home=self.home_sensors()),
                                      "place": self.place, "tz": self.tz}
                    lay.append(legend.LegendLayer())
            except Exception as e:
                notes.append(f"legend left out: {e.__class__.__name__}: {e}")
        return data, lay, "; ".join(notes)

    def announce(self, map_id, c, t, written, cid):
        """Tell Home Assistant a new picture is out (event `atlas_frame_rendered`), so an automation
        can show it elsewhere, e.g. media_player.play_media with one of `media_ids`."""
        try:
            self.hass.fire_event(EVENT, {
                "map_id": map_id, "map": NAMES[map_id], "mode": c.mode,
                "pushed_at": t.isoformat(timespec="seconds"), "files": [o.path for o in written],
                "media_ids": [m for m in (o.media_id() for o in written) if m], "tv": cid is not None})
        except Exception as e:
            log(f"could not fire {EVENT}: {e}")

    def cleanup(self, keep):
        """Delete our earlier uploads; one that fails stays listed and is tried again next time."""
        left = []
        for cid in self.store.d["uploaded"]:
            if cid == keep:
                left.append(cid)
                continue
            try:
                self.frame.delete(cid)
            except Exception as e:
                log(f"could not delete {cid}: {e}")
                left.append(cid)
        self.store.d["uploaded"] = left

    def catalog(self):
        """Every map id the helper takes: {id: "name · where from"}, where from being built in, the pack that
        carries it, or not installed."""
        def where(m):
            if m == clockmap.AUTO:
                return "today's version of W1ZW, W1ZS, W1ZM" + ("" if clockmap.available(self.have) else
                                                               " · not installed")
            if not self.have(m):
                return "not installed"
            if files.built_in(m):
                return "built in"
            return "pack " + next((pid for pid, i in sorted(packs.INSTALLED.items())
                                   if m in i["licence"].get("maps", [])), "?")
        return {m: f"{NAMES[m]} · {where(m)}" for m in ALL_MAPS}

    def matrix(self):
        """For the dashboard card: the versions (columns), and per place (row) each cell that exists, with where its
        map comes from: built in, pack <id>, or not installed."""
        def status(m):
            if m == clockmap.AUTO:
                return "installed" if clockmap.available(self.have) else "not installed"
            if not self.have(m):
                return "not installed"
            return "built in" if files.built_in(m) else "pack " + next(
                (pid for pid, i in sorted(packs.INSTALLED.items()) if m in i["licence"].get("maps", [])), "?")
        rows = [{"id": p, "name": NAMES[p],
                 "cells": {v: {"map": m, "status": status(m)} for v in VERSIONS if (m := cell(p, v))}}
                for p in PLACES]
        used = [v for v in VERSIONS if any(v in r["cells"] for r in rows)]
        return {"versions": {v: VERSIONS[v] for v in used}, "places": rows, "helper": H_MAPS}

    def report(self, state, c):
        attrs = {"friendly_name": "Atlas Frame", "icon": "mdi:map", "mode": c.mode,
                 "minutes_per_map": c.minutes, "maps": c.maps, "art_mode": self.art,
                 "tv": self.frame is not None, "output_files": [o.path for o in self.files_out],
                 **{k: v for k, v in self.status.items() if v is not None}}
        if c.unknown:
            attrs["maps_unknown"] = (f"{', '.join(c.unknown)}: not a map id or word; see maps_catalog and "
                                     "map_words")
        attrs["maps_catalog"] = self.catalog()
        attrs["maps_matrix"] = self.matrix()
        attrs["map_words"] = GROUP_HELP
        pk = packs.summary()
        if pk["installed"] or pk["refused"]:          # who each map pack is licensed to, and any refused
            attrs["map_packs"] = pk
        if self.last_push > 0:
            attrs["next_push_at"] = datetime.fromtimestamp(self.last_push + c.minutes * 60, timezone.utc) \
                .isoformat(timespec="seconds")
        snapshot = (state, json.dumps(attrs, sort_keys=True, default=str))
        if snapshot != getattr(self, "_reported", None):
            try:
                self.hass.set_state(STATUS, state, attrs)
                self._reported = snapshot
            except Exception as e:
                log(f"could not update {STATUS}: {e}")
        return state


CARD = os.environ.get("ATLAS_CARD", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                  "www", "atlas-frame-card.js"))
HA_WWW = os.environ.get("ATLAS_HA_WWW", "/homeassistant/www")     # Home Assistant's /local


def install_card(src=CARD, www=HA_WWW):
    """Copy the dashboard card into Home Assistant's www folder (served as /local/atlas-frame-card.js), when it is
    not there or differs. Returns what it did, for the log."""
    if not os.path.isfile(src):
        return None
    if not os.path.isdir(os.path.dirname(www)):
        return f"dashboard card: {os.path.dirname(www)} not mapped, card not installed"
    dst = os.path.join(www, os.path.basename(src))
    new = open(src, "rb").read()
    try:
        if os.path.isfile(dst) and open(dst, "rb").read() == new:
            return "dashboard card: /local/atlas-frame-card.js up to date"
        os.makedirs(www, exist_ok=True)
        tmp = dst + ".tmp"
        open(tmp, "wb").write(new)
        os.replace(tmp, dst)
        return "dashboard card: installed /local/atlas-frame-card.js (add it as a dashboard resource once, DOCS)"
    except OSError as e:
        return f"dashboard card: could not write {dst}: {e}"


def main():
    from .frame import Frame
    from .hass import Hass
    opt = json.load(open(os.path.join(DATA, "options.json")))
    use_tv = bool(opt.get("tv_host")) and not opt.get("preview_only")
    try:
        files_out = outputs.parse(opt.get("output_files", [DEFAULT_OUTPUT]))
    except ValueError as e:
        raise SystemExit(str(e))
    if not use_tv and not files_out:
        raise SystemExit("nowhere to show the maps: set tv_host (the Frame's IP address) with "
                         "preview_only off, or add a path to output_files")
    files.TEMPLATES_ONLY = opt.get("maps_source") == "templates"
    folder = (opt.get("maps_folder") or "").strip()
    if files.TEMPLATES_ONLY:
        log("maps_source templates: only the built-in maps are used")
    else:
        if folder:
            files.EXTERNAL = folder
            if os.path.isdir(folder):
                log(f"maps folder {folder}: its maps are used first")
            else:
                log(f"maps folder {folder} not found (network storage not mounted?): skipped until it appears")
        if os.path.isdir(files.OWN):
            log(f"my maps: {files.OWN}")
        else:
            try:                            # make the drop-in folder, so it shows on the Samba share
                os.makedirs(files.OWN, exist_ok=True)
                log(f"my maps: {files.OWN} (empty; unzip a map pack there to add maps)")
            except OSError:
                pass
    if not files.TEMPLATES_ONLY:
        try:                                # the map pack inbox, so it shows on the Samba share
            os.makedirs(packs.INBOX, exist_ok=True)
        except OSError:
            pass
        packs.scan(force=True)
        log(f"map packs: {packs.INBOX}, " + (", ".join(f"{p['pack']} (licensed to {p['licensee']})"
                                                      for p in packs.summary()["installed"]) or "none installed"))
    log("maps installed: " + ", ".join(m for m in ALL_MAPS if files.available(m)))
    note = install_card()
    if note:
        log(note)
    hass = Hass()
    try:
        cfg = hass.config()
        home = float(cfg["latitude"]), float(cfg["longitude"])
        place, tz = cfg.get("location_name"), cfg.get("time_zone")
    except Exception as e:
        home, place, tz = render.HOME, None, None
        log(f"could not read Home Assistant's location ({e}); using {home}")
    frame = None
    if use_tv:
        frame = Frame(opt["tv_host"], token_file=os.path.join(DATA, "tv-token.txt"),
                      show=opt.get("select_show") or None)
    target = ", ".join(([f"TV {opt['tv_host']}"] if use_tv else []) + [o.path for o in files_out])
    svc = Service(hass, frame, opt, Store(os.path.join(DATA, "state.json")), home=home, place=place,
                  tz=tz, files_out=files_out)
    log(f"Atlas Frame started: {target}, home {home[0]:.2f}, {home[1]:.2f}")
    while True:
        try:
            svc.tick()
        except Exception as e:              # never let one bad step stop the loop
            log(f"step failed: {e}")
        time.sleep(TICK)


if __name__ == "__main__":
    main()
