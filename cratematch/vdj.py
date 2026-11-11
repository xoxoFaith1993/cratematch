"""Where VirtualDJ lives on this PC, and writing playlists it can open."""
import os
import re
import subprocess

from xml.sax.saxutils import escape


def find_home():
    """VirtualDJ's home folder (holds database.xml and Playlists). None if VirtualDJ isn't set up."""
    cands = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\VirtualDJ") as k:
            cands.append(winreg.QueryValueEx(k, "HomeFolder")[0])
    except OSError:
        pass
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            docs = buf.value
    except Exception:
        pass
    cands += [os.path.join(docs, "VirtualDJ"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "VirtualDJ")]
    for c in cands:
        if c and os.path.isdir(c) and (os.path.isdir(os.path.join(c, "Playlists"))
                                       or os.path.isfile(os.path.join(c, "database.xml"))
                                       or os.path.isfile(os.path.join(c, "settings.xml"))):
            return os.path.normpath(c)
    return None


def lists_dir(home):
    """VirtualDJ 2021+ shows lists from <home>\\MyLists (browser: "My Lists")."""
    d = os.path.join(home, "MyLists")
    os.makedirs(d, exist_ok=True)
    return d


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name or "").strip(" .")
    return re.sub(r"\s+", " ", name)[:120] or "Client request"


def playlist_path(home, name):
    return os.path.join(lists_dir(home), safe_name(name) + ".vdjfolder")


def _attr(v):
    return escape(str(v), {'"': "&quot;"})


def _add_to_order(folder, name):
    """MyLists\\order lists the names VirtualDJ shows, top to bottom; new lists go at the end."""
    f = os.path.join(folder, "order")
    try:
        with open(f, encoding="utf-8-sig") as fh:
            names = [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        names = [os.path.splitext(n)[0] for n in sorted(os.listdir(folder)) if n.endswith(".vdjfolder")]
    if name not in names:
        names.append(name)
        with open(f, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(names) + "\n")


def write_playlist(home, name, entries, requests=None):
    """entries: library entries in play order (requests: the matching requests, used for the
    artist/title shown when a file has no tags). Overwrites a list with the same name.
    Returns the file written. Written exactly the way VirtualDJ 8.5 saves its own lists."""
    name = safe_name(name)
    path = playlist_path(home, name)
    rows = []
    for i, e in enumerate(entries):
        if not e.get("title") and requests and requests[i] and requests[i].get("title"):
            e = dict(e, artist=requests[i]["artist"], title=requests[i]["title"])
        a = [f'path="{_attr(e["path"])}"']
        try:
            a.append(f'size="{os.path.getsize(e["path"])}"')
        except OSError:
            pass
        if e.get("length"):
            a.append(f'songlength="{e["length"]:.1f}"')
        artist = e.get("artist") or e.get("fn_artist") or ""
        title = e.get("title") or e.get("fn_title") or ""
        if artist:
            a.append(f'artist="{_attr(artist)}"')
        if title:
            a.append(f'title="{_attr(title)}"')
        a.append(f'idx="{i}"')
        rows.append("\t<song " + " ".join(a) + " />")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<VirtualFolder noDuplicates="no">\n'
           + "".join(r + "\n" for r in rows) + "</VirtualFolder>\n")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(xml)
    os.replace(tmp, path)
    _add_to_order(os.path.dirname(path), name)
    return path


def list_exists(home, name):
    return os.path.isfile(playlist_path(home, name))


def is_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq virtualdj.exe", "/NH"], capture_output=True,
                             text=True, creationflags=0x08000000, timeout=5).stdout
        return "virtualdj.exe" in out.lower()
    except Exception:
        return False
