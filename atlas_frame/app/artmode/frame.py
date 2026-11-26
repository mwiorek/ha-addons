"""The Frame's Art Mode over the local network, through the `samsungframetv` package (unofficial,
github.com/NickWaterton/samsung-tv-ws-api). Only the calls its README documents are used.

NOT YET RUN AGAINST A TV. Check on the first day: that `art_mode()` reads "on"/"off" without waking
a TV in standby, that `upload()` returns the new content id, and that `select(..., show=False)`
changes the picture while Art Mode is on. If the picture does not change, turn on the add-on option
`select_show` (or set ATLAS_SHOW=1).
"""
import os

SHOW = os.environ.get("ATLAS_SHOW", "0") == "1"


class Frame:
    """Connects on first use, not when made: the library asks the TV for its model year as soon as
    its object is built, and a TV in standby accepts the connection but never answers (seen: TLS
    handshake timeout on 8002), which would stop the add-on at start. Any failure drops the
    connection, so the next call starts afresh once the TV is back."""

    def __init__(self, host, token_file="/data/tv-token.txt", name="Atlas", timeout=20, show=None):
        self.show = SHOW if show is None else bool(show)
        self.host, self.token_file, self.name, self.timeout = host, token_file, name, timeout
        self._tv = None

    def _art(self):
        if self._tv is None:
            from samsungframetv import SamsungTVWS     # the samsungframetv package (a fork of samsungtvws)
            self._tv = SamsungTVWS(self.host, port=8002, token_file=self.token_file, name=self.name,
                                   timeout=self.timeout)
        return self._tv.art()

    def _call(self, fn):
        try:
            return fn(self._art())
        except Exception:
            self._tv = None                             # reconnect next time
            raise

    def art_mode(self):
        """True if the TV is on and showing Art Mode, False if on but not in Art Mode. Raises if
        the TV does not answer (off, standby or away): the caller then leaves it alone."""
        return str(self._call(lambda a: a.get_artmode())).lower() == "on"

    def upload(self, jpeg):
        """Upload a JPEG with no matte (the map fills the screen); returns its content id. JPEG, not
        PNG: the TV keeps its art as JPEG either way, and the upload stays a few MB."""
        cid = self._call(lambda a: a.upload(jpeg, file_type="JPEG", matte="none"))
        if not cid:
            raise RuntimeError("the TV did not confirm the upload")
        return cid

    def select(self, content_id):
        self._call(lambda a: a.select_image(content_id, show=self.show))

    def delete(self, content_id):
        self._call(lambda a: a.delete(content_id))

