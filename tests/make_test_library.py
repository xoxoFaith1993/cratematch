"""Builds tests\\library: short tone files named like a real DJ's collection, from a real Spotify
playlist, with some songs left out on purpose. Run: python tests\\make_test_library.py"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from cratematch.sources import spotify_list

FFMPEG = r"D:\Home network\wavegrab\vendor\bin\ffmpeg.exe"
OUT = os.path.join(HERE, "library")
PLAYLIST = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


def tone(path, artist=None, title=None):
    args = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    if artist is not None:
        args += ["-metadata", f"artist={artist}", "-metadata", f"title={title}"]
    if path.endswith(".mp3"):
        args += ["-id3v2_version", "3", "-b:a", "64k"]
    subprocess.run(args + [path], check=True)


def main():
    random.seed(7)
    reqs, name, _ = spotify_list(PLAYLIST)
    os.makedirs(OUT, exist_ok=True)
    have, missing = [], []
    for i, r in enumerate(reqs):
        if i % 4 == 3:  # every 4th song: DJ doesn't have it
            missing.append(r)
            continue
        main_artist = r["artist"].split(",")[0].strip()
        style = i % 6
        folder = os.path.join(OUT, ["Top 40", "Party", "Wedding", "Hip Hop", "New"][i % 5])
        os.makedirs(folder, exist_ok=True)
        t = r["title"]
        if style == 0:      # tagged mp3, tidy name
            p, a, ti = f"{main_artist} - {t}.mp3", r["artist"], t
        elif style == 1:    # untagged wav, name only
            p, a, ti = f"{main_artist} - {t} (Clean).wav", None, None
        elif style == 2:    # track number + title, tags carry the artist
            p, a, ti = f"{i + 1:02d}. {t}.mp3", r["artist"], t
        elif style == 3:    # title - artist, lower case, no tags
            p, a, ti = f"{t.lower()} - {main_artist.lower()}.mp3", None, None
        elif style == 4:    # record-pool style
            p, a, ti = f"{main_artist} - {t} (Dirty Intro).mp3", None, None
        else:               # untagged wav with underscores
            p, a, ti = f"{main_artist}_-_{t}.wav".replace(" ", "_"), None, None
        p = "".join(c for c in p if c not in '<>:"/\\|?*')
        path = os.path.join(folder, p)
        tone(path, a, ti)
        have.append({"request": r, "file": path})
    # decoys: other versions of songs the DJ has
    for h in have[:4]:
        r = h["request"]
        a = r["artist"].split(",")[0]
        tone(os.path.join(OUT, "Party", f"{a} - {r['title']} (Instrumental).mp3"))
    tone(os.path.join(OUT, "Wedding", "Beyoncé - Halo.mp3"))
    with open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8") as f:
        json.dump({"playlist": PLAYLIST, "name": name, "have": have, "missing": missing}, f, indent=1, ensure_ascii=False)
    print(f"{name}: {len(have)} songs on disk, {len(missing)} left out -> {OUT}")


if __name__ == "__main__":
    main()
