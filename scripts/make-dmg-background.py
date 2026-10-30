"""Zeichnet den Hintergrund des DMG-Fensters: Pfeil von der App zum Ordner Programme.

Aufruf (macOS, wegen der Systemschrift):  python scripts/make-dmg-background.py
Ergebnis: assets/dmg-background.png und assets/dmg-background@2x.png (Retina).
Die Positionen passen zu installer/dmg-settings.py.
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 600, 380
APP_X, TARGET_X, ICON_Y = 160, 440, 170
ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")
FONT = "/System/Library/Fonts/SFNS.ttf"


def draw(scale):
    s = scale
    img = Image.new("RGB", (W * s, H * s))
    d = ImageDraw.Draw(img)
    for y in range(H * s):  # sanfter Verlauf von Weiss nach Hellblau
        t = y / (H * s)
        d.line([(0, y), (W * s, y)], fill=(int(252 - 14 * t), int(253 - 9 * t), 255))

    # Pfeil zwischen den Symbolen
    blue = (37, 99, 235)
    x0, x1, y = (APP_X + 78) * s, (TARGET_X - 78) * s, ICON_Y * s
    d.line([(x0, y), (x1 - 14 * s, y)], fill=blue, width=6 * s)
    d.polygon([(x1, y), (x1 - 22 * s, y - 14 * s), (x1 - 22 * s, y + 14 * s)], fill=blue)

    font = ImageFont.truetype(FONT, 17 * s)
    text = "Zum Installieren in den Ordner „Programme“ ziehen"
    w = d.textlength(text, font=font)
    d.text(((W * s - w) / 2, 300 * s), text, font=font, fill=(60, 64, 72))
    return img


if __name__ == "__main__":
    draw(1).save(os.path.join(ASSETS, "dmg-background.png"), optimize=True)
    draw(2).save(os.path.join(ASSETS, "dmg-background@2x.png"), optimize=True)
    print("gespeichert: assets/dmg-background.png, assets/dmg-background@2x.png")
