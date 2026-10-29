"""Setzt die Screenshots fuer die README paarweise zusammen: macOS links, Windows
rechts, gleich hoch, in einem Bild (sonst bricht GitHub sie untereinander um).

Aufruf:  python scripts/combine-screenshots.py ORDNER-MIT-SCREENSHOTS docs/screenshots
ORDNER enthaelt die Bilder aus dem Workflow "Screenshots" (beliebig verschachtelt).
"""
import glob
import os
import sys

from PIL import Image, ImageFilter

PAIRS = {
    "sync": ("macos-2-sync.png", "windows-3-fertig.png"),
    "einstellungen": ("macos-1-einstellungen.png", "windows-1-einstellungen.png"),
}
GAP = 40
SHADOW = 14  # Rand fuer den Schatten, gleich fuer beide Fenster
BORDER = (112, 112, 112, 255)


def find(src, name):
    return glob.glob(os.path.join(src, "**", name), recursive=True)[0]


def clean_windows_border(im):
    """Der 1-Pixel-Rand der Windows-Aufnahme enthaelt Reste des Hintergrunds."""
    im = im.convert("RGBA")
    w, h = im.size
    for x in range(w):
        im.putpixel((x, 0), BORDER)
        im.putpixel((x, h - 1), BORDER)
    for y in range(h):
        im.putpixel((0, y), BORDER)
        im.putpixel((w - 1, y), BORDER)
    return im


def with_shadow(im):
    """Dezenter Schatten, damit helle Fenster auf hellem Grund eine Kante haben."""
    w, h = im.size
    out = Image.new("RGBA", (w + 2 * SHADOW, h + 2 * SHADOW), (0, 0, 0, 0))
    alpha = Image.new("L", out.size, 0)
    alpha.paste(im.getchannel("A").point(lambda a: 70 if a else 0), (SHADOW, SHADOW + 3))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 255))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(6)))
    out.alpha_composite(shadow)
    out.alpha_composite(im, (SHADOW, SHADOW))
    return out


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for name, (mac_name, win_name) in PAIRS.items():
        mac = Image.open(find(src, mac_name)).convert("RGBA")
        win = clean_windows_border(Image.open(find(src, win_name)))
        h = mac.height
        win = win.resize((round(win.width * h / win.height), h), Image.LANCZOS)
        mac, win = with_shadow(mac), with_shadow(win)
        h = mac.height
        canvas = Image.new("RGBA", (mac.width + GAP + win.width, h), (0, 0, 0, 0))
        canvas.paste(mac, (0, 0), mac)
        canvas.paste(win, (mac.width + GAP, 0), win)
        path = os.path.join(out, name + ".png")
        canvas.save(path, optimize=True)
        print(path, canvas.size)


if __name__ == "__main__":
    main()
