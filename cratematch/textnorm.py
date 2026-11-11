"""Cleaning up song titles and artist names so different spellings can be compared."""
import re
import unicodedata

# Words in brackets / after " - " that describe the version of a song.
# Versions that change what you hear: a request for one shouldn't match a different one.
STRONG_VERSIONS = {
    "remix", "rmx", "instrumental", "acapella", "acappella", "a cappella", "live", "acoustic",
    "karaoke", "sped up", "slowed", "nightcore", "cover", "bootleg", "flip", "rework",
    "mashup", "vip", "dub", "reprise", "piano version", "orchestral",
}
# DJ edits of the same recording: fine to match, just a small preference for an exact pick.
SOFT_VERSIONS = {
    "clean", "dirty", "explicit", "radio edit", "radio", "edit", "extended", "extended mix",
    "original mix", "intro", "outro", "short", "club mix", "main", "album version",
    "single version", "quick hit", "hype", "transition",
}
# Noise that never matters for matching (checked on bracket text, e.g. "(Official Video)").
JUNK = re.compile(
    r"\b(official( music)?( video| audio| lyric video| visualizer)?|music video|lyric video|lyrics?|"
    r"visualizer|audio|video|hd|hq|4k|remaster(ed)?( \d{4})?|\d{4} remaster(ed)?|"
    r"\d{2,3} ?k(bps)?|320|topic|mono|stereo|bonus track|from .+ soundtrack)\b")
# Noise outside brackets in file names, only phrases that can't be part of a real title.
JUNK_CORE = re.compile(
    r"\b(official (music )?(video|audio|lyric video|visualizer)|music video|lyric video|"
    r"\d{2,3} ?kbps|128k|192k|256k|320k)\b")

# "feat. X" anywhere; "with X" only inside brackets ("Stay With Me" must survive)
FEAT = re.compile(r"\s*(?:[\(\[]\s*(?:feat|ft|featuring|with)\b\.?\s+([^\)\]]+)[\)\]]"
                  r"|\b(?:feat|ft|featuring)\b\.?\s+([^\(\[\-–—]+))", re.I)
BRACKETS = re.compile(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]")
DASH_SUFFIX = re.compile(r"\s+[-–—]\s+(.+)$")
ARTIST_SPLIT = re.compile(r"\s*(?:,|&|\+|/|;|\bx\b|\band\b|\bvs\.?\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bwith\b)\s*", re.I)
STOP = {"the", "a", "an", "of", "and", "to", "in", "on", "my", "me", "i", "you", "it", "is"}


def fold(s):
    """lowercase, no accents, & -> and, only letters/digits/spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace("$", "s").replace("ø", "o").replace("ß", "ss")
    s = re.sub(r"['’`´]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _versions_in(text):
    f = fold(text)
    strong = {v for v in STRONG_VERSIONS if re.search(rf"\b{v}\b", f)}
    if re.search(r"\bmix\b", f) and not re.search(r"\b(original|radio|club|extended|album) mix\b", f):
        strong.add("remix")
    if "rmx" in strong or "remix" in strong:
        strong.discard("rmx")
        strong.add("remix")
    soft = {v for v in SOFT_VERSIONS if re.search(rf"\b{v}\b", f)}
    return strong, soft


def split_title(title):
    """'Song (feat. X) - Radio Edit' -> core 'song', feat artists ['X'], strong/soft version words."""
    t = title or ""
    feats = []
    for m in FEAT.finditer(t):
        feats += [a for a in ARTIST_SPLIT.split(m.group(1) or m.group(2) or "") if a.strip()]
    t = FEAT.sub(" ", t)
    extra = []
    for m in BRACKETS.finditer(t):
        extra.append(m.group(1))
    t = BRACKETS.sub(" ", t)
    m = DASH_SUFFIX.search(t)
    if m:
        extra.append(m.group(1))
        t = t[:m.start()]
    strong, soft = set(), set()
    for e in extra:
        s, so = _versions_in(e)
        strong |= s
        soft |= so
    # keep remix names ("Skrillex Remix") as part of what identifies the track
    remixer = ""
    for e in extra:
        fe = fold(e)
        if re.search(r"\b(remix|rmx|mix|edit|flip|bootleg|rework|vip)\b", fe) and not JUNK.fullmatch(fe):
            remixer = fe
            break
    core = fold(JUNK_CORE.sub(" ", fold(t)))
    if not core:  # the whole title was in brackets
        core = fold(title)
    return {"core": core, "feat": [fold(a) for a in feats], "strong": strong, "soft": soft, "remixer": remixer}


def split_artists(artist):
    return [fold(a) for a in ARTIST_SPLIT.split(artist or "") if fold(a)]


def tokens(s):
    return [w for w in s.split() if w not in STOP and len(w) > 1] or s.split()


LEAD_NUM = re.compile(r"^\s*(?:\d{1,3}|[a-d]\d)\s*(?:[.\-_)]\s*|\s+(?=\D))")


def parse_filename(stem):
    """'01. Artist - Title (Clean)' -> ('Artist', 'Title (Clean)'). Artist may be ''."""
    s = stem.replace("_", " ").strip()
    s = LEAD_NUM.sub("", s, count=1).strip()
    parts = re.split(r"\s+[-–—]\s+|\s*[-–—]{2,}\s*", s, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return "", s
