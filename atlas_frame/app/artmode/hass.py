"""Home Assistant's REST API from inside an add-on (homeassistant_api: true gives SUPERVISOR_TOKEN).
Standard library only."""
import json
import os
import urllib.error
import urllib.request

API = os.environ.get("ATLAS_HA_API", "http://supervisor/core/api")


class Hass:
    def __init__(self, api=API, token=None, timeout=10):
        self.api, self.timeout = api.rstrip("/"), timeout
        self.token = token or os.environ.get("SUPERVISOR_TOKEN", "")

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.api}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode() or "null")

    def state(self, entity_id):
        """The entity's state object, or None if it does not exist."""
        try:
            return self._call("GET", f"/states/{entity_id}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def set_state(self, entity_id, state, attributes=None):
        """Show a value in Home Assistant (a status entity owned by the add-on)."""
        return self._call("POST", f"/states/{entity_id}", {"state": state, "attributes": attributes or {}})

    def fire_event(self, event_type, data=None):
        """Fire an event on Home Assistant's bus, for automations to pick up."""
        return self._call("POST", f"/events/{event_type}", data or {})

    def config(self):
        """Home Assistant's configuration: latitude, longitude, location_name, time_zone, ..."""
        return self._call("GET", "/config")

    def location(self):
        """(lat, lon) of the home set in Home Assistant."""
        c = self.config()
        return float(c["latitude"]), float(c["longitude"])
