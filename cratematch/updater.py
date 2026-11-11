"""Self-update from GitHub Releases (same scheme as Hunt Tracker).

"Publish Update.bat" bumps VERSION, builds the installer and uploads it as a release. When the
installed app opens it checks the latest release; if it's newer it downloads the installer, runs it
silently with /UPDATE=1 (the installer closes this app and reopens it afterwards) and exits.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request

from . import APP_NAME, VERSION

UPDATE_REPO = "xoxoFaith1993/cratematch"
FROZEN = getattr(sys, "frozen", False)


def _parts(v):
    return tuple(int(n) for n in re.findall(r"\d+", v))


def check_for_update():
    """(version, download url) of a newer release, or None."""
    req = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                                 headers={"User-Agent": APP_NAME, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=6) as r:
        rel = json.load(r)
    ver = str(rel.get("tag_name", "")).lstrip("vV")
    if not ver or _parts(ver) <= _parts(VERSION):
        return None
    for a in rel.get("assets", []):
        if a.get("name", "").lower().endswith(".exe"):
            return ver, a["browser_download_url"]
    return None


def download(ver, url, progress=None):
    dest = os.path.join(tempfile.gettempdir(), f"CrateMatchSetup-{ver}.exe")
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(tmp, dest)
    return dest


def _clean_env():
    """Without this the new copy inherits this one's unpack folder, which is deleted on exit."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def run_installer(setup):
    subprocess.Popen([setup, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE=1"],
                     env=_clean_env(), creationflags=0x00000008 | 0x00000200)
    os._exit(0)


def startup_check():
    """Installed .exe only: a small window while checking. Newer version -> download with a progress
    bar, install, reopen. Offline / up to date / any error -> just carry on opening the app."""
    if not FROZEN or "--no-update" in sys.argv:
        return
    import tkinter as tk
    from tkinter import ttk
    win = tk.Tk()
    win.title(f"{APP_NAME} update")
    win.configure(bg="#141518")
    win.resizable(False, False)
    w, h = 380, 120
    win.geometry(f"{w}x{h}+{(win.winfo_screenwidth() - w) // 2}+{(win.winfo_screenheight() - h) // 2}")
    win.attributes("-topmost", True)
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        win.iconbitmap(os.path.join(base, "assets", "icon.ico"))
    except Exception:
        pass
    msg = tk.Label(win, text="Checking for updates…", bg="#141518", fg="#E8E8EA", font=("Segoe UI", 11))
    msg.pack(pady=(24, 10))
    style = ttk.Style(win)
    style.theme_use("clam")
    style.configure("U.Horizontal.TProgressbar", background="#C8283C", troughcolor="#1D1F24", borderwidth=0)
    bar = ttk.Progressbar(win, length=300, mode="indeterminate", style="U.Horizontal.TProgressbar")
    bar.pack()
    bar.start(12)
    state = {"setup": None, "done": False}

    def work():
        try:
            found = check_for_update()
            if found:
                ver, url = found
                win.after(0, lambda: (msg.configure(text=f"Downloading version {ver}…"), bar.stop(),
                                      bar.configure(mode="determinate", maximum=100, value=0)))
                state["setup"] = download(ver, url, lambda d, t: win.after(
                    0, lambda: bar.configure(value=100 * d / t if t else 0)))
        except Exception:
            state["setup"] = None
        state["done"] = True

    def poll():
        if not state["done"]:
            win.after(100, poll)
            return
        if state["setup"]:
            msg.configure(text="Installing the update… CrateMatch will reopen by itself.")
            win.update()
            run_installer(state["setup"])
        win.destroy()

    threading.Thread(target=work, daemon=True).start()
    win.after(100, poll)
    win.mainloop()
