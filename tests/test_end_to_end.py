"""Spotify playlist -> scan tests\\library -> match -> compare with expected.json.
Run make_test_library.py first. Pass --write to also write the VirtualDJ playlist."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from cratematch import library, match, sources, vdj


def main():
    exp = json.load(open(os.path.join(HERE, "expected.json"), encoding="utf-8"))
    reqs, name, note = sources.spotify_list(exp["playlist"])
    entries = library.load_library(None, [os.path.join(HERE, "library")])
    lib = match.Library(entries)
    results = match.match_all(reqs, lib)
    want = {h["request"]["raw"]: os.path.normcase(h["file"]) for h in exp["have"]}
    bad = 0
    for m in results:
        t = m["req"]["raw"]
        got = os.path.normcase(m["entry"]["path"]) if m["entry"] else None
        exp_file = want.get(t)
        good = (got == exp_file) if exp_file else (m["status"] == "missing")
        bad += not good
        if not good or m["status"] == "check":
            print(f"{'ok ' if good else 'BAD'} {m['status']:7} {m['score']:.2f} {m['req']['raw'][:55]:55} -> "
                  f"{os.path.basename(got) if got else None}  (wanted {os.path.basename(exp_file) if exp_file else 'missing'})")
    counts = {s: sum(m["status"] == s for m in results) for s in ("found", "check", "missing")}
    print(f"{name}: {len(entries)} files scanned, {counts}, {len(results) - bad}/{len(results)} right")
    if "--write" in sys.argv:
        home = vdj.find_home()
        keep = [m for m in results if m["entry"]]
        p = vdj.write_playlist(home, "CrateMatch test", [m["entry"] for m in keep], [m["req"] for m in keep])
        print("wrote", p)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
