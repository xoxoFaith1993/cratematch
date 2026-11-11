"""Turning a Spotify link, a pasted list, or a document into a list of requested songs.

Each request is a dict: {"artist", "title", "duration" (sec or None), "raw" (what the client wrote),
"swap": True when "A - B" could mean either artist-title or title-artist}.
"""
import csv
import io
import json
import os
import re
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[\w-]+/)?(?:embed/)?|spotify:)(track|album|playlist)[/:]([A-Za-z0-9]{22})")
SPOTIFY_EMBED_CAP = 100  # Spotify's public embed page lists at most this many songs


class SourceError(Exception):
    pass


# ---------- Spotify (no login: reads the public embed page) ----------

def _spotify_embed(kind, sid):
    req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{sid}",
                                 headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        raise SourceError(f"Couldn't reach Spotify ({e}). Check the internet connection.") from None
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SourceError("Spotify didn't share that list. Make sure the playlist is public.")
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError, ValueError):
        raise SourceError("Spotify didn't share that list. Make sure the playlist is public.") from None


def _clean_artist(s):
    return (s or "").replace("\xa0", " ").strip()


def spotify_list(url):
    """-> (requests, list name, note or None)"""
    m = SPOTIFY_RE.search(url)
    if not m:
        raise SourceError("That isn't a Spotify playlist, album or song link.")
    kind, sid = m.groups()
    ent = _spotify_embed(kind, sid)
    if kind == "track":
        artist = ", ".join(a["name"] for a in ent.get("artists") or [])
        r = _req(artist, ent.get("name") or ent.get("title") or "", (ent.get("duration") or 0) / 1000)
        return [r], r["title"], None
    reqs = [_req(_clean_artist(t.get("subtitle")), t.get("title") or "", (t.get("duration") or 0) / 1000)
            for t in ent.get("trackList") or []]
    if not reqs:
        raise SourceError("That Spotify list is empty.")
    note = None
    if kind == "playlist" and len(reqs) >= SPOTIFY_EMBED_CAP:
        note = (f"Spotify only shares the first {SPOTIFY_EMBED_CAP} songs of a playlist this way. If it's longer: "
                "open the playlist in the Spotify app, click one song, press Ctrl+A then Ctrl+C, "
                "and paste into the box here instead of the link.")
    return reqs, ent.get("name") or "Spotify playlist", note


def spotify_tracks(ids, progress=None):
    """Look up many single-song links (what Ctrl+C in the Spotify app gives you)."""
    out = [None] * len(ids)
    done = [0]

    def one(i):
        try:
            out[i] = spotify_list(f"https://open.spotify.com/track/{ids[i]}")[0][0]
        except SourceError:
            out[i] = _req("", f"(Spotify song {ids[i]} - couldn't look it up)", None)
        done[0] += 1
        if progress:
            progress(done[0], len(ids))

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, range(len(ids))))
    return out


# ---------- text ----------

def _req(artist, title, duration=None, raw=None, swap=False):
    artist, title = (artist or "").strip(), (title or "").strip()
    return {"artist": artist, "title": title, "duration": duration or None,
            "raw": raw or (f"{artist} - {title}" if artist else title), "swap": swap}


LINE_PREFIX = re.compile(r"^\s*(?:#?\d{1,4}\s*[.):\-]\s*|#?\d{1,4}\s+(?=\D)|[-*•·–>]+\s*|\[\s*[x ]?\s*\]\s*)")
# Section headings in client documents ("Reception:", "Must play", "DO NOT PLAY", ...)
HEADING = re.compile(
    r"\b(play ?list|songs?|song ?list|set ?list|requests?|must[- ]?plays?|do ?n[o']?t[- ]?plays?|no[- ]?play|"
    r"don'?t play|please (don'?t|do not) play|avoid|ceremony|reception|cocktail( hour)?|dinner( music)?|"
    r"first dance|last dance|grand entrance|entrance|processional|recessional|cake cutting|bouquet toss|"
    r"garter|father[- ]daughter|mother[- ]son|wedding party|dance floor|special dances?)\b", re.I)
DO_NOT_PLAY = re.compile(r"\b(do ?n[o']?t[- ]?play|don'?t play|no[- ]?play|avoid|not play|blacklist|banned)\b", re.I)
VERSIONISH = re.compile(r"\b(remix|mix|edit|version|live|acoustic|instrumental|clean|dirty|explicit|extended|"
                        r"radio|intro|remaster(ed)?|feat|ft|with|cover|official|video|lyrics?)\b", re.I)


SECTION_WORDS = re.compile(r"\b(play ?list|song ?list|set ?list|must[- ]?plays?|do ?n[o']?t[- ]?plays?|don'?t play|"
                           r"no[- ]?play|requests)\b", re.I)


def is_heading(line):
    """A short line that names a section ("Reception:", "MUST PLAY", "First Dance") instead of a song.
    A normal "Artist - Title" line is never a heading unless it ends with ':' or '!' or is all caps."""
    s = LINE_PREFIX.sub("", unescape(line).strip(), count=1).strip()
    if not s or len(s) > 60:
        return False
    if s.endswith(":"):
        return True
    if not HEADING.search(s):
        return False
    bare = s.strip(" !:-–—*")
    if HEADING.fullmatch(bare) or re.fullmatch(r"(\w+\s+)?(songs|music|play ?list)", bare, re.I):
        return True          # "First Dance", "Reception songs", "Dinner music"
    if SECTION_WORDS.search(s) and not re.search(r"\bby\b", s, re.I):
        return s.isupper() or s.endswith("!") or not re.search(r"\s[-–—]\s", s)
    return s.isupper() and len(s) > 3


