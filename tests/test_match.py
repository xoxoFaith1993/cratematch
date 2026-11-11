"""Quick checks of the matcher on messy, DJ-style file names. Run: python tests\\test_match.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cratematch.library import make_entry
from cratematch.match import Library, match_one
from cratematch.sources import parse_line, _req

LIB = [
    make_entry(r"D:\Music\Pop\Mark Ronson - Uptown Funk (feat. Bruno Mars) [Clean].mp3"),
    make_entry(r"D:\Music\Pop\01. Uptown Funk (Instrumental).mp3", "Mark Ronson", "Uptown Funk (Instrumental)"),
    make_entry(r"D:\Music\Wedding\Ed Sheeran - Perfect.wav"),
    make_entry(r"D:\Music\Wedding\Ed Sheeran - Perfect (Acoustic).wav"),
    make_entry(r"D:\Music\Hip Hop\Drake\Hotline Bling.mp3"),
    make_entry(r"D:\Music\x.mp3", "Beyoncé", "Crazy In Love (feat. JAY-Z)", 236),
    make_entry(r"D:\Music\Dance\Avicii - Levels (Skrillex Remix).mp3"),
    make_entry(r"D:\Music\Dance\Avicii - Levels (Radio Edit).mp3"),
    make_entry(r"D:\Music\Oldies\earth wind & fire - september.mp3"),
    make_entry(r"D:\Music\Oldies\Sam Smith - Stay With Me.mp3"),
    make_entry(r"D:\Music\Oldies\Lana Del Rey - Video Games.mp3"),
    make_entry(r"D:\Music\Oldies\Whitney Houston - I Wanna Dance With Somebody (Who Loves Me).mp3"),
    make_entry(r"D:\Music\Love Story.mp3", "Taylor Swift", "Love Story"),
    make_entry(r"D:\Music\Love Songs\Love.mp3", "Kendrick Lamar", "LOVE."),
    make_entry(r"D:\Music\Party\Pitbull - Timber ft. Kesha (Dirty).mp3"),
    make_entry(r"D:\Music\Party\Pitbull - Timber ft. Kesha (Clean).mp3"),
    make_entry(r"D:\Music\Party\Shut Up And Dance - Walk The Moon.mp3"),
    make_entry(r"D:\Music\Video\Bruno Mars - 24K Magic (Official Music Video).mp4"),
]

# (request, expected file name or None, ok statuses)
CASES = [
    (_req("Mark Ronson, Bruno Mars", "Uptown Funk (feat. Bruno Mars)", 270), "[Clean].mp3", {"found"}),
    (parse_line("1. Ed Sheeran - Perfect"), "Ed Sheeran - Perfect.wav", {"found"}),
    (parse_line("Perfect by Ed Sheeran"), "Ed Sheeran - Perfect.wav", {"found"}),
    (parse_line("Perfect - Ed Sheeran"), "Ed Sheeran - Perfect.wav", {"found"}),
    (parse_line("Hotline Bling - Drake"), "Hotline Bling.mp3", {"found", "check"}),
    (_req("Beyoncé, JAY-Z", "Crazy In Love (feat. JAY-Z)"), "x.mp3", {"found"}),
    (parse_line("beyonce crazy in love"), None, {"missing", "check"}),
    (parse_line("Crazy in Love"), "x.mp3", {"found", "check"}),
    (_req("Avicii", "Levels - Radio Edit"), "(Radio Edit).mp3", {"found"}),
    (_req("Avicii", "Levels - Skrillex Remix"), "(Skrillex Remix).mp3", {"found"}),
    (_req("Avicii", "Levels"), "(Radio Edit).mp3", {"found"}),
    (parse_line("• September — Earth, Wind & Fire"), "september.mp3", {"found"}),
    (parse_line("Stay With Me - Sam Smith"), "Stay With Me.mp3", {"found"}),
    (parse_line("Lana Del Rey - Video Games"), "Video Games.mp3", {"found"}),
    (parse_line("Whitney Houston - I Wanna Dance with Somebody"), "Somebody (Who", {"found", "check"}),
    (parse_line("Taylor Swift - Love Story (Taylor's Version)"), "Love Story.mp3", {"found", "check"}),
    (parse_line("Love Story"), "Love Story.mp3", {"found", "check"}),
    (parse_line("Taylor Swift - Shake It Off"), None, {"missing"}),
    (_req("Pitbull, Kesha", "Timber"), "Timber", {"found"}),
    (parse_line("Walk the Moon - Shut Up and Dance"), "Shut Up And Dance", {"found"}),
    (parse_line("Bruno Mars - 24K Magic"), "24K Magic", {"found"}),
    (parse_line("Uptwon Funk - Mark Ronson"), "[Clean].mp3", {"found", "check"}),
    (parse_line("Bruno Mars - Uptown Funk"), "[Clean].mp3", {"found"}),
    (parse_line("Mark Ronson - Uptown Funk (Instrumental)"), "(Instrumental).mp3", {"found"}),
]


def main():
    lib = Library(LIB)
    bad = 0
    for req, want, ok in CASES:
        m = match_one(req, lib, prefer_clean="Timber" in req["title"])
        got = os.path.basename(m["entry"]["path"]) if m["entry"] else None
        good = m["status"] in ok and ((want is None and (got is None or m["status"] != "found")) or (want and got and want in got))
        bad += not good
        print(f"{'ok ' if good else 'BAD'} {m['status']:7} {m['score']:.2f}  {req['raw'][:50]:50} -> {got}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
