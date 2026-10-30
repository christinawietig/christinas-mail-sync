"""Setzt die Screenshots fuer die README paarweise zusammen: macOS links, Windows
rechts, gleich hoch, in einem Bild (sonst bricht GitHub sie untereinander um).

Die macOS-Aufnahme bringt den echten Fensterschatten mit. Die Windows-Aufnahme ist
genau das Fenster ohne Schatten; sie bekommt einen nachgebauten Schatten mit
denselben Raendern wie das Mac-Bild, damit beide Fenster gleich wirken.

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
    "vorschau": ("macos-5-vorschau.png", "windows-5-vorschau.png"),
}
GAP = 24
WIN_BORDER = (150, 150, 150, 255)


def find(src, name):
    return glob.glob(os.path.join(src, "**", name), recursive=True)[0]


def window_box(im):
    """Fenster innerhalb der Mac-Aufnahme: der deckende Teil ohne Schatten."""
    return im.getchannel("A").point(lambda a: 255 if a > 250 else 0).getbbox()


def clean_windows_border(im):
    """Der 1-Pixel-Rand der Windows-Aufnahme enthaelt Reste des Hintergrunds."""
    im = im.convert("RGBA")
    w, h = im.size
    for x in range(w):
        im.putpixel((x, 0), WIN_BORDER)
        im.putpixel((x, h - 1), WIN_BORDER)
    for y in range(h):
        im.putpixel((0, y), WIN_BORDER)
        im.putpixel((w - 1, y), WIN_BORDER)
    return im


def with_shadow(im, margins):
    """Weicher Schatten wie bei macOS: etwas nach unten versetzt, Raender = margins."""
    left, top, right, bottom = margins
    w, h = im.size
    out = Image.new("RGBA", (left + w + right, top + h + bottom), (0, 0, 0, 0))
    blur = max(min(left, right, bottom) / 2.5, 2)
    alpha = Image.new("L", out.size, 0)
    alpha.paste(110, (left, top + round(blur / 2), left + w, top + h + round(blur / 2)))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 255))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(shadow)
    out.alpha_composite(im, (left, top))
    return out


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for name, (mac_name, win_name) in PAIRS.items():
        mac = Image.open(find(src, mac_name)).convert("RGBA")
        x0, y0, x1, y1 = window_box(mac)
        margins = (x0, y0, mac.width - x1, mac.height - y1)
        win = clean_windows_border(Image.open(find(src, win_name)))
        h = y1 - y0  # Fenster gleich hoch, Schatten zaehlt nicht mit
        win = win.resize((round(win.width * h / win.height), h), Image.LANCZOS)
        win = with_shadow(win, margins)
        canvas = Image.new("RGBA", (mac.width + GAP + win.width, mac.height), (0, 0, 0, 0))
        canvas.alpha_composite(mac, (0, 0))
        canvas.alpha_composite(win, (mac.width + GAP, 0))
        path = os.path.join(out, name + ".png")
        canvas.save(path, optimize=True)
        print(path, canvas.size)


if __name__ == "__main__":
    main()
