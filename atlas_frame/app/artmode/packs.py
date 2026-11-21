"""Licensed map packs: one .atlaspack file per purchase, dropped into a folder, installed by the add-on itself.

    /share/atlas_frame/packs/<anything>.atlaspack      where the owner puts it (Samba: share/atlas_frame/packs)
    /data/packs/<pack id>/                              where the add-on keeps it once its licence checks out

A pack is a zip of a map folder (pictures, places/, grids/, a live map's calibration) plus:
    licence.json   who it is licensed to, the map ids it covers, and the SHA-256 of every other file in the pack
    licence.sig    an Ed25519 signature of licence.json's exact bytes, by a key listed in pack_keys.json
    LICENCE.txt, NOTICE.txt, README.txt   the terms, the data credits, how to install

The add-on installs a pack only if the signature verifies and every file matches its hash (nothing added, nothing
swapped). A map that is not built into the add-on is shown only while an installed licence covers its id, wherever its
files come from (files.available), so copying a pack's pictures into a maps folder does not get round it. Removing the
.atlaspack removes the installed pack. This keeps honest use easy and makes a shared pack carry its owner's name (the
sensor shows who each licence is for); it is not copy protection: the code is open and a picture on a TV can be
photographed. Each picture also carries an invisible mark of its licensee, so a copy found elsewhere can be traced
(packs.py trace, on the machine that issues licences).
"""
import hashlib
import json
import os
import re
import shutil
import time
import zipfile

from . import ed25519

HERE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.environ.get("ATLAS_PACKS_IN", "/share/atlas_frame/packs")
DATA = os.environ.get("ATLAS_DATA", "/data")
KEYS = os.environ.get("ATLAS_PACK_KEYS", os.path.join(HERE, "pack_keys.json"))
EXT = ".atlaspack"
META = ("licence.json", "licence.sig")
SCAN_S = 30                       # seconds between looks at the inbox
INSTALLED = {}                    # pack id -> {"licence": {...}, "dir", "file", "stamp"}
PROBLEMS = {}                     # pack file name -> why it was not installed
_LAST = [0.0]


def installed_dir():
    return os.path.join(DATA, "packs")


def public_keys():
    """{key id: 32-byte public key} of the licence issuers this build trusts."""
    try:
        with open(KEYS, encoding="utf-8") as f:
            return {k["id"]: bytes.fromhex(k["public"]) for k in json.load(f).get("keys", [])}
    except (OSError, ValueError, KeyError):
        return {}


def check_licence(raw, sig, keys=None):
    """The licence dict if `raw` (licence.json's bytes) carries a valid signature by a trusted key, else raises."""
    keys = public_keys() if keys is None else keys
    if not keys:
        raise ValueError("this build trusts no licence key")
    lic = json.loads(raw.decode("utf-8"))
    pub = keys.get(lic.get("key_id"))
    if pub is None:
        raise ValueError(f"signed by an unknown key {lic.get('key_id')!r}")
    if not ed25519.verify(pub, raw, bytes.fromhex(sig.decode("ascii").strip())):
        raise ValueError("the licence signature does not verify")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", str(lic.get("pack_id", ""))):
        raise ValueError("bad pack id")
    return lic


def _safe(name):
    return not (name.startswith("/") or "\\" in name or any(part in ("", "..") for part in name.split("/")))


def install(path, keys=None):
    """Check the pack at `path` and unpack it into /data/packs/<pack id>/. Returns the licence; raises on any fault."""
    with zipfile.ZipFile(path) as z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        if not all(n in names for n in META):
            raise ValueError("no licence in the pack")
        lic = check_licence(z.read("licence.json"), z.read("licence.sig"), keys)
        want = lic.get("files") or {}
        extra = [n for n in names if n not in want and n not in META]
        if extra:
            raise ValueError(f"files the licence does not list: {', '.join(extra[:3])}")
        missing = [n for n in want if n not in names]
        if missing:
            raise ValueError(f"files missing: {', '.join(missing[:3])}")
        dest = os.path.join(installed_dir(), lic["pack_id"])
        tmp = dest + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        for n, digest in want.items():
            if not _safe(n):
                raise ValueError(f"bad file name {n!r}")
            h = hashlib.sha256()
            out = os.path.join(tmp, n)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    h.update(chunk)
                    dst.write(chunk)
            if h.hexdigest() != digest:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError(f"{n} is not the file the licence lists")
        for n in META:
            with open(os.path.join(tmp, n), "wb") as f:
                f.write(z.read(n))
    with open(os.path.join(tmp, ".source.json"), "w", encoding="utf-8") as f:
        json.dump({"file": os.path.basename(path), "stamp": _stamp(path)}, f)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return lic


