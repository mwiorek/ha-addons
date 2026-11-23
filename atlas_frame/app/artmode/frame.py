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
    def __init__(self, host, token_file="/data/tv-token.txt", name="Atlas", timeout=20, show=None):
        self.show = SHOW if show is None else bool(show)
        from samsungframetv import SamsungTVWS     # the samsungframetv package (a fork of samsungtvws)
        self.tv = SamsungTVWS(host, port=8002, token_file=token_file, name=name, timeout=timeout)

    def art_mode(self):
        """True if the TV is on and showing Art Mode, False if on but not in Art Mode. Raises if
        the TV does not answer (off, standby or away): the caller then leaves it alone."""
        return str(self.tv.art().get_artmode()).lower() == "on"

    def upload(self, jpeg):
        """Upload a JPEG with no matte (the map fills the screen); returns its content id. JPEG, not
        PNG: the TV keeps its art as JPEG either way, and the upload stays a few MB."""
        cid = self.tv.art().upload(jpeg, file_type="JPEG", matte="none")
        if not cid:
            raise RuntimeError("the TV did not confirm the upload")
        return cid

    def select(self, content_id):
        self.tv.art().select_image(content_id, show=self.show)

    def delete(self, content_id):
        self.tv.art().delete(content_id)

