"""Finding every song the DJ already has: VirtualDJ's own database plus any music folders."""
import json
import os
import string
import struct
import xml.etree.ElementTree as ET

from . import paths
from .textnorm import parse_filename

AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".wma", ".opus", ".alac"}
VIDEO = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".wmv", ".mpg", ".webm"}
MEDIA = AUDIO | VIDEO


def make_entry(path, artist="", title="", length=None, in_vdj=False):
    stem = os.path.splitext(os.path.basename(path))[0]
    fa, ft = parse_filename(stem)
    return {"path": path, "artist": (artist or "").strip(), "title": (title or "").strip(),
            "fn_artist": fa, "fn_title": ft, "length": length, "in_vdj": in_vdj,
            "folder": os.path.basename(os.path.dirname(path)),
            "video": os.path.splitext(path)[1].lower() in VIDEO}


# ---------- VirtualDJ database ----------

def read_vdj_database(xml_path, drive_root=None):
    """database.xml -> entries. Drive databases (X:\\VirtualDJ\\database.xml) can hold paths without
    the drive letter, so those get drive_root put in front."""
    out = []
    try:
        for _, el in ET.iterparse(xml_path, events=("end",)):
            if el.tag != "Song":
                continue
            p = el.get("FilePath") or ""
            if p and drive_root and not (len(p) > 1 and p[1] == ":") and not p.startswith("\\\\"):
                p = os.path.join(drive_root, p.lstrip("\\/"))
            if p and os.path.splitext(p)[1].lower() in MEDIA and not p.lower().startswith(("http", "netsearch", "td", "ytb")):
                tags = el.find("Tags")
                infos = el.find("Infos")
                length = None
                if infos is not None and infos.get("SongLength"):
                    try:
                        length = float(infos.get("SongLength"))
                    except ValueError:
                        pass
                out.append(make_entry(p, tags.get("Author", "") if tags is not None else "",
                                      tags.get("Title", "") if tags is not None else "", length, True))
            el.clear()
    except (ET.ParseError, OSError):
        pass
    return out


def vdj_database_files(home):
    files = []
    if home and os.path.isfile(os.path.join(home, "database.xml")):
        files.append((os.path.join(home, "database.xml"), None))
    for d in string.ascii_uppercase:
        root = f"{d}:\\"
        f = os.path.join(root, "VirtualDJ", "database.xml")
        try:
            if os.path.isfile(f) and (not home or os.path.normcase(f) != os.path.normcase(os.path.join(home, "database.xml"))):
                files.append((f, root))
        except OSError:
            pass
    return files


# ---------- reading tags from files ----------

def _riff_info(path):
    """Artist/title from a WAV file's LIST/INFO chunk (common for WAVs with no ID3)."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"RIFF":
                return "", ""
            f.read(8)
            artist = title = ""
            for _ in range(64):
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
                if cid == b"LIST" and size < 1 << 20:
                    data = f.read(size)
                    if data[:4] == b"INFO":
                        i = 4
                        while i + 8 <= len(data):
                            sid, ssz = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
                            val = data[i + 8:i + 8 + ssz].split(b"\0")[0].decode("utf-8", "replace").strip()
                            if sid == b"IART":
                                artist = val
                            elif sid == b"INAM":
                                title = val
                            i += 8 + ssz + (ssz & 1)
                elif cid == b"data":
                    f.seek(size + (size & 1), 1)
                else:
                    f.seek(size + (size & 1), 1)
            return artist, title
    except (OSError, struct.error):
        return "", ""


def read_tags(path):
    """-> (artist, title, length seconds or None). Never raises."""
    artist = title = ""
    length = None
    try:
        import mutagen
        mf = mutagen.File(path, easy=True)
        if mf is not None:
            length = getattr(mf.info, "length", None)
            tags = mf.tags
            if tags is not None:
                try:
                    artist = ", ".join(tags.get("artist", [])) if hasattr(tags, "get") else ""
                    title = ", ".join(tags.get("title", [])) if hasattr(tags, "get") else ""
                except (TypeError, ValueError, KeyError):
                    pass
                if not title and hasattr(tags, "getall"):  # WAV/AIFF with raw ID3
                    t = tags.getall("TIT2")
                    a = tags.getall("TPE1")
                    title = str(t[0]) if t else ""
                    artist = str(a[0]) if a else artist
    except Exception:
        pass
    if not title and path.lower().endswith(".wav"):
        artist, title = _riff_info(path)
    return artist, title, length


class TagCache:
    def __init__(self):
        self.file = os.path.join(paths.data_dir(), "tagcache.json")
        try:
            with open(self.file, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.dirty = False

    def get(self, path, st):
        v = self.data.get(path)
        if v and v[0] == st.st_size and abs(v[1] - st.st_mtime) < 2:
            return v[2], v[3], v[4]
        a, t, ln = read_tags(path)
        self.data[path] = [st.st_size, st.st_mtime, a, t, ln]
        self.dirty = True
        return a, t, ln

    def save(self):
        if self.dirty:
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.file)
            self.dirty = False


def walk_media(folder, cancelled=lambda: False):
    stack = [folder]
    while stack:
        if cancelled():
            return
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not e.name.startswith(("$", ".")) and e.name.lower() not in ("system volume information",):
                                stack.append(e.path)
                        elif os.path.splitext(e.name)[1].lower() in MEDIA:
                            yield e
                    except OSError:
                        pass
        except OSError:
            pass


def load_library(vdj_home, folders, progress=None, cancelled=lambda: False):
    """All songs from VirtualDJ's database and the chosen folders, one entry per file.
    progress(message) is called now and then."""
    by_path = {}
    for xml, root in vdj_database_files(vdj_home):
        if progress:
            progress(f"Reading VirtualDJ library ({xml})...")
        for e in read_vdj_database(xml, root):
            by_path.setdefault(os.path.normcase(e["path"]), e)
    # drop VirtualDJ entries whose file is gone (moved/deleted songs)
    if progress:
        progress("Checking VirtualDJ songs still exist...")
    by_path = {k: v for k, v in by_path.items() if os.path.exists(v["path"])}
    cache = TagCache()
    n = 0
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for de in walk_media(folder, cancelled):
            key = os.path.normcase(de.path)
            n += 1
            if progress and n % 250 == 0:
                progress(f"Scanning music folders... {n:,} files")
            known = by_path.get(key)
            if known and known["title"]:
                continue
            try:
                st = de.stat()
            except OSError:
                continue
            a, t, ln = cache.get(de.path, st)
            if known:  # VirtualDJ had the file but no tags
                known["artist"], known["title"] = known["artist"] or a, t
                known["length"] = known["length"] or ln
            else:
                by_path[key] = make_entry(de.path, a, t, ln, False)
            if n % 2000 == 0:
                cache.save()
    cache.save()
    return list(by_path.values())
