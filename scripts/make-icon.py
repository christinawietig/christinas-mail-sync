"""Zeichnet das App-Icon (Brief mit Sync-Pfeilen) und erzeugt assets/MailSync.{png,icns,ico}.

Aufruf (macOS, fuer .icns wird iconutil gebraucht):  python scripts/make-icon.py
"""
import math
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter

S = 4096  # in 4-facher Groesse zeichnen, dann verkleinern (glatte Kanten)
ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def vertical_gradient(size, top, bottom):
    g = Image.new("RGBA", (1, size))
    for y in range(size):
        g.putpixel((0, y), lerp(top, bottom, y / (size - 1)) + (255,))
    return g.resize((size, size))


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Hintergrund: abgerundetes Quadrat mit Blau-Verlauf und weichem Schatten
    m, r = int(S * 0.1), int(S * 0.18)
    box = (m, m, S - m, S - m)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((m, m + S * 0.015, S - m, S - m + S * 0.015), r, fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.012)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, r, fill=255)
    bg = vertical_gradient(S, (72, 170, 245), (24, 98, 222))
    img.paste(bg, (0, 0), mask)

    # Brief
    d = ImageDraw.Draw(img)
    ex0, ey0, ex1, ey1 = S * 0.2, S * 0.3, S * 0.8, S * 0.7
    w = int(S * 0.012)
    d.rounded_rectangle((ex0, ey0, ex1, ey1), int(S * 0.04), fill=(250, 252, 255))
    fold = (150, 185, 230)
    d.line([(ex0 + S * 0.03, ey0 + S * 0.03), ((ex0 + ex1) / 2, ey0 + S * 0.24), (ex1 - S * 0.03, ey0 + S * 0.03)],
           fill=fold, width=w, joint="curve")
    d.line([(ex0 + S * 0.03, ey1 - S * 0.03), (ex0 + S * 0.22, ey0 + S * 0.19)], fill=fold, width=w)
    d.line([(ex1 - S * 0.03, ey1 - S * 0.03), (ex1 - S * 0.22, ey0 + S * 0.19)], fill=fold, width=w)

    # Oranger Kreis mit zwei Pfeilen
    cx, cy, cr = S * 0.72, S * 0.72, S * 0.2
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((cx - cr, cy - cr + S * 0.01, cx + cr, cy + cr + S * 0.01), fill=(0, 0, 0, 80))
    img.alpha_composite(ring.filter(ImageFilter.GaussianBlur(S * 0.01)))
    cmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cmask).ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=255)
    img.paste(vertical_gradient(S, (255, 170, 60), (236, 100, 20)), (0, 0), cmask)
    d = ImageDraw.Draw(img)
    d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), outline=(255, 255, 255), width=int(S * 0.012))

    ar, aw = cr * 0.58, int(S * 0.045)
    for start in (200, 20):  # zwei Boegen, je mit Pfeilspitze am Ende
        end = start + 120
        d.arc((cx - ar, cy - ar, cx + ar, cy + ar), start, end, fill="white", width=aw)
        a = math.radians(end)
        tip = (cx + ar * math.cos(a), cy + ar * math.sin(a))
        tangent = a + math.pi / 2  # Laufrichtung des Bogens (im Uhrzeigersinn)
        length, half = aw * 1.3, aw * 1.05
        p1 = (tip[0] + length * math.cos(tangent), tip[1] + length * math.sin(tangent))
        normal = (math.cos(a), math.sin(a))
        p2 = (tip[0] + normal[0] * half, tip[1] + normal[1] * half)
        p3 = (tip[0] - normal[0] * half, tip[1] - normal[1] * half)
        d.polygon([p1, p2, p3], fill="white")

    return img.resize((1024, 1024), Image.LANCZOS)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    icon = draw()
    icon.save(os.path.join(ASSETS, "MailSync.png"))
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "MailSync-256.png"))  # Fenstersymbol
    icon.save(os.path.join(ASSETS, "MailSync.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "MailSync.iconset")
        os.mkdir(iconset)
        for s in (16, 32, 128, 256, 512):
            icon.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, "icon_%dx%d.png" % (s, s)))
            icon.resize((2 * s, 2 * s), Image.LANCZOS).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (s, s)))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ASSETS, "MailSync.icns")], check=True)


if __name__ == "__main__":
    main()
