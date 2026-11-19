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


def home_reading(hass, home, entities):
    """One reading at home from Home Assistant sensor entities, or None if none is configured or
    readable. entities: {"temperature": "sensor.x", "pressure": ..., "wind_speed": ..., "wind_from": ...}.
    Units are taken as the sensors give them; set the sensors to deg C, hPa and m/s."""
    r = {"name": "Home", "lat": home[0], "lon": home[1], "source": "home assistant"}
    for key, entity in (entities or {}).items():
        if not entity:
            continue
        st = hass.state(entity)
        try:
            r[key] = float(st["state"])
        except (TypeError, KeyError, ValueError):
            continue
    return r if len(r) > 4 else None


# ---- the home weather entity (weather.forecast_home, Met.no by default) for the legend ----
WIND_TO_MS = {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444, "ft/s": 0.3048}
PRESSURE_TO_HPA = {"hPa": 1.0, "mbar": 1.0, "Pa": 0.01, "kPa": 10.0, "inHg": 33.8639, "mmHg": 1.33322,
                   "psi": 68.9476, "cbar": 10.0}
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
    """The legend's reading from a Home Assistant weather entity, in deg C, hPa and m/s, with the
    pressure's three-hour change from samples the add-on keeps itself (`samples`, a list of
    [time, hPa] that the caller persists)."""

    def __init__(self, hass, entity="weather.forecast_home", samples=None):
        self.hass, self.entity = hass, entity
        self.samples = samples if samples is not None else []

    def _attrs(self):
        st = self.hass.state(self.entity)
        if not st:
            raise LookupError(f"{self.entity} not found in Home Assistant")
        return st.get("attributes", {})

    def sample(self, now):
        """Record the pressure now if the last sample is old enough; keep four hours."""
        if self.samples and now - self.samples[-1][0] < SAMPLE_EVERY:
            return
        a = self._attrs()
        if a.get("pressure") is None:
            return
        self.samples.append([now, float(a["pressure"]) * PRESSURE_TO_HPA.get(a.get("pressure_unit", "hPa"), 1.0)])
        del self.samples[:-int(4 * 3600 / SAMPLE_EVERY) - 2]

    def change_3h(self, now, hpa):
        """hPa change over the last three hours, or None without a sample from then (within 45 min)."""
        if not self.samples:
            return None
        t0, p0 = min(self.samples, key=lambda s: abs(s[0] - (now - TREND_WINDOW)))
        return hpa - p0 if abs(t0 - (now - TREND_WINDOW)) <= 2700 else None

    def reading(self, now):
        a = self._attrs()
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
            r["pressure_change_3h"] = self.change_3h(now, r["pressure"])
        if "temperature" in r:
            app = a.get("apparent_temperature")
            if app is not None:
                app = float(app)
                if str(a.get("temperature_unit", "°C")).endswith("F"):
                    app = (app - 32) * 5 / 9
                r["feels_like"] = app
            else:
                r["feels_like"] = feels_like(r["temperature"], r.get("humidity"), r.get("wind_speed"))
        return r
