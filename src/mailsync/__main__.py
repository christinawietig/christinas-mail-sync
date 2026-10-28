import json
import os
import sys


def selftest(out_path, host1, host2):
    """Ohne Oberflaeche pruefen, ob imapsync und der Schluesselbund im Paket
    funktionieren (fuer den automatischen Build)."""
    from mailsync import credentials
    from mailsync.sync import selftest
    rc, out = selftest(host1, host2)
    try:
        credentials.set_password("selftest.invalid", "selftest", "x")
        ok = credentials.get_password("selftest.invalid", "selftest") == "x"
        credentials.delete_password("selftest.invalid", "selftest")
        out += "\nSchluesselbund: %s\n" % ("OK" if ok else "falscher Wert")
    except Exception as e:
        ok = False
        out += "\nSchluesselbund: %r\n" % e
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    sys.exit(rc if ok else 1)


def headless_sync(out_path):
    """Ein Sync ohne Oberflaeche fuer den automatischen Test: Einstellungen aus
    settings.json, Passwoerter aus MAILSYNC_PASSWORD1/2. Ergebnis als JSON."""
    import threading
    from dataclasses import asdict
    from mailsync import config
    from mailsync.sync import Sync
    events, finished = [], threading.Event()

    def on_event(kind, **data):
        if kind == "done":
            events.append({"kind": kind, **asdict(data["result"])})
            finished.set()
        elif kind == "error":
            events.append({"kind": kind, "text": data["text"]})
            finished.set()

    Sync(config.load_settings(), os.environ["MAILSYNC_PASSWORD1"], os.environ["MAILSYNC_PASSWORD2"],
         on_event).start()
    finished.wait()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(events[0], f)
    sys.exit(0 if events[0]["kind"] == "done" else 1)


def run():
    # Die Windows-App hat keine Konsole, daher gehen die Ausgaben in eine Datei
    if len(sys.argv) == 5 and sys.argv[1] == "--selftest":
        selftest(*sys.argv[2:])
    if len(sys.argv) == 3 and sys.argv[1] == "--sync-headless":
        headless_sync(sys.argv[2])
    from mailsync.gui import main
    main()


run()
