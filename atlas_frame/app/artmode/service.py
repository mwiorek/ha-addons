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
import time
import traceback
from datetime import datetime, timezone

from . import files, layers, legend, outputs, places, render, sources

DATA = os.environ.get("ATLAS_DATA", "/data")
TICK = 5                    # seconds between looks at the controls
ART_POLL = 15               # seconds between asking the TV whether it is in Art Mode
RETRY = 60                  # seconds before trying again after a failed push

MODES = {"Follow the sun": "follow", "Home light": "home", "Hold day": "day", "Hold dark": "night"}
ALL_MAPS = ["W1", "W1P", "W1T", "W1L", "W1G", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
            "R13", "R14", "R15", "R16"]
NAMES = {"W1": "The World", "W1P": "The World (population)", "W1T": "The World (temperature)", "W1L": "The World (temperature now)", "W1G": "The World (economic output)", "R1": "Europe", "R2": "Asia", "R3": "Africa", "R4": "North America",
         "R5": "South America", "R6": "Oceania", "R7": "Scandinavia", "R8": "Northern Africa",
         "R9": "The Middle East", "R10": "East Asia", "R11": "United States", "R12": "Southern Europe",
         "R13": "Southern Africa", "R14": "Indian Subcontinent", "R15": "British Isles",
         "R16": "Central America"}

# the helpers, and what the add-on does when one is missing
H_ON, H_MODE, H_MINUTES = "input_boolean.atlas_frame_on", "input_select.atlas_frame_mode", "input_number.atlas_frame_minutes"
H_MAPS, H_NEXT = "input_text.atlas_frame_maps", "input_button.atlas_frame_next"
H_WEATHER, H_HOME = "input_boolean.atlas_frame_weather", "input_boolean.atlas_frame_home_readings"
H_LEGEND = "input_boolean.atlas_frame_legend"
STATUS = "sensor.atlas_frame"
EVENT = "atlas_frame_rendered"
DEFAULT_OUTPUT = "/share/atlas_frame/latest.jpg"
DEFAULTS = {H_ON: "on", H_MODE: "Follow the sun", H_MINUTES: "2", H_MAPS: ",".join(ALL_MAPS),
            H_NEXT: "", H_WEATHER: "off", H_HOME: "off", H_LEGEND: "on"}


def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


class Controls:
    """The helpers' current values (defaults where a helper does not exist)."""

    def __init__(self, raw):
        self.raw = raw
        self.on = raw[H_ON] == "on"
        self.mode = MODES.get(raw[H_MODE], "follow")
        try:
            self.minutes = max(1.0, float(raw[H_MINUTES]))
        except ValueError:
            self.minutes = 2.0
        wanted = [m.strip().upper() for m in raw[H_MAPS].split(",")]
        self.maps = [m for m in wanted if m in ALL_MAPS] or list(ALL_MAPS)
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

    # ---- reading the world ----
    def controls(self):
        raw = {}
        for entity, default in DEFAULTS.items():
            try:
                st = self.hass.state(entity)
            except Exception:
                st = None
            raw[entity] = str(st["state"]) if st else default
        return Controls(raw)

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
        c = self.controls()
        if c.legend:                        # the barometer's tendency needs samples, TV on or off
            try:
                self.home_weather.sample(now)
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
        have = [m for m in c.maps if files.available(m)]
        missing = [m for m in c.maps if m not in have]
        self.status.update(maps_available=have or ["W1"],
                           maps_missing=(f"{', '.join(missing)} not installed: add them to the add-on's "
                                         "maps folder (DOCS, Maps)") if missing else None)
        return have or ["W1"]

    def push(self, c, now, why, to_tv=True):
        s = self.store
        rotation = self.installed(c)
        s.d["index"] = (s.d["index"] + 1) % len(rotation)
        map_id = rotation[s.d["index"]]
        t = datetime.fromtimestamp(now, timezone.utc)
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
                r = sources.home_reading(self.hass, self.home or render.HOME, self.opt.get("home_sensors", {}))
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
                    data["legend"] = {"reading": self.home_weather.reading(self.clock()),
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

    def report(self, state, c):
        attrs = {"friendly_name": "Atlas Frame", "icon": "mdi:map", "mode": c.mode,
                 "minutes_per_map": c.minutes, "maps": c.maps, "art_mode": self.art,
                 "tv": self.frame is not None, "output_files": [o.path for o in self.files_out],
                 **{k: v for k, v in self.status.items() if v is not None}}
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
    log("maps installed: " + ", ".join(m for m in ALL_MAPS if files.available(m)))
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
