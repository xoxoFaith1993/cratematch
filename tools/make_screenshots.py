"""Runs CrateMatch on the test library and saves README screenshots to docs\\.
Needs tests\\library (python tests\\make_test_library.py) in the music folders."""
import os
import subprocess
import sys
from tkinter import messagebox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cratematch import app as A
from cratematch import spotify_auth

DOCS = os.path.join(ROOT, "docs")
LINK = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
TEXT = """Johnson Wedding - song requests

Cocktail hour:
1. Tame Impala - Loser
2. Babydoll by Dominic Fike
3. Ashe - Stop The Wedding!

Reception / dance floor:
- Shakira - Dai Dai
- dtmf - bad bunny
- KAROL G - BbY WOW
- Tate McRae - Housewfie
- Mark Ronson - Uptown Funk

First Dance:
Beyonce - Halo

DO NOT PLAY:
Macarena
Chicken Dance
"""


def main():
    os.makedirs(DOCS, exist_ok=True)
    messagebox.showinfo = lambda *a, **k: None  # no pop-ups in the pictures
    spotify_auth.signed_in = lambda: False
    w = A.App()
    title = w.title()

    def shot(name):
        subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "capture.py"), title,
                          os.path.join(DOCS, name)])

    def wait_for(cond, then, tries=200):
        if cond():
            w.after(1200, then)
        elif tries:
            w.after(150, lambda: wait_for(cond, then, tries - 1))
        else:
            print("timed out")
            w.destroy()

    def step1():  # Spotify link
        w.tabs.set("Spotify")
        w.link.delete(0, "end")
        w.link.insert(0, LINK)
        w.results = []
        w.load_link()
        wait_for(lambda: bool(w.results), lambda: (shot("spotify-results.png"), w.after(2500, step2)))

    def step2():  # pasted client list
        w.tabs.set("Text list or document")
        w.text.delete("1.0", "end")
        w.text.insert("1.0", TEXT)
        first = w.results
        w.load_text()
        wait_for(lambda: w.results is not first and bool(w.results),
                 lambda: (w.after(300, lambda: shot("text-list-results.png")), w.after(2500, step3)))

    def step3():  # make the VirtualDJ list with a sub-list per section
        if "--create" in sys.argv:
            messagebox.askyesno = lambda *a, **k: True
            w.split.select()
            w.create_playlist()
        w.after(500, w.destroy)

    wait_for(lambda: w.lib is not None, step1)
    w.mainloop()


if __name__ == "__main__":
    main()