def _stamp(path):
    st = os.stat(path)
    return [st.st_size, int(st.st_mtime)]


def _load_installed(keys):
    """What /data/packs holds (after a restart), each licence checked again."""
    INSTALLED.clear()
    root = installed_dir()
    if not os.path.isdir(root):
        return
    for pid in sorted(os.listdir(root)):
        d = os.path.join(root, pid)
        try:
            with open(os.path.join(d, "licence.json"), "rb") as f:
                raw = f.read()
            with open(os.path.join(d, "licence.sig"), "rb") as f:
                lic = check_licence(raw, f.read(), keys)
            with open(os.path.join(d, ".source.json"), encoding="utf-8") as f:
                src = json.load(f)
            INSTALLED[lic["pack_id"]] = {"licence": lic, "dir": d, "file": src["file"], "stamp": src["stamp"]}
        except Exception:                       # a half-installed or altered folder: not used
            shutil.rmtree(d, ignore_errors=True)


def scan(force=False, keys=None):
    """Install new or changed packs from the inbox, drop the ones whose file was removed. Cheap: a listing and a
    stat per pack, every SCAN_S seconds. Returns True when what is installed changed."""
    now = time.time()
    if not force and now - _LAST[0] < SCAN_S:
        return False
    _LAST[0] = now
    keys = public_keys() if keys is None else keys
    if not INSTALLED:
        _load_installed(keys)
    before = {k: v["stamp"] for k, v in INSTALLED.items()}
    files = {}
    if os.path.isdir(INBOX):
        files = {n: os.path.join(INBOX, n) for n in os.listdir(INBOX) if n.lower().endswith(EXT)}
    by_file = {v["file"]: k for k, v in INSTALLED.items()}
    for name, path in sorted(files.items()):
        pid = by_file.get(name)
        try:
            stamp = _stamp(path)
        except OSError:
            continue
        if pid and INSTALLED[pid]["stamp"] == stamp:
            continue
        if PROBLEMS.get(name, (None,))[0] == stamp:
            continue                            # already refused as it is: not again every scan
        try:
            lic = install(path, keys)
            INSTALLED[lic["pack_id"]] = {"licence": lic, "dir": os.path.join(installed_dir(), lic["pack_id"]),
                                         "file": name, "stamp": stamp}
            PROBLEMS.pop(name, None)
            print(f"pack {name}: installed {lic['pack_id']} for {lic.get('licensee')}: {', '.join(lic.get('maps', []))}",
                  flush=True)
        except Exception as e:
            PROBLEMS[name] = (stamp, f"{e.__class__.__name__}: {e}"[:200])
            print(f"pack {name}: not installed, {PROBLEMS[name][1]}", flush=True)
    for pid, info in list(INSTALLED.items()):   # its file was taken out of the inbox: the pack goes too
        if info["file"] not in files:
            shutil.rmtree(info["dir"], ignore_errors=True)
            del INSTALLED[pid]
            print(f"pack {info['file']}: removed", flush=True)
    for name in [n for n in PROBLEMS if n not in files]:
        del PROBLEMS[name]
    return {k: v["stamp"] for k, v in INSTALLED.items()} != before


def folders():
    """[(source, folder)] of the installed packs, for files.folders."""
    return [("pack " + pid, info["dir"]) for pid, info in sorted(INSTALLED.items())]


def licensed(map_id):
    return any(map_id in info["licence"].get("maps", []) for info in INSTALLED.values())


def summary():
    """For the sensor: each installed pack, who it is licensed to, its maps; and the packs refused, with why."""
    return {"installed": [{"pack": pid, "licensee": i["licence"].get("licensee"), "licence": i["licence"].get("licence_id"),
                           "maps": i["licence"].get("maps", [])} for pid, i in sorted(INSTALLED.items())],
            "refused": {n: why for n, (_s, why) in PROBLEMS.items()}}


def reset():
    INSTALLED.clear()
    PROBLEMS.clear()
    _LAST[0] = 0.0
