"""Erstellt die Screenshots fuer die README, mit Beispieldaten (example.org).

Es werden keine echten Einstellungen gelesen, keine Passwoerter abgefragt und
keine Server kontaktiert: Der Sync ist hier nur nachgestellt.

Aufruf:  PYTHONPATH=src python scripts/screenshots.py docs/screenshots
macOS braucht dafuer die Berechtigung "Bildschirmaufnahme" fuer das Terminal.
Auf GitHub erstellt der Workflow "Screenshots" die Bilder fuer beide Systeme.
"""
import os
import subprocess
import sys

from mailsync import config, credentials, gui, setupcode
from mailsync.sync import Result

DEMO = config.Settings(
    source_host="imap.alte-schule.example.org", source_user="erika.muster@alte-schule.example.org",
    target_host="imap.neue-schule.example.org", target_user="erika.muster",
    target_user_rule="localpart", exclude_folders=["INBOX.Trash"])
PLATFORM = "windows" if sys.platform == "win32" else "macos"


class FakeSync:
    log_path = ""

    def __init__(self, *args):
        pass

    def start(self):
        pass

    def stop(self):
        pass


def capture(win, path):
    win.update()
    if sys.platform == "darwin":
        import Quartz
        windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
        # Das Fenster dieses Prozesses mit passender Position und Breite
        x, w = win.winfo_rootx(), win.winfo_width()
        ids = [d["kCGWindowNumber"] for d in windows
               if d["kCGWindowOwnerPID"] == os.getpid() and d.get("kCGWindowIsOnscreen")
               and abs(d["kCGWindowBounds"]["X"] - x) <= 2 and abs(d["kCGWindowBounds"]["Width"] - w) <= 2]
        subprocess.run(["screencapture", "-x", "-l", str(ids[0]), path], check=True)
    else:
        import ctypes
        from ctypes import wintypes
        from PIL import ImageGrab
        hwnd = int(win.wm_frame(), 16)
        rect = wintypes.RECT()
        # Fensterrahmen ohne unsichtbaren Schattenrand (DWMWA_EXTENDED_FRAME_BOUNDS)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(path)
    print("gespeichert:", path)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots"
    os.makedirs(out, exist_ok=True)
    credentials.get_password = lambda host, user: None
    gui.Sync = FakeSync
    app = gui.App()
    root = app.root
    code = setupcode.from_settings(DEMO)
    steps = []

    def step(fn):
        steps.append(fn)
        return fn

    @step
    def setup():
        app.settings = config.Settings()
        app.show_setup()
        f = app.frame
        f.code_text.insert("1.0", code)
        f._check_code()
        f.source_user.set(DEMO.source_user)
        f._suggest_target(None)
        f.source_pw.set("x" * 12)
        f.target_pw.set("x" * 12)
        f.save_button.focus_set()
        return "1-einrichtung"

    @step
    def running():
        app.settings = DEMO
        app.show_sync("", "")
        f = app.frame
        f.on_event("folder", {"i": 4, "n": 11, "name": "INBOX.Klasse 7b"})
        for _ in range(23):
            f.on_event("copied", {})
        f.bar.configure(value=3.6)
        return "2-sync"

    @step
    def done():
        app.frame.on_event("done", {"result": Result(transferred=37)})
        return "3-fertig"

    @step
    def share():
        app.dialog = gui.ShareDialog(app)
        app.dialog._copy(code)
        return "4-code-teilen"

    def run(i=0):
        if i > 0:
            capture(run.window, os.path.join(out, "%s-%s.png" % (PLATFORM, run.name)))
        if i == len(steps):
            root.destroy()
            return
        run.name = steps[i]()
        run.window = getattr(app, "dialog", None) or root
        run.window.lift()
        run.window.focus_force()
        root.after(1200, lambda: run(i + 1))

    root.after(300, run)
    root.mainloop()


if __name__ == "__main__":
    main()
