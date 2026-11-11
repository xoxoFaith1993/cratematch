"""Sections: headings -> sub-lists, text round trip, several Spotify playlists, VirtualDJ folder layout.
Run: python tests\\test_sections.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cratematch import sources, vdj
from cratematch.library import make_entry

BAD = []


def check(what, ok):
    print(("ok   " if ok else "BAD  ") + what)
    if not ok:
        BAD.append(what)


def main():
    text = """Johnson Wedding - song requests

Cocktail hour:
1. Tame Impala - Loser
2. Babydoll by Dominic Fike

Reception / dance floor:
- Shakira - Dai Dai
- Beyonce - Halo

First Dance
At Last - Etta James

DO NOT PLAY:
Macarena
"""
    reqs, name, note = sources.from_text(text)
    secs = sources.sections_of(reqs)
    check(f"name from title line ({name!r})", name == "Johnson Wedding")
    check(f"sections {secs}", secs == ["Cocktail hour", "Reception / dance floor", "First Dance"])
    check("do-not-play left out", len(reqs) == 5 and "Do not play" in (note or ""))

    # round trip through the "Edit as text" format
    from cratematch.app import App
    as_text = App._as_text(App, reqs, name)
    reqs2, name2, _ = sources.from_text(as_text)
    check("round trip keeps name", name2 == name)
    check("round trip keeps sections", [r["section"] for r in reqs2] == [r["section"] for r in reqs])
    check("round trip keeps songs", [r["raw"] for r in reqs2] == [r["raw"] for r in reqs])
    # a section that looks like a list name, further down, stays a section
    t3 = "Playlist: Smith Party\n\nKids playlist:\nBaby Shark\n\nGrown ups:\nToxic - Britney Spears\n"
    r3, n3, _ = sources.from_text(t3)
    check(f"'Kids playlist' is a section ({[r['section'] for r in r3]}, name {n3!r})",
          n3 == "Smith Party" and [r["section"] for r in r3] == ["Kids playlist", "Grown ups"])

    # two Spotify playlists pasted together: each becomes a section
    two = ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M\n"
           "https://open.spotify.com/playlist/37i9dQZF1DX5Ejj0EkURtP\n")
    r4, n4, _ = sources.from_text(two)
    check(f"two playlists -> two sections {sources.sections_of(r4)}", len(sources.sections_of(r4)) == 2)

    # VirtualDJ layout: list + .subfolders\ with one list per section + order files
    home = tempfile.mkdtemp()
    e = lambda p: make_entry(p, "A", os.path.basename(p))
    sections = [("Cocktail hour", [e(r"C:\m\1.mp3")], None),
                ("Reception / dance floor", [e(r"C:\m\2.mp3"), e(r"C:\m\3.mp3")], None)]
    vdj.write_playlist(home, "Johnson Wedding", [e(r"C:\m\1.mp3"), e(r"C:\m\2.mp3"), e(r"C:\m\3.mp3")],
                       sections=sections)
    ml = os.path.join(home, "MyLists")
    sub = os.path.join(ml, "Johnson Wedding.subfolders")
    check("main list file", os.path.isfile(os.path.join(ml, "Johnson Wedding.vdjfolder")))
    check(f"sub-lists {sorted(os.listdir(sub))}",
          sorted(os.listdir(sub)) == ["Cocktail hour.vdjfolder", "Reception - dance floor.vdjfolder", "order"])
    order = open(os.path.join(sub, "order"), encoding="utf-8").read().split()
    check(f"sub order {open(os.path.join(sub, 'order'), encoding='utf-8').read()!r}",
          open(os.path.join(sub, "order"), encoding="utf-8").read().splitlines() == ["Cocktail hour", "Reception - dance floor"])
    check("top order", open(os.path.join(ml, "order"), encoding="utf-8").read().splitlines() == ["Johnson Wedding"])
    print(f"\n{'all passed' if not BAD else f'{len(BAD)} failed'}")
    return len(BAD)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
