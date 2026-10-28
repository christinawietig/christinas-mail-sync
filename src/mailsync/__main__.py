import sys


def run():
    # "--selftest DATEI HOST1 HOST2": ohne Oberflaeche pruefen, ob imapsync im Paket
    # laeuft (fuer den automatischen Build; die Windows-App hat keine Konsole, daher Datei)
    if len(sys.argv) == 5 and sys.argv[1] == "--selftest":
        from mailsync.sync import selftest
        rc, out = selftest(sys.argv[3], sys.argv[4])
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(out)
        sys.exit(rc)
    from mailsync.gui import main
    main()


run()
