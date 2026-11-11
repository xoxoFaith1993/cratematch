"""Shows the problem reports sent from CrateMatch's "Report a problem" button (newest first).

Reports go to the Hunt Tracker database's "issues" list, which only the developer's Hunt Tracker id
can read, so this signs in with the installed Hunt Tracker's settings. Hunt Tracker's own reports are
left out (use its "Read Diagnostics.py" for those).
Run: python tools\\read_reports.py           (--all to include ones already seen)"""
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cratematch.report import API_KEY, DB_URL, _post  # noqa: E402

SEEN = os.path.join(ROOT, "tools", ".seen_reports.json")
HUNT_CFG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HuntTracker", "hunttracker.json")


def main():
    try:
        cfg = json.load(open(HUNT_CFG, encoding="utf-8"))
        refresh = cfg["leaderboard_refresh"]
    except (OSError, ValueError, KeyError):
        sys.exit(f"Needs your signed-in Hunt Tracker on this PC ({HUNT_CFG}).")
    tok = _post(f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
                {"grant_type": "refresh_token", "refresh_token": refresh})["id_token"]
    with urllib.request.urlopen(f"{DB_URL}/issues.json?auth={tok}", timeout=20) as r:
        issues = json.loads(r.read() or b"null") or {}
    ours = sorted(((iss.get("t", 0), key, iss) for uid, by_user in issues.items() for key, iss in by_user.items()
                   if (iss.get("setup") or {}).get("app") == "CrateMatch"), key=lambda x: -x[0])
    try:
        seen = set(json.load(open(SEEN, encoding="utf-8")))
    except (OSError, ValueError):
        seen = set()
    show = ours if "--all" in sys.argv else [x for x in ours if x[1] not in seen]
    print(f"{len(ours)} CrateMatch report(s), {len(show)} {'shown' if '--all' in sys.argv else 'new'}\n")
    for ts, key, iss in show:
        when = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        print("=" * 70)
        print(f"[{when}] {iss.get('name')}  (v{iss.get('v')})")
        print(iss.get("text", ""))
        print("setup:", ", ".join(f"{k}={v}" for k, v in (iss.get("setup") or {}).items() if k != "app"))
        print()
    json.dump(sorted(seen | {k for _, k, _ in ours}), open(SEEN, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
