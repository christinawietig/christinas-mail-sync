"""macOS: Die App beim ersten Start aus "Programme" einmalig ins Dock legen.

Nur einmal: Wer sie spaeter aus dem Dock entfernt, bekommt sie nicht ungefragt zurueck.
Alle Fehler werden geschluckt - das Dock ist Komfort, kein Muss.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from . import config

MARKER = "dock-eingetragen.txt"


def app_bundle():
    """Pfad der laufenden .app, oder None (Quelltext, Windows)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    # .../Christinas Mail-Sync.app/Contents/MacOS/Christinas Mail-Sync
    bundle = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))))
    return bundle if bundle.endswith(".app") else None


def installed(bundle):
    """Nur aus Programme heraus, nicht aus der DMG oder einer Downloads-Kopie."""
    return bundle.startswith(("/Applications/", os.path.expanduser("~/Applications/")))


def in_dock(dock_plist, bundle):
    """dock_plist: Inhalt von com.apple.dock als dict."""
    want = bundle.rstrip("/")
    for tile in dock_plist.get("persistent-apps", []):
        url = tile.get("tile-data", {}).get("file-data", {}).get("_CFURLString", "")
        path = unquote(url.replace("file://", "", 1)).rstrip("/")
        if path == want:
            return True
    return False


def _read_dock():
    out = subprocess.run(["defaults", "export", "com.apple.dock", "-"],
                         capture_output=True, check=True, timeout=10).stdout
    return plistlib.loads(out)


def add_once():
    try:
        bundle = app_bundle()
        if not bundle or not installed(bundle):
            return
        marker = os.path.join(config.data_dir(), MARKER)
        if os.path.exists(marker):
            return
        if not in_dock(_read_dock(), bundle):
            # Wie das Dock selbst: Datei-URL (_CFURLStringType 15)
            url = Path(bundle).as_uri() + "/"
            tile = ("<dict><key>tile-data</key><dict><key>file-data</key><dict>"
                    "<key>_CFURLString</key><string>%s</string>"
                    "<key>_CFURLStringType</key><integer>15</integer>"
                    "</dict></dict></dict>") % url.replace("&", "&amp;")
            subprocess.run(["defaults", "write", "com.apple.dock", "persistent-apps", "-array-add", tile],
                           capture_output=True, check=True, timeout=10)
            # Das Dock liest die Einstellung erst nach einem Neustart (dauert eine Sekunde)
            subprocess.run(["killall", "Dock"], capture_output=True, timeout=10)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(bundle + "\n")
    except Exception:
        pass
