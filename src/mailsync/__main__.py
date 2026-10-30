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
        # Kommt die App an die Release-Seite (Zertifikate im Paket)?
        from mailsync import update
        out += "\nUpdate-Pruefung: neueste Version %s\n" % update.latest_version()
    except Exception as e:
        rc = 1
        out += "\nUpdate-Pruefung: %r\n" % e
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
    events, finished, seen = [], threading.Event(), {"preview": None, "planned": None}

    def on_event(kind, **data):
        if kind in ("preview", "planned"):
            seen[kind] = data["total"]
            if kind == "preview":
                sync.proceed()  # Vorschau beim ersten Lauf: wie "Übertragen" klicken
        elif kind == "done":
            events.append({"kind": kind, **asdict(data["result"])})
            finished.set()
        elif kind == "error":
            events.append({"kind": kind, "text": data["text"]})
            finished.set()

    sync = Sync(config.load_settings(), os.environ["MAILSYNC_PASSWORD1"], os.environ["MAILSYNC_PASSWORD2"],
                on_event)
    sync.start()
    finished.wait()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({**events[0], **seen}, f)
    sys.exit(0 if events[0]["kind"] == "done" else 1)


def check_setup(out_path):
    """Fuer den Update-Test: Findet die App Einstellungen und Passwoerter? Schreibt
    die Einstellungen und je Postfach nur, OB ein Passwort da ist - nie das Passwort."""
    from dataclasses import asdict
    from mailsync import __version__, config, credentials
    s = config.load_settings()
    result = {
        "version": __version__,
        "settings": asdict(s),
        "source_password": credentials.get_password(s.source_host, s.source_user) is not None,
        "target_password": credentials.get_password(s.target_host, s.target_user) is not None,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    sys.exit(0)


def run():
    # Die Windows-App hat keine Konsole, daher gehen die Ausgaben in eine Datei
    if len(sys.argv) == 5 and sys.argv[1] == "--selftest":
        selftest(*sys.argv[2:])
    if len(sys.argv) == 3 and sys.argv[1] == "--sync-headless":
        headless_sync(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--check-setup":
        check_setup(sys.argv[2])
    from mailsync.gui import main
    main()


run()
