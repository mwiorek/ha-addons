"""Data for the map layers: current weather at each map's places (Open-Meteo), and readings from
your own Home Assistant sensors at home. Standard library only.

A reading is a dict: name, lat, lon, and any of temperature (deg C), pressure (hPa, at sea level),
wind_speed (m/s), wind_from (deg, the direction the wind blows from), plus "source". Places from
artmode/places.py also carry their 4K `dot` and label `box`.
"""
import json
import time
import urllib.parse
import urllib.request

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
FIELDS = {"temperature_2m": "temperature", "pressure_msl": "pressure",
          "wind_speed_10m": "wind_speed", "wind_direction_10m": "wind_from"}


class OpenMeteo:
    """Current conditions for many places in one request. Free, no key; data updates about every
    15 minutes, so results are cached per map for `ttl` seconds. Only the places' coordinates
    (public city positions) are sent."""

    def __init__(self, ttl=900, timeout=15, fetch=None):
        self.ttl, self.timeout = ttl, timeout
        self._fetch = fetch or self._http
        self._cache = {}

    def _http(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "atlas-frame/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def readings(self, map_id, places, now=None):
        now = time.time() if now is None else now
        hit = self._cache.get(map_id)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        if not places:
            return []
        q = urllib.parse.urlencode({
            "latitude": ",".join(f"{p['lat']:.3f}" for p in places),
            "longitude": ",".join(f"{p['lon']:.3f}" for p in places),
            "current": ",".join(FIELDS), "wind_speed_unit": "ms", "timezone": "GMT"})
        body = self._fetch(f"{OPEN_METEO}?{q}")
        rows = body if isinstance(body, list) else [body]
        out = []
        for p, row in zip(places, rows):
            cur = (row or {}).get("current") or {}
            r = dict(p, source="open-meteo")
            for k, name in FIELDS.items():
                if cur.get(k) is not None:
                    r[name] = float(cur[k])
            out.append(r)
        self._cache[map_id] = (now, out)
        return out


# ---- the home weather entity (weather.forecast_home, Met.no by default) for the legend ----
WIND_TO_MS = {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444, "ft/s": 0.3048}
PRESSURE_TO_HPA = {"hPa": 1.0, "mbar": 1.0, "Pa": 0.01, "kPa": 10.0, "inHg": 33.8639, "mmHg": 1.33322,
                   "psi": 68.9476, "cbar": 10.0}
SENSOR_KEYS = ("temperature", "pressure", "wind_speed", "wind_from")
COMPASS = {d: i * 22.5 for i, d in enumerate("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}


def sensor_value(key, st):
    """A sensor's state in the add-on's units (deg C, hPa, m/s, degrees), from its unit_of_measurement; None when
    it is missing, unavailable or not a number. A sensor without a unit is taken as already in those units."""
    if not st:
        return None
    raw = str(st.get("state", "")).strip()
    unit = str((st.get("attributes") or {}).get("unit_of_measurement") or "").strip()
    if key == "wind_from" and raw.upper() in COMPASS:
        return COMPASS[raw.upper()]
    try:
        v = float(raw)
    except ValueError:
        return None
    if v != v:                                          # NaN
        return None
    if key == "temperature":
        if unit.endswith("F"):
            return (v - 32) * 5 / 9
        if unit == "K":
            return v - 273.15
        return v
    if key == "pressure":
        return v * PRESSURE_TO_HPA.get(unit, 1.0)
    if key == "wind_speed":
        return v * WIND_TO_MS.get(unit, 1.0)
    return v


def home_reading(hass, home, entities):
    """One reading at home from Home Assistant sensor entities, or None if none is configured or
    readable. entities: {"temperature": "sensor.x", "pressure": ..., "wind_speed": ..., "wind_from": ...}.
    Each value is converted from the sensor's own unit_of_measurement (sensor_value)."""
    r = {"name": "Home", "lat": home[0], "lon": home[1], "source": "home assistant"}
    for key, entity in (entities or {}).items():
        if not entity or key not in SENSOR_KEYS:
            continue
        v = sensor_value(key, hass.state(entity))
        if v is not None:
            r[key] = v
    return r if len(r) > 4 else None


TREND_WINDOW = 3 * 3600         # the barometer's tendency is read over three hours
SAMPLE_EVERY = 300              # seconds between pressure samples


def feels_like(t, humidity=None, wind_ms=None):
    """Apparent temperature (deg C), the way weather services report it: wind chill in the cold
    (at or below 10 deg C with wind above 4.8 km/h, the North American / Canadian formula), the heat
    index in the heat (27 deg C and up, 40 % humidity or more, the Rothfusz regression), otherwise
    the air temperature itself."""
    v = (wind_ms or 0.0) * 3.6
    if t <= 10 and v > 4.8:
        p = v ** 0.16
        return 13.12 + 0.6215 * t - 11.37 * p + 0.3965 * t * p
    if t >= 27 and humidity is not None and humidity >= 40:
        f, r = t * 9 / 5 + 32, humidity
        hi = (-42.379 + 2.04901523 * f + 10.14333127 * r - 0.22475541 * f * r - 0.00683783 * f * f
              - 0.05481717 * r * r + 0.00122874 * f * f * r + 0.00085282 * f * r * r - 0.00000199 * f * f * r * r)
        return (hi - 32) * 5 / 9
    return t


class HomeWeather:
    """The legend's reading, in deg C, hPa and m/s: your own home sensors where the add-on has them
    (`home_sensors`, as home_reading reads them), the Home Assistant weather entity for the rest. The
    pressure's three-hour change comes from samples the add-on keeps itself (`samples`, a list of
    [time, hPa, source] that the caller persists), always of the pressure the legend shows."""

    def __init__(self, hass, entity="weather.forecast_home", samples=None):
        self.hass, self.entity = hass, entity
        self.samples = samples if samples is not None else []

    def _attrs(self):
        st = self.hass.state(self.entity)
        if not st:
            raise LookupError(f"{self.entity} not found in Home Assistant")
        return st.get("attributes", {})

    def due(self, now):
        """Whether a pressure sample is due (so the caller reads a sensor only then)."""
        return not self.samples or now - self.samples[-1][0] >= SAMPLE_EVERY

    def sample(self, now, hpa=None):
        """Record the pressure now if the last sample is old enough; keep four hours. hpa: the home
        sensor's pressure, when the add-on has one (the legend then shows it); otherwise the weather
        entity's. A change of source starts the samples again: a trend from one barometer to another
        would be the difference between two instruments, not the weather."""
        src = "sensor" if hpa is not None else "entity"
        if self.samples and (self.samples[-1][2:3] or ["entity"])[0] != src:
            del self.samples[:]
        if self.samples and now - self.samples[-1][0] < SAMPLE_EVERY:
            return
        if hpa is None:
            a = self._attrs()
            if a.get("pressure") is None:
                return
            hpa = float(a["pressure"]) * PRESSURE_TO_HPA.get(a.get("pressure_unit", "hPa"), 1.0)
        self.samples.append([now, float(hpa), src])
        del self.samples[:-int(4 * 3600 / SAMPLE_EVERY) - 2]

    def change_3h(self, now, hpa):
        """hPa change over the last three hours, or None without a sample from then (within 45 min)."""
        if not self.samples:
            return None
        t0, p0 = min(self.samples, key=lambda s: abs(s[0] - (now - TREND_WINDOW)))[:2]    # [t, hPa(, source)]
        return hpa - p0 if abs(t0 - (now - TREND_WINDOW)) <= 2700 else None

    def reading(self, now, home=None):
        """home: a home_reading (your sensors); its values win over the weather entity's. Without
        the weather entity the sensors alone make the reading."""
        try:
            a = self._attrs()
        except LookupError:
            if not home:
                raise
            a = {}
        r = {}
        t = a.get("temperature")
        if t is not None:
            t = float(t)
            if str(a.get("temperature_unit", "°C")).endswith("F"):
                t = (t - 32) * 5 / 9
            r["temperature"] = t
        if a.get("humidity") is not None:
            r["humidity"] = float(a["humidity"])
        if a.get("wind_speed") is not None:
            r["wind_speed"] = float(a["wind_speed"]) * WIND_TO_MS.get(a.get("wind_speed_unit", "km/h"), 1 / 3.6)
        if a.get("wind_bearing") is not None:
            try:
                r["wind_from"] = float(a["wind_bearing"])
            except (TypeError, ValueError):
                pass
        if a.get("pressure") is not None:
            r["pressure"] = float(a["pressure"]) * PRESSURE_TO_HPA.get(a.get("pressure_unit", "hPa"), 1.0)
        mine = [k for k in SENSOR_KEYS if (home or {}).get(k) is not None]
        for k in mine:                                  # your own sensors win
            r[k] = float(home[k])
        r["from_sensors"] = mine
        if "pressure" in r:
            r["pressure_change_3h"] = self.change_3h(now, r["pressure"])
        if "temperature" in r:
            app = a.get("apparent_temperature")
            if "temperature" in mine or "wind_speed" in mine:
                app = None                              # the model's feels-like belongs to the model's air
            if app is not None:
                app = float(app)
                if str(a.get("temperature_unit", "°C")).endswith("F"):
                    app = (app - 32) * 5 / 9
                r["feels_like"] = app
            else:
                r["feels_like"] = feels_like(r["temperature"], r.get("humidity"), r.get("wind_speed"))
        return r
