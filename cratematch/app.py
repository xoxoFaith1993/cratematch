"""CrateMatch window: request list in, VirtualDJ playlist out."""
import datetime
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import APP_NAME, VERSION, library, match, paths, sources, spotify_auth, vdj

RED = "#C8283C"
RED_HOVER = "#A51F31"
BG = "#141518"
PANEL = "#1D1F24"
TEXT = "#E8E8EA"
MUTED = "#9A9CA5"
OK_C, CHECK_C, MISS_C, SKIP_C = "#4CC38A", "#E8B339", "#E5484D", "#6B6E78"
STATUS_TEXT = {"found": "✔  Found", "check": "?  Check", "missing": "✖  Missing", "skip": "–  Left out"}


def center_over(win, parent):
    """Put a pop-up window in the middle of the main window instead of the screen corner."""
    def place():
        try:
            win.tk.call("tk::PlaceWindow", win._w, "widget", parent._w)
        except tk.TclError:
            pass
    win.after(20, place)


def asset(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME}  –  client requests to VirtualDJ")
        try:  # use most of the screen height so more matches fit
            scale = ctk.ScalingTracker.get_window_scaling(self)
            h = max(700, min(1000, int(self.winfo_screenheight() / scale * 0.86)))
        except Exception:
            h = 820
        self.geometry(f"1100x{h}+60+30")
        self.minsize(900, 680)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(asset("icon.ico"))
        except Exception:
            pass
        self.settings = paths.load_settings()
        self.vdj_home = self.settings.get("vdj_home") or vdj.find_home()
        self.lib = None
        self.lib_busy = False
        self.reqs = None          # current request list
        self.loaded_name = None   # name of the list as it was loaded (Spotify playlist name, file name)
        self.results = []         # match results, one per request
        self.choice = {}          # row -> chosen entry (None = left out)
        self.pending_note = None
        self._build()
        self.after(100, self.load_library)
        if spotify_auth.signed_in():
            self.after(300, self.refresh_playlists)

    # ---------- layout ----------
    def _build(self):
        f_title = ctk.CTkFont(size=22, weight="bold")
        f_h = ctk.CTkFont(size=15, weight="bold")
        self.f_small = ctk.CTkFont(size=12)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(top, text="CrateMatch", font=f_title, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(top, text="   Turn a client's song list into a VirtualDJ playlist from the music you already have",
                     text_color=MUTED).pack(side="left", pady=(6, 0))
        ctk.CTkButton(top, text="Settings", width=90, fg_color=PANEL, hover_color="#2A2D34",
                      command=self.open_settings).pack(side="right")

        # 1. request
        req = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
        req.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(req, text="1   The client's songs", font=f_h, text_color=TEXT).pack(anchor="w", padx=14, pady=(10, 0))
        self.tabs = ctk.CTkTabview(req, height=190, fg_color=PANEL, segmented_button_selected_color=RED,
                                   segmented_button_selected_hover_color=RED_HOVER)
        self.tabs.pack(fill="x", padx=10, pady=(0, 8))
        sp = self.tabs.add("Spotify")
        tx = self.tabs.add("Text list or document")

        row = ctk.CTkFrame(sp, fg_color="transparent")
        row.pack(fill="x")
        self.sp_status = ctk.CTkLabel(row, text="", text_color=MUTED)
        self.sp_status.pack(side="left")
        self.sp_btn = ctk.CTkButton(row, text="", width=150, fg_color=RED, hover_color=RED_HOVER, command=self.toggle_sign_in)
        self.sp_btn.pack(side="right")
        self.sp_refresh = ctk.CTkButton(row, text="Refresh list", width=100, fg_color="#2A2D34", hover_color="#353943",
                                        command=self.refresh_playlists)
        self.sp_help = ctk.CTkButton(row, text="How does this work?", width=150, fg_color="transparent",
                                     hover_color="#2A2D34", text_color=MUTED, command=lambda: SpotifyHelp(self))
        self.sp_help.pack(side="left", padx=10)
        self.pl_frame = ctk.CTkScrollableFrame(sp, height=80, fg_color=BG)
        self.pl_frame.pack(fill="x", pady=6)
        row2 = ctk.CTkFrame(sp, fg_color="transparent")
        row2.pack(fill="x")
        self.link = ctk.CTkEntry(row2, placeholder_text="…or paste a Spotify playlist link here")
        self.link.pack(side="left", fill="x", expand=True)
        self.link.bind("<Return>", lambda e: self.load_link())
        ctk.CTkButton(row2, text="Find songs", width=110, fg_color=RED, hover_color=RED_HOVER,
                      command=self.load_link).pack(side="left", padx=(8, 0))
        self._sp_ui()

        self.text = ctk.CTkTextbox(tx, height=130, wrap="none", fg_color=BG, border_width=1, border_color="#3A3D46")
        self.text.pack(side="left", fill="both", expand=True)
        col = ctk.CTkFrame(tx, fg_color="transparent")
        col.pack(side="left", fill="y", padx=(10, 0))
        ctk.CTkButton(col, text="Open a file…", width=140, fg_color="#2A2D34", hover_color="#353943",
                      command=self.open_file).pack(pady=(0, 6))
        ctk.CTkButton(col, text="Find these songs", width=140, fg_color=RED, hover_color=RED_HOVER,
                      command=self.load_text).pack()
        ctk.CTkLabel(col, text="Paste one song per line,\ne.g. Artist - Title.\nWorks with .txt, .csv,\nWord .docx and\nSpotify song links.",
                     text_color=MUTED, font=self.f_small, justify="left").pack(pady=10, anchor="w")

        # 2. library
        lib = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
        lib.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(lib, text="2   Your music", font=f_h, text_color=TEXT).pack(side="left", padx=14, pady=10)
        self.lib_label = ctk.CTkLabel(lib, text="Loading…", text_color=MUTED)
        self.lib_label.pack(side="left", padx=8)
        ctk.CTkButton(lib, text="Rescan", width=80, fg_color="#2A2D34", hover_color="#353943",
                      command=self.load_library).pack(side="right", padx=(6, 12))
        ctk.CTkButton(lib, text="Music folders…", width=120, fg_color="#2A2D34", hover_color="#353943",
                      command=self.edit_folders).pack(side="right")

        # bottom bar first (side=bottom) so it never gets squeezed off a small window
        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, anchor="w", font=self.f_small)
        self.status.pack(side="bottom", fill="x", padx=20, pady=(0, 8))
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(side="bottom", fill="x", padx=18, pady=(4, 6))

        # 3. results
        res = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
        res.pack(fill="both", expand=True, padx=18, pady=6)
        head = ctk.CTkFrame(res, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(head, text="3   Matches", font=f_h, text_color=TEXT).pack(side="left")
        self.summary = ctk.CTkLabel(head, text="", text_color=MUTED)
        self.summary.pack(side="left", padx=12)
        self.edit_btn = ctk.CTkButton(head, text="Edit as text", width=100, height=26, fg_color="#2A2D34",
                                      hover_color="#353943", command=self.edit_as_text, state="disabled")
        self.edit_btn.pack(side="right")
        ctk.CTkLabel(head, text="Right-click a song to pick another version or leave it out", text_color=MUTED,
                     font=self.f_small).pack(side="right", padx=10)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("CM.Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=26,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("CM.Treeview.Heading", background="#262931", foreground=MUTED, relief="flat",
                        font=("Segoe UI", 10, "bold"))
        style.map("CM.Treeview", background=[("selected", "#3A2028")], foreground=[("selected", TEXT)])
        style.map("CM.Treeview.Heading", background=[("active", "#2E323B")])
        style.configure("CM.Vertical.TScrollbar", background="#2A2D34", troughcolor=BG, borderwidth=0, arrowsize=12)
        wrap = tk.Frame(res, bg=BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tree = ttk.Treeview(wrap, columns=("status", "req", "file"), show="headings", style="CM.Treeview")
        for c, t, w in (("status", "", 110), ("req", "Requested", 380), ("file", "Your file", 480)):
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, minwidth=60, stretch=c != "status", anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview, style="CM.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for k, c in (("found", OK_C), ("check", CHECK_C), ("missing", MISS_C), ("skip", SKIP_C)):
            self.tree.tag_configure(k, foreground=c)
        self.tree.tag_configure("section", foreground="#FF6B7F", background="#1F1418", font=("Segoe UI", 10, "bold"))
        self.tree.bind("<Button-3>", self.row_menu)
        self.tree.bind("<Double-1>", self.toggle_row)

        # 4. create
        ctk.CTkLabel(bot, text="Playlist name", text_color=MUTED).pack(side="left")
        self.name = ctk.CTkEntry(bot, width=280)
        self.name.pack(side="left", padx=8)
        self.clean = ctk.CTkCheckBox(bot, text="Prefer clean versions", fg_color=RED, hover_color=RED_HOVER,
                                     command=self.rematch)
        if self.settings.get("prefer_clean"):
            self.clean.select()
        self.clean.pack(side="left", padx=10)
        self.split = ctk.CTkCheckBox(bot, text="Sub-list per section", fg_color=RED, hover_color=RED_HOVER,
                                     command=self._split_changed)
        if self.settings.get("split_sections", True):
            self.split.select()     # packed only when the list has sections
        self.make_btn = ctk.CTkButton(bot, text="Create VirtualDJ playlist", height=38, width=220,
                                      font=ctk.CTkFont(size=14, weight="bold"), fg_color=RED, hover_color=RED_HOVER,
                                      command=self.create_playlist, state="disabled")
        self.make_btn.pack(side="right")
        self.miss_btn = ctk.CTkButton(bot, text="Copy missing songs", height=38, width=160, fg_color="#2A2D34",
                                      hover_color="#353943", command=self.copy_missing, state="disabled")
        self.miss_btn.pack(side="right", padx=8)

    # ---------- helpers ----------
    def set_status(self, msg):
        self.after(0, lambda: self.status.configure(text=msg))

    def bg(self, work, done=None, fail=None):
        def run():
            try:
                r = work()
            except Exception as e:  # shown to the user
                self.after(0, lambda e=e: (fail or self.show_error)(e))
                return
            if done:
                self.after(0, lambda: done(r))
        threading.Thread(target=run, daemon=True).start()

    def show_error(self, e):
        self.set_status("")
        messagebox.showerror(APP_NAME, str(e) or e.__class__.__name__, parent=self)

    def save_settings(self):
        paths.save_settings(self.settings)

    # ---------- Spotify ----------
    def _sp_ui(self):
        if spotify_auth.signed_in():
            self.sp_status.configure(text=self.settings.get("spotify_name") and
                                     f"Signed in to Spotify as {self.settings['spotify_name']}. Pick a playlist:"
                                     or "Signed in to Spotify. Pick a playlist:")
            self.sp_btn.configure(text="Sign out", fg_color="#2A2D34", hover_color="#353943")
            self.sp_refresh.pack(side="right", padx=8)
        else:
            self.sp_status.configure(text="Sign in to see your Spotify playlists here.")
            self.sp_btn.configure(text="Sign in with Spotify", fg_color=RED, hover_color=RED_HOVER)
            self.sp_refresh.pack_forget()
            for w in self.pl_frame.winfo_children():
                w.destroy()

    def toggle_sign_in(self):
        if spotify_auth.signed_in():
            spotify_auth.sign_out()
            self.settings.pop("spotify_name", None)
            self.save_settings()
            self._sp_ui()
            return
        if not spotify_auth.client_id():
            messagebox.showinfo(APP_NAME, "Spotify sign-in isn't set up on this copy yet.\n\n"
                                "Open Settings and paste the Spotify Client ID. Until then you can still paste "
                                "playlist links below.", parent=self)
            return
        self.set_status("Finish signing in in your web browser…")
        self.sp_btn.configure(state="disabled")

        def done(name):
            self.sp_btn.configure(state="normal")
            self.settings["spotify_name"] = name
            self.save_settings()
            self._sp_ui()
            self.set_status("Signed in to Spotify.")
            self.refresh_playlists()

        def fail(e):
            self.sp_btn.configure(state="normal")
            self._sp_ui()
            if isinstance(e, spotify_auth.NotOnList):
                self.set_status("")
                SpotifyHelp(self, not_on_list=True)
            else:
                self.show_error(e)
        self.bg(spotify_auth.sign_in, done, fail)

    def refresh_playlists(self):
        self.set_status("Getting your Spotify playlists…")

        def done(pls):
            for w in self.pl_frame.winfo_children():
                w.destroy()
            for p in pls:
                n = f"{p['count']} songs" if p.get("count") is not None else ""
                by = "" if p["mine"] else f"   by {p['owner']}"
                b = ctk.CTkButton(self.pl_frame, text=f"{p['name']}      {n}{by}", anchor="w", height=28,
                                  fg_color="transparent", hover_color="#2A2D34", text_color=TEXT,
                                  command=lambda p=p: self.load_spotify_playlist(p))
                b.pack(fill="x")
            if not pls:
                ctk.CTkLabel(self.pl_frame, text="No playlists in this Spotify account.", text_color=MUTED).pack()
            self.set_status(f"{len(pls)} Spotify playlists.")

        def fail(e):
            self._sp_ui()
            if isinstance(e, spotify_auth.NotOnList):
                self.set_status("")
                SpotifyHelp(self, not_on_list=True)
            else:
                self.show_error(e)
        self.bg(spotify_auth.my_playlists, done, fail)

    def load_spotify_playlist(self, p):
        self.set_status(f"Reading “{p['name']}” from Spotify…")
        self.bg(lambda: spotify_auth.playlist_songs(p["id"], p["name"]),
                lambda r: self.got_requests(r, from_spotify=True))

    def load_link(self):
        url = self.link.get().strip()
        if not url:
            return
        links = list(sources.SPOTIFY_RE.finditer(url))
        if not links:
            messagebox.showinfo(APP_NAME, "That doesn't look like a Spotify link. In Spotify: … → Share → "
                                "Copy link to playlist, then paste it here.", parent=self)
            return
        if len(links) > 1:  # several playlists pasted at once: each becomes its own sub-list
            self.set_status(f"Reading {len(links)} playlists from Spotify…")
            self.bg(lambda: self._several_playlists(links), self.got_requests)
            return
        self.set_status("Reading the playlist from Spotify…")
        m = links[0]
        if m.group(1) == "playlist" and spotify_auth.signed_in():
            self.bg(lambda: spotify_auth.playlist_songs(m.group(2)), lambda r: self.got_requests(r, from_spotify=True))
        else:
            self.bg(lambda: sources.spotify_list(url), lambda r: self.got_requests(r, from_spotify=True))

    def _several_playlists(self, links):
        """Several playlist links -> one list with a section per playlist (full length when signed in)."""
        reqs, note = [], None
        for m in links:
            if m.group(1) == "playlist" and spotify_auth.signed_in():
                r, n, nt = spotify_auth.playlist_songs(m.group(2))
            else:
                r, n, nt = sources.spotify_list(m.group(0))
            for q in r:
                q["section"] = n
            reqs += r
            note = note or nt
        return reqs, f"Client request {datetime.date.today():%b %d}", note

    # ---------- text / files ----------
    def load_text(self):
        text = self.text.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo(APP_NAME, "Paste the client's song list into the box first (or open a file).", parent=self)
            return
        self.set_status("Reading the list…")
        prog = lambda d, t: self.set_status(f"Looking up Spotify songs… {d}/{t}")
        self.bg(lambda: sources.from_text(text, prog), lambda r: self.got_requests((r[0], r[1], r[2])))

    def open_file(self):
        p = filedialog.askopenfilename(parent=self, title="Open the client's song list",
                                       filetypes=[("Song lists", "*.txt *.csv *.docx *.pdf *.m3u *.m3u8"),
                                                  ("All files", "*.*")])
        if not p:
            return
        self.set_status(f"Reading {os.path.basename(p)}…")
        prog = lambda d, t: self.set_status(f"Looking up Spotify songs… {d}/{t}")

        def done(r):
            reqs, name, note = r
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self._as_text(reqs, None))
            self.got_requests(r)
        self.bg(lambda: sources.from_file(p, prog), done)

    def got_requests(self, r, from_spotify=False):
        reqs, name, note = r
        if not reqs:
            self.show_error("No songs found in that list.")
            return
        if from_spotify and self.reqs:
            have = self.name.get().strip() or "the current list"
            add = messagebox.askyesnocancel(
                APP_NAME, f"You already have “{have}” loaded.\n\n"
                f"Add “{name}” to it as its own sub-list?\n\n"
                "Yes:  keep both, one folder in VirtualDJ with a sub-list for each playlist\n"
                "No:  start over with just this playlist", parent=self)
            if add is None:
                self.set_status("")
                return
            if add:
                old = self.reqs
                if all(q.get("section") is None for q in old):
                    for q in old:
                        q["section"] = self.loaded_name or have
                for q in reqs:
                    q["section"] = name
                self.reqs = old + reqs
                self.pending_note = note
                if self.name.get().strip() == (self.loaded_name or ""):
                    self.name.delete(0, "end")
                    self.name.insert(0, f"Client request {datetime.date.today():%b %d}")
                self.set_status("Added. Rename the playlist (bottom left) to the event's name if you like.")
                if self.lib is not None:
                    self.rematch()
                return
        self.reqs = reqs
        self.loaded_name = name
        self.name.delete(0, "end")
        self.name.insert(0, name or f"Client request {datetime.date.today():%b %d}")
        self.pending_note = note
        if self.lib is None:
            self.set_status(f"{len(reqs)} songs requested. Waiting for your music library to finish loading…")
            return
        self.rematch()

    # ---------- library ----------
    def load_library(self):
        if self.lib_busy:
            return
        self.lib_busy = True
        self.lib_label.configure(text="Loading your music…", text_color=MUTED)
        folders = self.settings.get("folders", [])
        home = self.vdj_home

        def work():
            entries = library.load_library(home, folders, progress=lambda m: self.after(
                0, lambda: self.lib_label.configure(text=m)))
            return match.Library(entries)

        def done(lib):
            self.lib_busy = False
            self.lib = lib
            n_vdj = sum(1 for it in lib.items if it.entry["in_vdj"])
            parts = [f"{len(lib):,} songs"]
            if home:
                parts.append(f"{n_vdj:,} from VirtualDJ")
            nf = len(self.settings.get("folders", []))
            parts.append(f"{nf} music folder{'s' if nf != 1 else ''}")
            if not home:
                parts.append("VirtualDJ not found (Settings)")
            self.lib_label.configure(text="  ·  ".join(parts), text_color=TEXT if len(lib) else CHECK_C)
            if not len(lib):
                self.lib_label.configure(text="No songs found yet. Click “Music folders…” and choose where your music is.")
            if self.reqs:
                self.rematch()

        def fail(e):
            self.lib_busy = False
            self.lib_label.configure(text="Couldn't load your music", text_color=MISS_C)
            self.show_error(e)
        self.bg(work, done, fail)

    def edit_folders(self):
        FolderDialog(self)

    # ---------- matching ----------
    def rematch(self):
        self.settings["prefer_clean"] = bool(self.clean.get())
        self.save_settings()
        if not self.reqs or self.lib is None:
            return
        reqs, lib, clean = self.reqs, self.lib, bool(self.clean.get())
        self.set_status(f"Matching {len(reqs)} songs…")

        def done(results):
            self.results = results
            self.choice = {i: m["entry"] for i, m in enumerate(results)}
            self.fill_table()
            if self.pending_note:
                note, self.pending_note = self.pending_note, None
                messagebox.showinfo(APP_NAME, note, parent=self)
        self.bg(lambda: match.match_all(reqs, lib, clean), done)

    def _row_status(self, i):
        m = self.results[i]
        if m["status"] == "missing" and self.choice.get(i) is None:
            return "missing"
        if self.choice.get(i) is None:
            return "skip"
        return m["status"] if self.choice[i] is m["entry"] else "found"

    # ---------- sections ----------
    OTHER = "Other requests"

    def _sections(self):
        """[(section name or None, [row indexes])] in the client's order."""
        out = {}
        for i, m in enumerate(self.results):
            out.setdefault(m["req"].get("section"), []).append(i)
        return list(out.items())

    def _has_sections(self):
        return len(self._sections()) > 1

    def _split_changed(self):
        self.settings["split_sections"] = bool(self.split.get())
        self.save_settings()

    def _as_text(self, reqs, name):
        """Request list -> editable text, with each section as a heading line."""
        lines = [f"Playlist: {name}", ""] if name else []
        sec = object()
        for q in reqs:
            s = q.get("section")
            if s != sec:
                if lines and lines[-1] != "":
                    lines.append("")
                if s is not None or any(x.get("section") for x in reqs):
                    lines.append(f"{s or self.OTHER}:")
                sec = s
            lines.append(q["raw"])
        return "\n".join(lines) + "\n"

    def edit_as_text(self):
        if not self.reqs:
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self._as_text(self.reqs, self.name.get().strip()))
        self.tabs.set("Text list or document")
        self.set_status("Add headings like “Cocktail hour:” above groups of songs to split them into sub-lists, "
                        "then click “Find these songs”.")

    def fill_table(self):
        self.tree.delete(*self.tree.get_children())
        groups = self._sections()
        show_heads = len(groups) > 1
        for k, (sec, rows) in enumerate(groups):
            if show_heads:
                self.tree.insert("", "end", iid=f"sec{k}", tags=("section",),
                                 values=("", f"▾  {sec or self.OTHER}   ({len(rows)} song{'s' if len(rows) != 1 else ''})", ""))
            for i in rows:
                m = self.results[i]
                st = self._row_status(i)
                self.tree.insert("", "end", iid=str(i), values=(STATUS_TEXT[st], m["req"]["raw"], self._file_text(i)),
                                 tags=(st,))
        if show_heads:
            self.split.pack(side="left", padx=4, after=self.clean)
        else:
            self.split.pack_forget()
        self.edit_btn.configure(state="normal")
        self.update_summary()

    def _file_label(self, e):
        return os.path.basename(e["path"]) + "     " + os.path.dirname(e["path"])

    def _file_text(self, i):
        e = self.choice.get(i)
        if e:
            return self._file_label(e)
        alts = self.results[i]["alts"]
        if alts:  # not sure enough to use it, but worth showing
            return f"closest: {os.path.basename(alts[0][1]['path'])}   (double-click to use it)"
        return ""

    def update_summary(self):
        sts = [self._row_status(i) for i in range(len(self.results))]
        n_in = sum(1 for i in range(len(self.results)) if self.choice.get(i))
        c = {s: sts.count(s) for s in ("found", "check", "missing", "skip")}
        txt = f"{n_in} of {len(sts)} songs ready"
        if c["check"]:
            txt += f"  ·  {c['check']} to double-check (yellow)"
        if c["missing"]:
            txt += f"  ·  {c['missing']} not in your library"
        self.summary.configure(text=txt)
        self.make_btn.configure(state="normal" if n_in else "disabled")
        self.miss_btn.configure(state="normal" if c["missing"] else "disabled")
        self.set_status("")

    def _refresh_row(self, i):
        st = self._row_status(i)
        self.tree.item(str(i), values=(STATUS_TEXT[st], self.results[i]["req"]["raw"], self._file_text(i)), tags=(st,))
        self.update_summary()

    def toggle_row(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid or iid.startswith("sec"):
            return
        i = int(iid)
        m = self.results[i]
        if self.choice.get(i) is None:
            self.choice[i] = m["entry"] or (m["alts"][0][1] if m["alts"] else None)
        else:
            self.choice[i] = None
        self._refresh_row(i)

    def row_menu(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid or iid.startswith("sec"):
            return
        self.tree.selection_set(iid)
        i = int(iid)
        m = self.results[i]
        menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT, activebackground=RED, activeforeground="white", bd=0)
        cur = self.choice.get(i)
        if m["alts"]:
            menu.add_command(label="Use one of these files:", state="disabled")
            for s, e in m["alts"]:
                mark = "●  " if e is cur else "     "
                menu.add_command(label=f"{mark}{os.path.basename(e['path'])}   ({min(s, 1):.0%} match)",
                                 command=lambda e=e: self._choose(i, e))
            menu.add_separator()
        menu.add_command(label="Choose a file myself…", command=lambda: self._choose_file(i))
        if cur is not None:
            menu.add_command(label="Leave this song out", command=lambda: self._choose(i, None))
            menu.add_command(label="Show file in Explorer", command=lambda: subprocess.Popen(
                ["explorer", "/select,", cur["path"]]))
        menu.tk_popup(ev.x_root, ev.y_root)

    def _choose(self, i, e):
        self.choice[i] = e
        self._refresh_row(i)

    def _choose_file(self, i):
        p = filedialog.askopenfilename(parent=self, title="Choose the song file",
                                       filetypes=[("Music", " ".join("*" + x for x in sorted(library.MEDIA))),
                                                  ("All files", "*.*")])
        if p:
            a, t, ln = library.read_tags(p)
            self._choose(i, library.make_entry(os.path.normpath(p), a, t, ln))

    # ---------- output ----------
    def copy_missing(self):
        miss = [self.results[i]["req"]["raw"] for i in range(len(self.results)) if self._row_status(i) == "missing"]
        self.clipboard_clear()
        self.clipboard_append("\n".join(miss))
        self.set_status(f"Copied {len(miss)} missing songs. Paste them anywhere (e.g. a note or Wavegrab).")

    def create_playlist(self):
        if not self.vdj_home:
            messagebox.showerror(APP_NAME, "Couldn't find VirtualDJ on this PC. Open VirtualDJ once, or set its "
                                 "folder in Settings.", parent=self)
            return
        name = vdj.safe_name(self.name.get())
        rows = [i for i in range(len(self.results)) if self.choice.get(i)]
        if vdj.list_exists(self.vdj_home, name) and not messagebox.askyesno(
                APP_NAME, f"VirtualDJ already has a list called “{name}”. Replace it?", parent=self):
            return
        sections = None
        if self._has_sections() and self.split.get():
            sections = []
            for sec, srows in self._sections():
                keep = [i for i in srows if self.choice.get(i)]
                if keep:
                    sections.append((sec or self.OTHER, [self.choice[i] for i in keep],
                                     [self.results[i]["req"] for i in keep]))
        try:
            vdj.write_playlist(self.vdj_home, name, [self.choice[i] for i in rows],
                               [self.results[i]["req"] for i in rows], sections=sections)
        except OSError as e:
            self.show_error(f"Couldn't save the playlist: {e}")
            return
        if sections:
            msg = (f"Made “{name}” with {len(rows)} songs, plus a sub-list for each part:\n\n"
                   + "\n".join(f"   •  {s}  ({len(e)})" for s, e, _ in sections)
                   + f"\n\nIn VirtualDJ, look under My Lists. “{name}” has all the songs; click the + next to "
                     "it to see the sub-lists.")
        else:
            msg = f"Made “{name}” with {len(rows)} songs.\n\nIn VirtualDJ, look under My Lists on the left."
        if vdj.is_running():
            msg += ("\n\nVirtualDJ is open right now, so click the little − next to My Lists and then + "
                    "to make the new list appear.")
        self.set_status(f"Created “{name}” in VirtualDJ.")
        messagebox.showinfo(APP_NAME, msg, parent=self)

    # ---------- settings ----------
    def open_settings(self):
        SettingsDialog(self)


HELP_STEPS = [
    ("Click “Sign in with Spotify”.", "A small Spotify window pops up."),
    ("Log in the way you always do.", "Email and password, or Continue with Google / Facebook / Apple."),
    ("Click “Agree”.", "The window closes by itself and your playlists show up in CrateMatch."),
    ("Click a playlist.", "CrateMatch finds those songs in your music. Saved a client's playlist in Spotify? "
                          "It's in the list too."),
]
HELP_NOT_ON_LIST = [
    ("Find the email on your Spotify account.",
     "In the Spotify app: click your picture (top right) → Account. Your web browser opens; click "
     "“Edit profile” and your email is shown there. If you log in to Spotify with Google, Facebook "
     "or Apple, it's the email of that account."),
    ("Send that email to the person who set up CrateMatch for you.",
     "Click “Copy a message” below and paste it into a text or email. They add you in under a minute "
     "(Spotify only lets up to 5 people they choose use this sign-in)."),
    ("When they say you're added, click “Sign in with Spotify” again.",
     "That's it. You'll stay signed in from then on."),
]


class SpotifyHelp(ctk.CTkToplevel):
    """Step-by-step Spotify sign-in help, or what to do when the account isn't on the list yet."""

    def __init__(self, app, not_on_list=False):
        super().__init__(app)
        self.app = app
        self.title("Spotify sign-in")
        self.geometry("600x620" if not_on_list else "600x480")
        self.configure(fg_color=BG)
        self.transient(app)
        self.after(50, self.grab_set)
        center_over(self, app)
        big = ctk.CTkFont(size=18, weight="bold")
        f_step = ctk.CTkFont(size=14, weight="bold")
        if not_on_list:
            ctk.CTkLabel(self, text="Almost there: your Spotify isn't on the list yet", font=big,
                         text_color=TEXT).pack(anchor="w", padx=20, pady=(18, 4))
            ctk.CTkLabel(self, text="Spotify only lets accounts that have been added use CrateMatch's sign-in. "
                         "Here's how to get added:", text_color=MUTED, wraplength=550,
                         justify="left").pack(anchor="w", padx=20, pady=(0, 8))
            steps = HELP_NOT_ON_LIST
        else:
            ctk.CTkLabel(self, text="Signing in with Spotify", font=big, text_color=TEXT).pack(
                anchor="w", padx=20, pady=(18, 8))
            steps = HELP_STEPS
        for n, (head, body) in enumerate(steps, 1):
            row = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=8)
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row, text=str(n), width=34, height=34, corner_radius=17, fg_color=RED,
                         text_color="white", font=f_step).pack(side="left", padx=12, pady=10, anchor="n")
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 12))
            ctk.CTkLabel(col, text=head, font=f_step, text_color=TEXT, anchor="w", justify="left",
                         wraplength=470).pack(anchor="w")
            ctk.CTkLabel(col, text=body, text_color=MUTED, anchor="w", justify="left",
                         wraplength=470).pack(anchor="w")
        tail = ("Good to know: you stay signed in, so next time your playlists are already there. "
                "Spotify asks you to sign in again roughly every 6 months.") if not not_on_list else \
            ("Until then, you can still paste a Spotify playlist link into the box under the sign-in "
             "button (in Spotify: … → Share → Copy link to playlist).")
        ctk.CTkLabel(self, text=tail, text_color=MUTED, wraplength=550, justify="left").pack(
            anchor="w", padx=20, pady=(10, 0))
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=16, side="bottom")
        ctk.CTkButton(btns, text="OK", width=100, fg_color=RED, hover_color=RED_HOVER,
                      command=self.destroy).pack(side="right")
        if not_on_list:
            self.copied = ctk.CTkLabel(btns, text="", text_color=OK_C)
            ctk.CTkButton(btns, text="Copy a message", width=150, fg_color="#2A2D34", hover_color="#353943",
                          command=self.copy_msg).pack(side="left")
            self.copied.pack(side="left", padx=10)

    def copy_msg(self):
        self.clipboard_clear()
        self.clipboard_append("Hi! Please add me to CrateMatch's Spotify sign-in.\n"
                              "My name: \nMy Spotify email: \n")
        self.copied.configure(text="Copied. Paste it into a text and fill in your email.")


class FolderDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Music folders")
        self.geometry("620x380")
        self.configure(fg_color=BG)
        self.transient(app)
        self.after(50, self.grab_set)
        center_over(self, app)
        ctk.CTkLabel(self, text="Folders with your music", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(self, text="Songs already in VirtualDJ's library are always included. Add folders here for "
                     "anything VirtualDJ hasn't seen yet.\nSub-folders are searched too.",
                     text_color=MUTED, justify="left").pack(anchor="w", padx=16, pady=(2, 8))
        self.box = tk.Listbox(self, bg=PANEL, fg=TEXT, selectbackground=RED, borderwidth=0, highlightthickness=0,
                              font=("Segoe UI", 10), activestyle="none")
        self.box.pack(fill="both", expand=True, padx=16)
        self.folders = list(app.settings.get("folders", []))
        for f in self.folders:
            self.box.insert("end", f)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(row, text="Add folder…", width=110, fg_color="#2A2D34", hover_color="#353943",
                      command=self.add).pack(side="left")
        ctk.CTkButton(row, text="Remove", width=90, fg_color="#2A2D34", hover_color="#353943",
                      command=self.remove).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Done", width=110, fg_color=RED, hover_color=RED_HOVER, command=self.done).pack(side="right")

    def add(self):
        d = filedialog.askdirectory(parent=self, title="Choose a music folder")
        if d:
            d = os.path.normpath(d)
            if d not in self.folders:
                self.folders.append(d)
                self.box.insert("end", d)

    def remove(self):
        for i in reversed(self.box.curselection()):
            self.box.delete(i)
            del self.folders[i]

    def done(self):
        changed = self.folders != self.app.settings.get("folders", [])
        self.app.settings["folders"] = self.folders
        self.app.save_settings()
        self.destroy()
        if changed:
            self.app.load_library()


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Settings")
        self.geometry("620x330")
        self.configure(fg_color=BG)
        self.transient(app)
        self.after(50, self.grab_set)
        center_over(self, app)
        f = ctk.CTkFont(size=14, weight="bold")
        ctk.CTkLabel(self, text="VirtualDJ folder", font=f).pack(anchor="w", padx=16, pady=(14, 2))
        r = ctk.CTkFrame(self, fg_color="transparent")
        r.pack(fill="x", padx=16)
        self.home = ctk.CTkEntry(r)
        self.home.insert(0, app.vdj_home or "")
        self.home.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r, text="Change…", width=90, fg_color="#2A2D34", hover_color="#353943",
                      command=self.pick_home).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(self, text="Found automatically. Only change this if VirtualDJ keeps its files somewhere unusual.",
                     text_color=MUTED, font=app.f_small).pack(anchor="w", padx=16)
        # Only shown on a build without the Client ID built in (normal users never see it)
        self.cid = None
        if not spotify_auth.DEFAULT_CLIENT_ID:
            ctk.CTkLabel(self, text="Spotify Client ID", font=f).pack(anchor="w", padx=16, pady=(14, 2))
            self.cid = ctk.CTkEntry(self)
            self.cid.insert(0, app.settings.get("spotify_client_id", ""))
            self.cid.pack(fill="x", padx=16)
            ctk.CTkLabel(self, text="From developer.spotify.com → your app. Redirect URI: " + spotify_auth.REDIRECT,
                         text_color=MUTED, font=app.f_small).pack(anchor="w", padx=16)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16, side="bottom")
        ctk.CTkLabel(row, text=f"{APP_NAME} {VERSION}", text_color=MUTED).pack(side="left")
        ctk.CTkButton(row, text="Save", width=110, fg_color=RED, hover_color=RED_HOVER, command=self.save).pack(side="right")

    def pick_home(self):
        d = filedialog.askdirectory(parent=self, title="VirtualDJ folder (has MyLists and database.xml)")
        if d:
            self.home.delete(0, "end")
            self.home.insert(0, os.path.normpath(d))

    def save(self):
        home = self.home.get().strip()
        if home and not os.path.isdir(home):
            messagebox.showerror(APP_NAME, "That VirtualDJ folder doesn't exist.", parent=self)
            return
        changed = home != (self.app.vdj_home or "")
        if home and home != vdj.find_home():
            self.app.settings["vdj_home"] = home
        else:
            self.app.settings.pop("vdj_home", None)
        self.app.vdj_home = home or vdj.find_home()
        cid = self.cid.get().strip() if self.cid else self.app.settings.get("spotify_client_id", "")
        if cid != self.app.settings.get("spotify_client_id", ""):
            self.app.settings["spotify_client_id"] = cid
            spotify_auth.sign_out()
            self.app._sp_ui()
        self.app.save_settings()
        self.destroy()
        if changed:
            self.app.load_library()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    App().mainloop()
