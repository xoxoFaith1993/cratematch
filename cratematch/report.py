"""Report a problem: sends the user's message (plus the app's version and setup) to the developer.

Uses the same Firebase database as Hunt Tracker, so reports land where the developer already reads
them ("issues" node, rules: anyone signed in anonymously may add a report under their own id, only
the developer can read). Each report is tagged setup.app = "CrateMatch". The database limits a report
to: t, v (<=20 chars), name (<=40), text (1..3000), setup {key: string <=200 or number/bool}.
"""
import json
import platform
import time
import urllib.request

from . import APP_NAME, VERSION, paths

DB_URL = "https://hunt-tracker-leaderboard-default-rtdb.firebaseio.com"
API_KEY = "AIzaSyAH_iRkVse016gT0tGuh1e0rrOxUvP2q0M"  # Firebase Web API key: public by design, the rules guard the data
TEXT_LIMIT = 3000


def _post(url, body, method="POST"):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": f"{APP_NAME}/{VERSION}"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read() or b"null")


def _sign_in():
    """Anonymous sign-in (no account): a random id kept in the settings. -> (token, uid)"""
    s = paths.load_settings()
    if s.get("report_refresh"):
        try:
            r = _post(f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
                      {"grant_type": "refresh_token", "refresh_token": s["report_refresh"]})
            return r["id_token"], r["user_id"]
        except Exception:
            pass  # expired or revoked: make a new id below
    r = _post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}", {"returnSecureToken": True})
    s = paths.load_settings()
    s["report_refresh"] = r["refreshToken"]
    paths.save_settings(s)
    return r["idToken"], r["localId"]


def _clip(v, n=200):
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    v = str(v)
    return v if len(v) <= n else v[:n - 1] + "…"


def build_text(message, context=""):
    """The user's words first; the automatic details after, cut to fit the database's limit."""
    text = message.strip()
    if context:
        room = TEXT_LIMIT - len(text) - 40
        if room > 100:
            text += "\n\n--- added automatically ---\n" + (context if len(context) <= room else context[:room - 1] + "…")
    return text[:TEXT_LIMIT]


def send(message, name="", context="", setup=None):
    """Sends a report. Returns True, or raises with a short reason."""
    if not message.strip():
        raise ValueError("Type what happened first.")
    token, uid = _sign_in()
    info = {"app": APP_NAME, "windows": f"{platform.release()} {platform.version()}"}
    info.update(setup or {})
    body = {"t": int(time.time()), "v": VERSION[:20], "name": _clip(f"{APP_NAME}: {name}".strip(": ") if name else APP_NAME, 40),
            "text": build_text(message, context),
            "setup": {k: _clip(v) for k, v in info.items() if v is not None and v != ""}}
    _post(f"{DB_URL}/issues/{uid}.json?auth={token}", body)
    return True
