"""Draws the Squish icon: a compress glyph (two chevrons pressing toward a bar), white on a black
rounded tile with a white outline. Writes icon.ico/icon.png here and the Android launcher mipmaps."""
import os
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Black rounded tile with a white outline
d.rounded_rectangle([24, 24, S - 24, S - 24], radius=220, fill="black", outline="white", width=40)

W = 68   # stroke width
cx = S // 2
# Top chevron pointing down, bottom chevron pointing up
top = [(cx - 210, 250), (cx, 420), (cx + 210, 250)]
bot = [(cx - 210, S - 250), (cx, S - 420), (cx + 210, S - 250)]
for pts in (top, bot):
    d.line(pts, fill="white", width=W, joint="curve")
    for p in (pts[0], pts[-1]):  # round the line ends
        d.ellipse([p[0] - W // 2, p[1] - W // 2, p[0] + W // 2, p[1] + W // 2], fill="white")
    d.ellipse([pts[1][0] - W // 2, pts[1][1] - W // 2, pts[1][0] + W // 2, pts[1][1] + W // 2], fill="white")
# Centre bar
d.rounded_rectangle([cx - 250, cx - 34, cx + 250, cx + 34], radius=34, fill="white")

here = os.path.dirname(os.path.abspath(__file__))
png = img.resize((256, 256), Image.LANCZOS)
png.save(os.path.join(here, "icon.png"))
png.save(os.path.join(here, "icon.ico"),
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# Android launcher icons: same art on a full-bleed black square.
res = os.path.join(here, "..", "android_app", "android", "app", "src", "main", "res")
full = Image.new("RGBA", (S, S), "black")
full.alpha_composite(img)
for folder, size in {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96,
                     "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}.items():
    p = os.path.join(res, folder)
    os.makedirs(p, exist_ok=True)
    full.resize((size, size), Image.LANCZOS).save(os.path.join(p, "ic_launcher.png"))
# Adaptive icon: glyph only (no tile) in the safe zone on a black background.
glyph = Image.new("RGBA", (S, S), (0, 0, 0, 0))
g = ImageDraw.Draw(glyph)
for pts in (top, bot):
    g.line(pts, fill="white", width=W, joint="curve")
    for p in (pts[0], pts[1], pts[-1]):
        g.ellipse([p[0] - W // 2, p[1] - W // 2, p[0] + W // 2, p[1] + W // 2], fill="white")
g.rounded_rectangle([cx - 250, cx - 34, cx + 250, cx + 34], radius=34, fill="white")
fg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
art = glyph.resize((int(S * 0.56), int(S * 0.56)), Image.LANCZOS)
fg.alpha_composite(art, (int(S * 0.22), int(S * 0.22)))
for folder, size in {"mipmap-mdpi": 108, "mipmap-hdpi": 162, "mipmap-xhdpi": 216,
                     "mipmap-xxhdpi": 324, "mipmap-xxxhdpi": 432}.items():
    fg.resize((size, size), Image.LANCZOS).save(os.path.join(res, folder, "ic_launcher_foreground.png"))
os.makedirs(os.path.join(res, "mipmap-anydpi-v26"), exist_ok=True)
with open(os.path.join(res, "mipmap-anydpi-v26", "ic_launcher.xml"), "w") as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@color/ic_launcher_background"/>\n'
            '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n</adaptive-icon>\n')
os.makedirs(os.path.join(res, "values"), exist_ok=True)
with open(os.path.join(res, "values", "ic_launcher_background.xml"), "w") as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#000000</color>\n</resources>\n')
print("icons written")
