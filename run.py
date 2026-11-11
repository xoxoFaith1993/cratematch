import sys


def selftest(out):
    """CrateMatch.exe --selftest <folder>: checks every part except the window, writes selftest.log."""
    import os
    import traceback
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "selftest.log"), "w", encoding="utf-8") as log:
        def step(name, fn):
            try:
                log.write(f"OK   {name}: {fn()}\n")
            except Exception:
                log.write(f"FAIL {name}: {traceback.format_exc()}\n")
            log.flush()

        from cratematch import VERSION, library, match, sources, updater, vdj
        log.write(f"CrateMatch {VERSION}\n")
        step("virtualdj home", vdj.find_home)
        step("spotify embed", lambda: len(sources.spotify_list(
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[0]))
        lib = match.Library([library.make_entry(r"C:\x\Mark Ronson - Uptown Funk (Clean).mp3"),
                             library.make_entry(r"C:\x\Ed Sheeran - Perfect.wav")])
        step("match", lambda: [match.match_one(r, lib)["status"] for r in sources.from_text(
            "1. Uptown Funk - Bruno Mars\nPerfect by Ed Sheeran\nToxic - Britney Spears")[0]])
        step("mutagen", lambda: __import__("mutagen").version_string)
        step("update check", updater.check_for_update)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        from cratematch import updater
        updater.startup_check()
        from cratematch.app import main
        main()
