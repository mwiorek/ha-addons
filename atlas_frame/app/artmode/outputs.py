"""Picture files the add-on keeps up to date beside (or instead of) the Frame: the add-on option
`output_files`. Each push writes the picture to every path, whatever the Frame is doing, so a
player that loops a file (VLC over Samba on another TV), a Local File camera, or a cast automation
always finds the map of the moment. The extension picks the encoding: `.png` lossless (about 11 MB),
`.jpg` at the option `jpeg_quality` (about 3.5 MB at 95). List both to compare them on a screen.

    /share/...   the Samba share's `share` folder (the default, /share/atlas_frame/latest.jpg)
    /media/...   Home Assistant's media folder: also reachable as media-source://media_source/local/...,
                 which media_player.play_media can cast to Chromecast, Google TV, DLNA and the like

A file is replaced in one step (written beside it, then renamed), so a reader never sees half a
picture.
"""
import os

MEDIA = "/media"


class FileOutput:
    def __init__(self, path):
        self.path = path
        self.kind = "png" if path.lower().endswith(".png") else "jpg"

    def write(self, data):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, self.path)

    def media_id(self):
        """The file's Home Assistant media-source id if it is in the media folder, else None."""
        rel = os.path.relpath(self.path, MEDIA)
        if rel.startswith(".."):
            return None
        return "media-source://media_source/local/" + rel.replace(os.sep, "/")


def parse(paths):
    """FileOutputs for the option's paths: blanks dropped, each path once, relative paths refused."""
    out, seen = [], set()
    for p in paths or []:
        p = str(p).strip()
        if not p or p in seen:
            continue
        if not os.path.isabs(p):
            raise ValueError(f"output file {p!r} is not a full path (e.g. /share/atlas_frame/latest.jpg)")
        if not p.lower().endswith((".jpg", ".jpeg", ".png")):
            raise ValueError(f"output file {p!r} must end in .jpg or .png")
        seen.add(p)
        out.append(FileOutput(p))
    return out
