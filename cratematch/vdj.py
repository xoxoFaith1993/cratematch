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
    name = re.sub(r"\s*[/\\|]\s*", " - ", name or "")          # "Reception / dance floor"
    name = re.sub(r'[<>:"?*\x00-\x1f]', " ", name).strip(" .-")
    return re.sub(r"\s+", " ", name)[:120] or "Client request"


def playlist_path(home, name):
    return os.path.join(lists_dir(home), safe_name(name) + ".vdjfolder")


def _attr(v):
    return escape(str(v), {'"': "&quot;"})


def _read_order(folder):
    try:
        with open(os.path.join(folder, "order"), encoding="utf-8-sig") as fh:
            return [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        return [os.path.splitext(n)[0] for n in sorted(os.listdir(folder)) if n.endswith(".vdjfolder")]


def _write_order(folder, names):
    with open(os.path.join(folder, "order"), "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(names) + "\n")


def _add_to_order(folder, name):
    """<folder>\\order lists the names VirtualDJ shows, top to bottom; new lists go at the end."""
    names = _read_order(folder)
    if name not in names:
        names.append(name)
    elif os.path.isfile(os.path.join(folder, "order")):
        return
    _write_order(folder, names)


def write_playlist(home, name, entries, requests=None, sections=None):
    """entries: library entries in play order (requests: the matching requests, used for the
    artist/title shown when a file has no tags). Overwrites a list with the same name.

    sections: optional [(section name, entries, requests), ...]. The list then also gets one
    sub-list per section, the way VirtualDJ's "Create List subfolder" stores them:
    MyLists\\<name>.vdjfolder (all songs) + MyLists\\<name>.subfolders\\<section>.vdjfolder + order.
    Returns the main list's file."""
    name = safe_name(name)
    path = playlist_path(home, name)
    _write_list(path, entries, requests)
    _add_to_order(os.path.dirname(path), name)
    if sections:
        sub = os.path.splitext(path)[0] + ".subfolders"
        os.makedirs(sub, exist_ok=True)
        ours = []
        for sname, sentries, sreqs in sections:
            sname = safe_name(sname)
            n, k = sname, 2
            while n in ours:            # two sections with the same name
                n, k = f"{sname} {k}", k + 1
            ours.append(n)
            _write_list(os.path.join(sub, n + ".vdjfolder"), sentries, sreqs)
        # our sections first, in the client's order; keep any sub-lists the DJ made himself
        _write_order(sub, ours + [n for n in _read_order(sub) if n not in ours
                                  and os.path.exists(os.path.join(sub, n + ".vdjfolder"))])
    return path


def _write_list(path, entries, requests=None):
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


def list_exists(home, name):
    return os.path.isfile(playlist_path(home, name))


def is_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq virtualdj.exe", "/NH"], capture_output=True,
                             text=True, creationflags=0x08000000, timeout=5).stdout
        return "virtualdj.exe" in out.lower()
    except Exception:
        return False
