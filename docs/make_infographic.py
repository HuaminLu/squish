"""Builds docs/squish-infographic.png: a shareable one-image overview of the app."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SS = os.path.join(HERE, "screenshots")
OUT = os.path.join(HERE, "squish-infographic.png")
W, H = 1600, 900
BLACK, WHITE, GREY, FAINT = (0, 0, 0), (255, 255, 255), (154, 154, 154), (58, 58, 58)

def font(name, size):
    for cand in [name, "segoeui.ttf"]:
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", cand)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

img = Image.new("RGB", (W, H), BLACK)
d = ImageDraw.Draw(img)

# Left column: brand
icon = Image.open(os.path.join(HERE, "..", "desktop", "icon.png")).convert("RGBA").resize((96, 96), Image.LANCZOS)
img.paste(icon, (70, 70), icon)
d.text((186, 58), "squish", font=font("segoeuib.ttf", 84), fill=WHITE)
d.text((190, 160), "simple video compressor", font=font("segoeuii.ttf", 30), fill=GREY)

d.line([(70, 220), (700, 220)], fill=FAINT, width=2)

big = font("segoeuib.ttf", 64)
d.text((70, 250), "278 MB", font=big, fill=GREY)
d.text((330, 250), "→", font=big, fill=WHITE)
d.text((420, 250), "9.7 MB", font=big, fill=WHITE)
d.text((72, 335), "same clip, still looks the same on Discord", font=font("segoeuii.ttf", 26), fill=GREY)

steps = [("1", "Pick a video", "any size, any format"),
         ("2", "Pick a limit", "5 · 8 · 10 · 20 MB or custom"),
         ("3", "Squish It", "always under the limit, saved to Downloads")]
y = 410
for n, t, sub in steps:
    d.rounded_rectangle([70, y, 126, y + 56], radius=12, fill=WHITE)
    d.text((98, y + 28), n, font=font("segoeuib.ttf", 30), fill=BLACK, anchor="mm")
    d.text((146, y - 2), t, font=font("segoeuib.ttf", 30), fill=WHITE)
    d.text((148, y + 32), sub, font=font("segoeui.ttf", 22), fill=GREY)
    y += 92

d.rounded_rectangle([70, 700, 700, 760], radius=14, outline=WHITE, width=2)
d.text((385, 730), "Windows exe  ·  Android apk  ·  100 % offline", font=font("segoeuib.ttf", 24), fill=WHITE, anchor="mm")
d.text((70, 790), "github.com/HuaminLu/squish  →  Releases  →  Squish.exe", font=font("segoeui.ttf", 24), fill=GREY)
d.text((70, 826), "Portable, nothing to install. SmartScreen: More info → Run anyway.", font=font("segoeui.ttf", 20), fill=GREY)

# Right: Windows picked + done, and the Android done shot
def shadow_paste(im, pos, radius=18):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=radius, fill=255)
    border = Image.new("RGB", (im.width + 4, im.height + 4), FAINT)
    bm = Image.new("L", border.size, 0)
    ImageDraw.Draw(bm).rounded_rectangle([0, 0, border.width - 1, border.height - 1], radius=radius + 2, fill=255)
    img.paste(border, (pos[0] - 2, pos[1] - 2), bm)
    img.paste(im, pos, m)

win = Image.open(os.path.join(SS, "windows-4-done.png")).convert("RGB")
win = win.resize((int(win.width * 0.78), int(win.height * 0.78)), Image.LANCZOS)   # ~608 x 733
shadow_paste(win, (760, 80))
droid = Image.open(os.path.join(SS, "android-4-done.png")).convert("RGB")
droid = droid.resize((int(droid.width * 0.62), int(droid.height * 0.62)), Image.LANCZOS)  # ~335 x 725
shadow_paste(droid, (1215, 80), radius=28)

img.save(OUT, optimize=True)
print("wrote", OUT, img.size)
