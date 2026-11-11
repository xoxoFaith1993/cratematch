"""Signing in to Spotify (PKCE, no secret needed) to list the user's playlists and read them in full.

Spotify Development Mode rules (Feb 2026): the developer app's owner needs Premium, up to 5 users
must be added under "User Management", and song lists are only returned for playlists the user
owns or collaborates on. For other playlists we fall back to the public embed page (first 100 songs).
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from . import paths
from .sources import SourceError, _req, spotify_list

# Filled in after creating the app at developer.spotify.com (can also be set in Settings).
DEFAULT_CLIENT_ID = "12b978ff325f46dfa82e51ab3bdd7bb9"  # Ethan's "CrateMatch" app (Development mode)
PORT = 43821
REDIRECT = f"http://127.0.0.1:{PORT}/callback"
SCOPES = "playlist-read-private playlist-read-collaborative"
API = "https://api.spotify.com/v1"


class NotOnList(SourceError):
    """The Spotify account signed in fine, but isn't on the app's User Management list yet."""


def client_id():
    return (paths.load_settings().get("spotify_client_id") or DEFAULT_CLIENT_ID).strip()


def _token_file():
    return os.path.join(paths.data_dir(), "spotify_token.json")


def _protect(data: bytes, unprotect=False) -> bytes:
    """Windows DPAPI: the saved login can only be read by this Windows user."""
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp, out = BLOB(len(data), buf), BLOB()
    fn = ctypes.windll.crypt32.CryptUnprotectData if unprotect else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _load_token():
    try:
        with open(_token_file(), "rb") as f:
            return json.loads(_protect(f.read(), unprotect=True))
    except Exception:
        return None


def _save_token(tok):
    with open(_token_file(), "wb") as f:
        f.write(_protect(json.dumps(tok).encode()))


def sign_out():
    try:
        os.remove(_token_file())
    except OSError:
        pass


def signed_in():
    return _load_token() is not None


def _post_token(form):
    req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                 data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            tok = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SourceError(f"Spotify sign-in failed ({e.code}): {e.read().decode('utf-8', 'replace')[:200]}") from None
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    return tok


def _find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(p):
                return p
    return None


def open_login_window(url):
    """A small sign-in window (Edge in app mode: no tabs or address bar) with its own profile, so it
    never touches the user's normal browser and remembers the Spotify login for next time.
    Returns the process (to close it afterwards), or None if it fell back to the normal browser."""
    edge = _find_edge()
    if edge:
        import subprocess
        try:
            import ctypes
            sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            sw, sh = 1920, 1080
        w, h = 520, 780
        try:
            return subprocess.Popen([
                edge, f"--app={url}", f"--window-size={w},{h}",
                f"--window-position={max(0, (sw - w) // 2)},{max(0, (sh - h) // 2)}",
                "--user-data-dir=" + os.path.join(paths.data_dir(), "login-window"),
                "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
        except OSError:
            pass
    webbrowser.open(url)
    return None


def close_login_window(proc):
    if proc and proc.poll() is None:
        import subprocess
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=0x08000000)


def sign_in(timeout=300):
    """Opens a small Spotify login window and waits for it. Returns the display name."""
    cid = client_id()
    if not cid:
        raise SourceError("Spotify sign-in isn't set up yet: add the Client ID in Settings.")
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got = {}
    done = threading.Event()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not self.path.startswith("/callback"):
                self.send_response(404)
                self.end_headers()
                return
            if q.get("state", [""])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            ok = "code" in got
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Signed in! Going back to CrateMatch…" if ok
                   else "Spotify sign-in was cancelled. You can close this window.")
            self.wfile.write(f"<html><head><title>CrateMatch</title></head><body style='font-family:Segoe UI;"
                             f"background:#141518;color:#eee;text-align:center;padding-top:120px'><h2>{msg}</h2>"
                             f"<script>setTimeout(function(){{window.close()}},800)</script></body></html>".encode())
            done.set()

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        raise SourceError(f"Couldn't start sign-in (port {PORT} is busy). Close other CrateMatch windows and try again.") from None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES,
        "code_challenge_method": "S256", "code_challenge": challenge, "state": state})
    win = open_login_window(url)
    try:
        # wait for the callback; stop early if the user closes the sign-in window
        deadline = time.time() + timeout
        while not done.wait(0.5):
            if win and win.poll() is not None:
                raise SourceError("Spotify sign-in window was closed before finishing.")
            if time.time() > deadline:
                raise SourceError("Spotify sign-in timed out. Try again.")
    finally:
        srv.shutdown()
        srv.server_close()
        if win:
            time.sleep(1.2)  # let the "Signed in!" page show for a moment
            close_login_window(win)
    if "code" not in got:
        raise SourceError("Spotify sign-in was cancelled" + (f" ({got['error']})." if got.get("error") else "."))
    tok = _post_token({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT,
                       "client_id": cid, "code_verifier": verifier})
    _save_token(tok)
    try:
        return me().get("display_name") or "Spotify user"
    except PermissionError:
        # Development mode: only accounts added under User Management may use the app
        sign_out()
        raise NotOnList("This Spotify account isn't on CrateMatch's list yet.") from None


def _access_token():
    tok = _load_token()
    if not tok:
        raise SourceError("Not signed in to Spotify.")
    if time.time() >= tok.get("expires_at", 0):
        new = _post_token({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                           "client_id": client_id()})
        new.setdefault("refresh_token", tok["refresh_token"])
        _save_token(new)
        tok = new
    return tok["access_token"]


def _get(url):
    if not url.startswith("http"):
        url = API + url
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _access_token()})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(min(int(e.headers.get("Retry-After", "2")), 10))
                continue
            if e.code == 401:
                sign_out()
                raise SourceError("Spotify sign-in expired. Please sign in again.") from None
            if e.code == 403:
                raise PermissionError(e.read().decode("utf-8", "replace")[:200]) from None
            raise SourceError(f"Spotify error {e.code}.") from None
        except urllib.error.URLError as e:
            raise SourceError(f"Couldn't reach Spotify ({e.reason}).") from None


def me():
    return _get("/me")


def my_playlists():
    """All playlists in the user's library: [{"id", "name", "owner", "count", "mine"}]."""
    try:
        my_id = me().get("id")
    except PermissionError:
        sign_out()
        raise NotOnList("This Spotify account isn't on CrateMatch's list anymore.") from None
    out, url = [], "/me/playlists?limit=50"
    while url:
        page = _get(url)
        for p in page.get("items") or []:
            if not p:
                continue
            owner = (p.get("owner") or {})
            info = p.get("items") or p.get("tracks") or {}
            out.append({"id": p["id"], "name": p.get("name") or "(no name)",
                        "owner": owner.get("display_name") or owner.get("id") or "",
                        "count": info.get("total"),
                        "mine": owner.get("id") == my_id or bool(p.get("collaborative"))})
        url = page.get("next")
    return out


def playlist_songs(pid, name=None):
    """Full song list for a playlist. Falls back to the public page (first 100) for playlists
    Spotify won't list in full. -> (requests, name, note or None)"""
    try:
        reqs, url = [], f"/playlists/{pid}/items?limit=50"
        while url:
            page = _get(url)
            for it in page.get("items") or []:
                t = it.get("item") or it.get("track")
                if not t or t.get("type", "track") != "track":
                    continue
                artist = ", ".join(a.get("name", "") for a in t.get("artists") or [] if a.get("name"))
                reqs.append(_req(artist, t.get("name") or "", (t.get("duration_ms") or 0) / 1000))
            url = page.get("next")
        if reqs:
            return reqs, name, None
    except (PermissionError, SourceError):
        pass
    reqs, n, note = spotify_list(f"https://open.spotify.com/playlist/{pid}")
    return reqs, name or n, note
