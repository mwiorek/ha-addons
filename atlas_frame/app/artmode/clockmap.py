"""The World (clock), W1Z: one map id in the rotation that shows whichever of its versions matches today's clocks.

The clock map is drawn for three days of the year, each a map of its own (side-loaded, never built in):
    W1ZW  northern winter  (the clocks of 22 November 2026: the north on standard time, the south on summer time)
    W1ZS  northern summer  (1 July 2026: the north on summer time, the south on standard time)
    W1ZM  the mixed weeks  (20 March 2026: North America and the south on summer time, Europe not yet)
At each push W1Z resolves to one of those that is installed. Add-on option `clock_version`: "current" (default) picks
the version whose clocks match today's best, compared over the regions that change their clocks; "winter", "summer"
or "mixed" pins one (falling back to "current" if that one is not installed).
"""
import datetime as dt
from zoneinfo import ZoneInfo

AUTO = "W1Z"
VARIANTS = {"W1ZW": "2026-11-22", "W1ZS": "2026-07-01", "W1ZM": "2026-03-20"}
PINNED = {"winter": "W1ZW", "summer": "W1ZS", "mixed": "W1ZM"}
NAMES = {"W1Z": "The World (clock)", "W1ZW": "The World (clock, northern winter)",
         "W1ZS": "The World (clock, northern summer)", "W1ZM": "The World (clock, mixed weeks)"}
# the regions that change their clocks, weighted by how much of the map they are
KEY_ZONES = {"America/New_York": 3, "America/Chicago": 2, "Europe/Paris": 3, "Europe/London": 1,
             "Australia/Sydney": 2, "Pacific/Auckland": 1, "America/Santiago": 1, "Africa/Cairo": 1,
             "Asia/Jerusalem": 1, "Africa/Casablanca": 1}


def _offsets(day):
    t = dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.timezone.utc)
    return {z: t.astimezone(ZoneInfo(z)).utcoffset() for z in KEY_ZONES}


def mismatch(today, variant):
    """Weighted count of key regions whose clocks differ between `today` (a date) and the variant's day."""
    a, b = _offsets(today), _offsets(dt.date.fromisoformat(VARIANTS[variant]))
    return sum(w for z, w in KEY_ZONES.items() if a[z] != b[z])


def pick(today, have, version="current"):
    """The variant to show on `today` among the installed ones (`have`), or None if none is installed."""
    have = [v for v in VARIANTS if v in have]
    if not have:
        return None
    pinned = PINNED.get((version or "current").strip().lower())
    if pinned in have:
        return pinned
    return min(have, key=lambda v: (mismatch(today, v), list(VARIANTS).index(v)))


def resolve(map_id, when, version, available):
    """The map to render for rotation entry `map_id`: W1Z becomes its version for `when` (a datetime); any other id
    is itself. `available(id)` says whether a map's files are there."""
    if map_id != AUTO:
        return map_id
    return pick(when.date(), [v for v in VARIANTS if available(v)], version) or map_id


def available(available_fn):
    """Whether W1Z can be shown: any of its versions installed."""
    return any(available_fn(v) for v in VARIANTS)
