# PyInstaller-Bauanleitung. Bauen mit:  pyinstaller mailsync.spec
# Vorher muss imapsync in vendor/ liegen (siehe scripts/).
# Ergebnis: dist/Christinas Mail-Sync.app (macOS) bzw. dist/Christinas Mail-Sync.exe (Windows)
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "src")
from mailsync import APP_NAME, __version__  # noqa: E402

win = sys.platform == "win32"
imapsync = "vendor/imapsync.exe" if win else "vendor/imapsync"

a = Analysis(
    ["src/mailsync/__main__.py"],
    pathex=["src"],
    # Auf dem Mac wird imapsync erst nach dem Bauen hineinkopiert (siehe unten)
    datas=[(imapsync, "imapsync")] if win else [],
    hiddenimports=["keyring.backends.macOS", "keyring.backends.Windows"],
)
pyz = PYZ(a.pure)

if win:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name=APP_NAME, console=False,
              icon="assets/MailSync.ico", upx=False)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, name=APP_NAME, console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)
    app = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        icon="assets/MailSync.icns",
        bundle_identifier="io.github.christinawietig.mail-sync",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
    # imapsync ist eine von pp gepackte Datei mit angehaengtem Archiv. PyInstaller
    # wuerde sie neu signieren und dabei zerstoeren. Deshalb hier unveraendert
    # als Ressource hineinkopieren und danach nur die App als Ganzes signieren.
    bundle = os.path.join(DISTPATH, APP_NAME + ".app")
    target = os.path.join(bundle, "Contents", "Resources", "imapsync")
    os.makedirs(target, exist_ok=True)
    shutil.copy2(imapsync, os.path.join(target, "imapsync"))
    subprocess.run(["codesign", "--force", "-s", "-", bundle], check=True)
