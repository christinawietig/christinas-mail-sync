# PyInstaller-Bauanleitung. Bauen mit:  pyinstaller mailsync.spec
# Vorher muss imapsync in vendor/ liegen (siehe scripts/).
# Ergebnis: dist/Christinas Mail-Sync.app (macOS) bzw. dist/Christinas Mail-Sync/ (Windows,
# daraus macht installer/windows.iss die setup.exe).
#
# macOS: MACOS_SIGN_IDENTITY="Developer ID Application: ..." signiert fuer die Notarisierung
# (mit Hardened Runtime und Zeitstempel). Ohne die Variable wird nur ad hoc signiert.
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "src")
from mailsync import APP_NAME, __version__  # noqa: E402

win = sys.platform == "win32"

a = Analysis(
    ["src/mailsync/__main__.py"],
    pathex=["src"],
    # Auf dem Mac wird imapsync erst nach dem Bauen hineinkopiert (siehe unten)
    datas=([("vendor/imapsync.exe", "imapsync")] if win else []) + [("assets/MailSync-256.png", "assets"), ("LICENSE", ".")],
    hiddenimports=["keyring.backends.macOS", "keyring.backends.Windows"],
)
pyz = PYZ(a.pure)

version_info = None
if win:
    # Versionsnummer in den Dateieigenschaften der exe (Eigenschaften -> Details)
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(([int(n) for n in __version__.split(".")] + [0, 0, 0, 0])[:4])
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040704B0", [
                  StringStruct("CompanyName", "Christina Wietig"),
                  StringStruct("FileDescription", APP_NAME),
                  StringStruct("FileVersion", __version__),
                  StringStruct("ProductName", APP_NAME),
                  StringStruct("ProductVersion", __version__),
                  StringStruct("LegalCopyright", "Christina Wietig, MIT-Lizenz"),
                  StringStruct("OriginalFilename", APP_NAME + ".exe")])]),
              VarFileInfo([VarStruct("Translation", [0x0407, 1200])])])

exe = EXE(pyz, a.scripts, exclude_binaries=True, name=APP_NAME, console=False,
          icon="assets/MailSync.ico" if win else None, version=version_info, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if not win:
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
    # imapsync (Skript und Perl-Module) als Ressource hineinkopieren
    bundle = os.path.join(DISTPATH, APP_NAME + ".app")
    target = os.path.join(bundle, "Contents", "Resources", "imapsync")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree("vendor/imapsync-macos", target)

    # Signieren von innen nach aussen: erst jede Datei mit Maschinencode, dann die App
    identity = os.environ.get("MACOS_SIGN_IDENTITY", "").strip() or "-"
    opts = ["--force", "-s", identity]
    if identity != "-":
        opts += ["--options", "runtime", "--timestamp"]

    def is_macho(path):
        with open(path, "rb") as f:
            return f.read(4) in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe")

    main_exe = os.path.join(bundle, "Contents", "MacOS", APP_NAME)
    nested = [os.path.join(d, f) for d, _, files in os.walk(bundle) for f in files]
    nested = [p for p in nested if not os.path.islink(p) and p != main_exe and is_macho(p)]
    for path in sorted(nested, key=len, reverse=True):
        subprocess.run(["codesign", *opts, path], check=True)
    subprocess.run(["codesign", *opts, bundle], check=True)
