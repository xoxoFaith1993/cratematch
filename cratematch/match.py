"""Matching requested songs to files in the DJ's library."""
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher, get_close_matches

from .textnorm import fold, split_artists, split_title, tokens

FOUND, CHECK = 0.82, 0.66   # score at or above FOUND = sure; CHECK..FOUND = "please check"


def _sim(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sm = SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() < 0.5:
        return sm.real_quick_ratio() * 0.5
    return sm.ratio()


class _Key:
    """One way of reading a song's identity (from tags, or from the file name)."""
    __slots__ = ("artists", "artist_str", "core", "strong", "soft", "remixer")

    def __init__(self, artist, title):
        st = split_title(title)
        self.artists = split_artists(artist) + st["feat"]
        self.artist_str = fold(artist) + " " + " ".join(st["feat"])
        self.core, self.strong, self.soft, self.remixer = st["core"], st["strong"], st["soft"], st["remixer"]


class _Lib:
    __slots__ = ("entry", "keys", "path_fold", "rank")

    def __init__(self, e):
        self.entry = e
        # (reading, penalty): tags first, then the file name both ways round ("Title - Artist.mp3")
        self.keys = []
        if e["title"]:
            self.keys.append((_Key(e["artist"], e["title"]), 0.0))
        self.keys.append((_Key(e["fn_artist"], e["fn_title"]), 0.0))
        if e["fn_artist"]:
            self.keys.append((_Key(e["fn_title"], e["fn_artist"]), 0.02))
        p = e["path"]
        self.path_fold = fold(os.path.basename(os.path.dirname(os.path.dirname(p))) + " " + e["folder"] + " "
                              + os.path.splitext(os.path.basename(p))[0])
        # tie-break: audio over video, already in VirtualDJ, mp3/wav first
        ext = os.path.splitext(p)[1].lower()
        self.rank = (0 if not e["video"] else 1, 0 if e["in_vdj"] else 1, 0 if ext in (".mp3", ".wav") else 1)


class Library:
    def __init__(self, entries):
        self.items = [_Lib(e) for e in entries]
        self.index = defaultdict(set)
        for i, it in enumerate(self.items):
            for k, _ in it.keys:
                for w in tokens(k.core):
                    self.index[w].add(i)
        self.vocab = list(self.index)

    def __len__(self):
        return len(self.items)

    def _candidates(self, core):
        words = tokens(core)
        cand = set()
        hits = [self.index.get(w) for w in words]
        known = [h for h in hits if h]
        if known:
            # songs sharing the rarest words first; enough to always include the right one
            known.sort(key=len)
            for h in known[:3]:
                cand |= h
        if not known or len(known) < len(words):
            for w in words:
                if w not in self.index and len(w) > 3:
                    for close in get_close_matches(w, self.vocab, n=3, cutoff=0.8):
                        cand |= self.index[close]
        return cand


def _artist_score(req_key, lk, lib):
    if not req_key.artists:
        return None
    if lk.artists:
        best = max(_sim(ra, la) for ra in req_key.artists for la in lk.artists)
        main = req_key.artists[0]
        if len(main) > 2 and re.search(rf"\b{re.escape(main)}\b", lk.artist_str):
            best = max(best, 0.97)
        return best
    # no artist on the file: is the artist in the folder or file name?
    main = req_key.artists[0]
    if len(main) > 2 and re.search(rf"\b{re.escape(main)}\b", lib.path_fold):
        return 0.92
    return None


def _score(req_key, req_dur, lib, prefer_clean):
    best = 0.0
    for lk, pen in lib.keys:
        t = _sim(req_key.core, lk.core)
        if t < 0.55:
            continue
        t -= pen
        a = _artist_score(req_key, lk, lib)
        if a is None:
            # title only: good, but never "sure" unless the request had no artist either
            s = t * (0.97 if not req_key.artists else 0.86)
        else:
            s = 0.6 * t + 0.4 * a
            if a < 0.5:
                s -= 0.1
        # versions: a remix request wants that remix; a plain request wants the original
        if req_key.strong != lk.strong:
            s -= 0.13 * len(req_key.strong ^ lk.strong)
        elif req_key.remixer and lk.remixer and _sim(req_key.remixer, lk.remixer) < 0.6:
            s -= 0.12
        if req_key.soft - lk.soft:
            s -= 0.02
        if lk.soft - req_key.soft:
            s -= 0.01
        if prefer_clean:
            if "clean" in lk.soft:
                s += 0.03
            if lk.soft & {"dirty", "explicit"}:
                s -= 0.03
        ln = lib.entry["length"]
        if req_dur and ln and not (req_key.strong ^ lk.strong) and not lk.soft:
            d = abs(req_dur - ln)
            if d <= 4:
                s += 0.02
            elif d > 45:
                s -= 0.04
        best = max(best, s)
    if lib.entry["video"]:
        best -= 0.01
    return best


def match_one(req, lib, prefer_clean=False):
    """-> {"req", "status": found|check|missing, "score", "entry", "alts": [(score, entry)...]}"""
    readings = [(req["artist"], req["title"])]
    if req.get("swap") and req["artist"]:
        readings.append((req["title"], req["artist"]))
    scored = {}
    for artist, title in readings:
        key = _Key(artist, title)
        if not key.core:
            continue
        for i in lib._candidates(key.core):
            s = _score(key, req.get("duration"), lib.items[i], prefer_clean)
            if s > scored.get(i, 0):
                scored[i] = s
    ranked = sorted(scored.items(), key=lambda kv: (-round(kv[1], 3), lib.items[kv[0]].rank))
    alts = [(s, lib.items[i].entry) for i, s in ranked[:8] if s >= 0.55]
    if not alts:
        return {"req": req, "status": "missing", "score": 0.0, "entry": None, "alts": []}
    s, e = alts[0]
    status = "found" if s >= FOUND else "check" if s >= CHECK else "missing"
    return {"req": req, "status": status, "score": s, "entry": e if status != "missing" else None, "alts": alts}


def match_all(reqs, lib, prefer_clean=False, progress=None):
    out = []
    for n, r in enumerate(reqs, 1):
        out.append(match_one(r, lib, prefer_clean))
        if progress and n % 10 == 0:
            progress(n, len(reqs))
    return out
