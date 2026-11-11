"""Draws the CrateMatch icon (a record with a check mark) -> cratematch/assets/icon.png + icon.ico"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "cratematch", "assets")
N = 1024


def main():
    os.makedirs(OUT, exist_ok=True)
    icon = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    d.rounded_rectangle((40, 40, N - 40, N - 40), radius=230, fill=(200, 40, 60, 255))
    # record
    c, r = N / 2, 360
    d.ellipse((c - r, c - r, c + r, c + r), fill=(22, 22, 26, 255))
    for g in range(300, 140, -38):
        d.ellipse((c - g, c - g, c + g, c + g), outline=(55, 55, 62, 255), width=6)
    d.ellipse((c - 120, c - 120, c + 120, c + 120), fill=(200, 40, 60, 255))
    d.ellipse((c - 18, c - 18, c + 18, c + 18), fill=(22, 22, 26, 255))
    # check mark badge
    bx, by, br = 760, 760, 170
    d.ellipse((bx - br, by - br, bx + br, by + br), fill=(255, 255, 255, 255))
    pts = [(bx - 85, by + 5), (bx - 25, by + 70), (bx + 90, by - 60)]
    d.line(pts, fill=(200, 40, 60, 255), width=52, joint="curve")
    for p in (pts[0], pts[2]):
        d.ellipse((p[0] - 26, p[1] - 26, p[0] + 26, p[1] + 26), fill=(200, 40, 60, 255))
    big = icon.resize((256, 256), Image.LANCZOS)
    big.save(os.path.join(OUT, "icon.png"))
    big.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
