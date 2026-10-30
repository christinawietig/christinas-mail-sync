# Christinas Mail-Sync – Entwicklung

Die README ist für Anwenderinnen und Anwender (nicht technisch, Deutsch). Technisches gehört hierher.

## Regeln

- **Niemals Zugangsdaten oder echte Daten committen:** keine Passwörter, Tokens, echten Server-
  oder Schulnamen, Mailadressen, `settings.json`, `uebertragen.txt` oder Logs. Beispiele nur mit
  `example.org`. `.gitignore` und ein lokaler pre-commit-Hook (`.git/hooks/pre-commit`, nicht versioniert)
  blockieren die bekannten Fälle.
- Commits mit der GitHub-noreply-Adresse von christinawietig.
- Oberfläche und Meldungen auf Deutsch, verständlich für Nicht-Techniker. Code-Kommentare ohne Umlaute.
- Releases (`git tag v1.x.y && git push --tags`) nur nach ausdrücklichem Okay.

## Aufbau

- `src/mailsync/plan.py`: Liest beide Postfächer (nur lesend), Schlüssel = Message-ID (sonst Hash aus
  Date/From/Subject; imapsyncs Ersatz-ID `<UID@imapsync>` zählt nicht). Bekannt = Statusdatei ∪ Ziel.
- `src/mailsync/sync.py`: imapsync pro Ordner mit `--search1 "UID …"`, `--addheader`, Zertifikatsprüfung
  über `--sslargs SSL_verify_mode=1` + certifi. Passwörter nur über temporäre Passfiles.
- `src/mailsync/setupcode.py`: Einrichtungscode `MS1-…` (Crockford-Base32, Deflate, CRC-32).
  Enthält Server, Ports, Benutzernamen, ausgeschlossene Ordner – **nie Passwörter**.
- `src/mailsync/gui.py`: tkinter. Einstellungen mit live mitlaufendem Code (Kopieren/Einfügen), Sync-Fortschritt.
- `src/mailsync/credentials.py`: `keyring` (macOS-Schlüsselbund, Windows-Anmeldeinformationsverwaltung).
- Versteckte Aufrufe für Tests: `--selftest DATEI HOST1 HOST2`, `--sync-headless DATEI`
  (Passwörter aus `MAILSYNC_PASSWORD1/2`). `MAILSYNC_DATA_DIR` und `MAILSYNC_CA_FILE` ersetzen Datenordner und CA.

- Abgleich: Bei jedem Sync werden beide Postfächer neu gelesen. Bekannt = Ziel ∪ `uebertragen.txt`.
  Fehlt die Datei, entstehen keine Duplikate; nur im Ziel gelöschte Mails kämen wieder.

## Bauen und testen

Voraussetzungen: Python 3.13 mit Tk. Für den Mac-Build zusätzlich die Xcode Command Line Tools und Homebrew mit `openssl@3`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/build-imapsync-macos.sh                 # imapsync -> vendor/imapsync (eigenständig, arm64)
.venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python -m mailsync       # App aus dem Quelltext
.venv/bin/pyinstaller --noconfirm mailsync.spec   # -> dist/
# Ende-zu-Ende-Test mit GreenMail (braucht Java und "cryptography"):
PYTHONPATH=src .venv/bin/python tests/e2e.py -- "dist/Christinas Mail-Sync.app/Contents/MacOS/Christinas Mail-Sync"
```

- macOS: imapsync liegt als Skript mit Perl-Modulen in `Contents/Resources/imapsync/` und läuft mit
  `/usr/bin/perl` (5.34). Keine gepackte Einzeldatei (PAR::Packer), weil Apple die nicht signieren kann.
  `mailsync.spec` signiert jede Mach-O-Datei einzeln, dann die App: mit `MACOS_SIGN_IDENTITY`
  (Developer ID, Hardened Runtime, Zeitstempel), sonst ad hoc.
- `scripts/package-macos.sh`: App notarisieren und heften, DMG bauen (`dmgbuild`, `installer/dmg-settings.py`,
  Hintergrund aus `scripts/make-dmg-background.py`), DMG signieren, notarisieren, heften.
- Windows: onedir-Build, daraus `installer/windows.iss` (Inno Setup) die `Christinas-Mail-Sync-Setup.exe`;
  installiert ohne Adminrechte nach `%LOCALAPPDATA%\Programs`.
- Windows: offizielles `imapsync.exe` (`scripts/fetch-imapsync-windows.ps1`, Prüfsumme in `scripts/imapsync-version.sh`).

## GitHub Actions

- `build.yml`: Baut Windows (Setup wird still installiert, getestet und deinstalliert) und macOS (DMG),
  Unit-Tests, Selbsttest (imapsync + Schlüsselbund) und Ende-zu-Ende-Test der fertigen App mit GreenMail.
  Bei Tags `v*` entsteht ein Release.
- Signieren/Notarisieren: Secrets in der GitHub-Umgebung `release` (nur Tags `v*` und `main`):
  `MACOS_CERT_P12` (base64), `MACOS_CERT_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID`.
  Developer ID von Johannes Hoppe. Der macOS-Job nutzt die Umgebung nur bei Tags und beim Start von Hand.
- `screenshots.yml` (manuell): `scripts/screenshots.py` mit Beispieldaten. Artefakte herunterladen
  (`gh run download`) und mit `scripts/combine-screenshots.py ORDNER docs/screenshots` paarweise
  zusammensetzen (macOS links, Windows rechts, gleich hoch, ein Bild – sonst bricht GitHub sie um).

## Offene Punkte

- Die Windows-Setup.exe ist nicht signiert: SmartScreen warnt beim ersten Start.
- macOS-Mindestversion 12.0 ist ungeprüft; vorausgesetzt wird `/usr/bin/perl` 5.34.
