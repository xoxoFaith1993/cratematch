"""Reading client lists in different shapes: .txt, .csv, .docx. Run: python tests\\test_sources.py"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cratematch import sources

TXT = """Wedding playlist - must play!

1. Ed Sheeran - Perfect
2) Uptown Funk by Mark Ronson
3.	September – Earth, Wind & Fire
- Shut Up and Dance (Walk the Moon)
• Beyoncé — Crazy in Love 3:56
Don't Stop Believin' - Journey
Cha Cha Slide
Silly Love Songs - Wings

DO NOT PLAY:
Macarena
Chicken Dance - Polka Band

First Dance
At Last - Etta James
"""

CSV = '''"Track URI","Track Name","Artist URI(s)","Artist Name(s)","Album Name","Duration (ms)"
"spotify:track:1","Perfect","x","Ed Sheeran","÷","263400"
"spotify:track:2","Crazy In Love (feat. JAY-Z)","x","Beyoncé;JAY-Z","Dangerously","236133"
'''

DOCX_XML = ('<?xml version="1.0"?><w:document xmlns:w="w"><w:body>'
            '<w:p><w:r><w:t>Reception songs</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Ed Sheeran - Perfect</w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">Journey </w:t></w:r><w:r><w:t>- Don&apos;t Stop Believin&apos;</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Levels</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Avicii</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '</w:body></w:document>')


def show(label, reqs):
    print(f"--- {label}: {len(reqs)} songs")
    for r in reqs:
        print(f"   artist={r['artist']!r:28} title={r['title']!r:34} swap={r['swap']} dur={r['duration']}")


def main():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "list.txt")
    open(p, "w", encoding="utf-8").write(TXT)
    reqs, _, note = sources.from_file(p)
    show(f"txt (note={note!r})", reqs)
    p = os.path.join(d, "export.csv")
    open(p, "w", encoding="utf-8").write(CSV)
    show("csv", sources.from_file(p)[0])
    p = os.path.join(d, "Smith wedding.docx")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", DOCX_XML)
    reqs, name, _ = sources.from_file(p)
    show(f"docx (name={name!r})", reqs)
    # cp1252 file (Notepad "ANSI")
    p = os.path.join(d, "ansi.txt")
    open(p, "wb").write("Beyonc\xe9 - Halo\r\n".encode("cp1252"))
    show("ansi txt", sources.from_file(p)[0])


if __name__ == "__main__":
    main()