def parse_line(line):
    """One line of a client's list -> request, or None for blank/heading lines."""
    s = unescape(line).replace("​", "").strip().strip('"').strip()
    if not s or not re.search(r"[A-Za-z0-9]", s):
        return None
    s = LINE_PREFIX.sub("", s, count=1).strip()
    s = re.sub(r"\s+\(?\d{1,2}:\d{2}\)?\s*$", "", s)  # trailing length "3:45"
    if not s:
        return None
    if "\t" in s:  # copied from a spreadsheet / Spotify desktop: title<TAB>artist...
        cols = [c.strip() for c in s.split("\t") if c.strip()]
        if len(cols) >= 2:
            return _req(cols[1], cols[0], raw=s, swap=True)
    m = re.match(r"^(.+?)\s+by\s+(.+)$", s, re.I)
    if m and not re.search(r"\s[-–—]\s", s):
        return _req(m.group(2), m.group(1), raw=s)
    parts = re.split(r"\s+[-–—]\s+|\s*[–—]\s*", s, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return _req(parts[0], parts[1], raw=s, swap=True)
    m = re.match(r"^(.+?)\s*[:|]\s+(.+)$", s)
    if m:
        return _req(m.group(1), m.group(2), raw=s, swap=True)
    m = re.match(r"^(.+?)\s*\(([^()]+)\)$", s)  # "Shut Up and Dance (Walk the Moon)"
    if m and not VERSIONISH.search(m.group(2)):
        return _req(m.group(2), m.group(1), raw=s, swap=True)
    return _req("", s, raw=s)


def from_text(text, progress=None):
    """Pasted text: song lines and/or Spotify links. -> (requests, list name or None, note or None)
    Headings are skipped, and songs under a "Do not play" heading are left out."""
    lines, banned = [], []
    skipping = False
    for ln in text.splitlines():
        if is_heading(ln):
            skipping = bool(DO_NOT_PLAY.search(ln))
            continue
        (banned if skipping else lines).append(ln)
    links = [SPOTIFY_RE.search(ln) for ln in lines]
    playlist_links = [m for m in links if m and m.group(1) != "track"]
    track_ids = [m.group(2) for m in links if m and m.group(1) == "track"]
    reqs, note, name = [], None, None
    for m in playlist_links:
        r, n, note2 = spotify_list(m.group(0))
        reqs += r
        name = name or n
        note = note or note2
    if track_ids:
        reqs += spotify_tracks(track_ids, progress)
    for ln, m in zip(lines, links):
        if not m:
            r = parse_line(ln)
            if r:
                reqs.append(r)
    banned = [b for b in banned if parse_line(b)]
    if banned:
        dnp = f"Left out {len(banned)} song{'s' if len(banned) != 1 else ''} listed under “Do not play”."
        note = dnp + ("\n\n" + note if note else "")
    return reqs, name, note


def _csv_requests(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        """first header matching the names, in order of preference; ID/URI/URL columns never count"""
        for exact in (True, False):
            for n in names:
                for i, h in enumerate(head):
                    if re.search(r"\b(uri|url|id|isrc|link)", h):
                        continue
                    if (h == n) if exact else (n in h):
                        return i
        return None

    ti = col("track name", "song name", "title", "song", "track", "name")
    ai = col("artist name", "artists", "artist", "performer", "by")
    di = col("duration (ms)", "duration")
    if ti is None:
        return [r for r in (parse_line(" - ".join(c for c in row if c.strip())) for row in rows) if r]
    out = []
    for row in rows[1:]:
        if ti >= len(row) or not row[ti].strip():
            continue
        artist = row[ai] if ai is not None and ai < len(row) else ""
        dur = None
        if di is not None and di < len(row):
            try:
                v = float(row[di])
                dur = v / 1000 if "ms" in head[di] or v > 10000 else v
            except ValueError:
                pass
        out.append(_req(artist.replace(";", ", "), row[ti], dur))
    return out


def _docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    # tables: one row = one line, cells separated by tabs ("Title<TAB>Artist")
    xml = re.sub(r"</w:p>(?=(?:\s*<[^>]*>)*?\s*</w:tc>)", " ", xml)
    xml = re.sub(r"</w:tc>", "\t", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"</w:p>|<w:br/>", "\n", xml)
    return unescape(re.sub(r"<[^>]+>", "", xml))


def _read_text_file(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            t = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return t
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def from_file(path, progress=None):
    """-> (requests, list name, note or None)"""
    ext = os.path.splitext(path)[1].lower()
    name = os.path.splitext(os.path.basename(path))[0]
    if ext == ".docx":
        reqs, n, note = from_text(_docx_text(path), progress)
        return reqs, name, note
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise SourceError("PDF files aren't supported yet. Copy the text out of the PDF and paste it in.")
        text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        reqs, n, note = from_text(text, progress)
        return reqs, name, note
    text = _read_text_file(path)
    if ext == ".csv":
        return _csv_requests(text), name, None
    if ext in (".m3u", ".m3u8"):
        from .textnorm import parse_filename
        reqs = []
        for ln in text.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                a, t = parse_filename(os.path.splitext(os.path.basename(ln.replace("/", "\\")))[0])
                reqs.append(_req(a, t))
        return reqs, name, None
    if ext == ".doc":
        raise SourceError("Old .doc files aren't supported. Open it in Word, Save As .docx (or copy and paste the list).")
    reqs, n, note = from_text(text, progress)
    return reqs, n or name, note
