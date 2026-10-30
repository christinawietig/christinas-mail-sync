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
- `src/mailsync/gui.py`: tkinter. Einstellungen mit live mitlaufendem Code (Kopieren/Einfügen), Sync-Fortschritt
  nach Mails mit Restzeit, nach Fehlern „Protokoll kopieren“ (`sync.support_text`: Passwörter maskiert, gekürzt).
- Vorschau: Beim ersten Lauf in ein Zielpostfach meldet `Sync` `preview` und wartet auf `proceed()`/`stop()`.
  Bestätigt wird pro Ziel in `bestaetigt.txt` (Datenordner); `--sync-headless` bestätigt selbst.
- `src/mailsync/update.py`: Update-Hinweis. Liest nur die Weiterleitung von `/releases/latest` auf
  `/releases/tag/vX.Y.Z` (keine API, kein Rate-Limit, keine Daten). Offline passiert nichts.
- `src/mailsync/credentials.py`: `keyring` (macOS-Schlüsselbund, Windows-Anmeldeinformationsverwaltung).
- Versteckte Aufrufe für Tests: `--selftest DATEI HOST1 HOST2` (prüft auch die Update-Abfrage), `--sync-headless DATEI`
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
- `scripts/package-macos.sh dmg|submit|finish|history`: `dmg` baut unsigniert nur die DMG (`dmgbuild`,
  `installer/dmg-settings.py`, Hintergrund aus `scripts/make-dmg-background.py`). `submit` baut die DMG aus der
  signierten App, signiert sie und reicht sie bei Apple ein, ohne zu warten (Apple prüft die App darin mit);
  Ergebnis in `dist/signed/`. `finish` fragt Apple; bei „Accepted“ Ticket an die DMG heften und wie Gatekeeper
  prüfen. Die erste Notarisierung eines neuen Accounts kann Tage dauern.
- `scripts/macos-signing.sh setup|notary-key|cleanup`: temporärer Schlüsselbund mit Zertifikat bzw. nur `.p8`.
- imapsync, cpanm und alle Perl-Module haben feste Versionen (`scripts/imapsync-version.sh`,
  `scripts/build-imapsync-macos.sh`); imapsync und cpanm mit Prüfsumme.
- Windows: onedir-Build, daraus `installer/windows.iss` (Inno Setup) die `Christinas-Mail-Sync-Setup.exe`;
  installiert ohne Adminrechte nach `%LOCALAPPDATA%\Programs`.
- Windows: offizielles `imapsync.exe` (`scripts/fetch-imapsync-windows.ps1`, Prüfsumme in `scripts/imapsync-version.sh`).

## GitHub Actions

- `build.yml`: Baut Windows (Update-Test: die veröffentlichte Version wird installiert und eingerichtet, die neue
  drüberinstalliert, `--check-setup` prüft Einstellungen, Passwörter und den Apps-Eintrag; danach Selbsttest,
  Ende-zu-Ende-Test und Deinstallation) und macOS (DMG),
  Unit-Tests, Selbsttest (imapsync + Schlüsselbund) und Ende-zu-Ende-Test der fertigen App mit GreenMail.
  Bei Tags `v*` entsteht ein Release mit der Setup.exe. Signierte macOS-Builds reichen die DMG bei Apple
  ein und sichern sie als Artifact `macos-signed` (90 Tage) – die eingereichte DMG geht so nie verloren.
  Der Job `lint` prüft Workflows (actionlint) und Shell-Skripte (shellcheck).
- `mac-release.yml`: nach jedem Build, alle 30 Minuten und von Hand. Sucht das neueste Release ohne DMG
  (oder den angegebenen Build-Lauf), holt `macos-signed` und führt `package-macos.sh finish` aus (Skripte
  aus demselben Commit). Prüft Apple noch, endet der Lauf grün und der nächste fragt wieder. Fertige DMG →
  ans Release. Lehnt Apple ab, wird das Artifact gelöscht (sonst würde alle 30 Minuten neu gefragt).
- `notary-status.yml` (manuell): zeigt die Notarisierungs-Einreichungen bei Apple mit Status.
- Signieren/Notarisieren: Secrets in der GitHub-Umgebung `release` (nur Tags `v*` und `main`):
  `MACOS_CERT_P12` (base64), `MACOS_CERT_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID`.
  Developer ID von Johannes Hoppe. Der macOS-Job nutzt die Umgebung nur bei Tags und beim Start von Hand.
- `screenshots.yml` (manuell): `scripts/screenshots.py` mit Beispieldaten. Artefakte herunterladen
  (`gh run download`) und mit `scripts/combine-screenshots.py ORDNER docs/screenshots` paarweise
  zusammensetzen (macOS links, Windows rechts, gleich hoch, ein Bild – sonst bricht GitHub sie um).
  macOS-Aufnahmen mit echtem Fensterschatten, Windows bekommt einen passenden nachgebauten.

## Release

Nur nach ausdrücklichem Okay von Christina.

1. **Version erhöhen:** `__version__` in `src/mailsync/__init__.py` (die einzige Stelle; Info.plist, Setup.exe,
   App-exe und DMG-Name übernehmen sie beim Bauen). Commit „Version X.Y.Z“, auf `main` pushen.
2. **Build auf `main` abwarten, alles grün:** Unit-Tests, Selbsttest (inkl. Update-Abfrage), Windows-Update-Test
   (veröffentlichte Version → neue drüber), Ende-zu-Ende-Test auf beiden Systemen, `lint`.
   Weitere Pushes auf `main` brechen den laufenden Build ab – erst warten, dann taggen.
3. **Taggen:** `git tag vX.Y.Z <commit> && git push origin vX.Y.Z`. Der Build läuft für den Tag noch einmal komplett.
4. **Windows:** Der Job `release` legt das Release mit `Christinas-Mail-Sync-Setup.exe` an (ca. 10 Minuten).
5. **Mac:** Der Build reicht die signierte DMG bei Apple ein (Artifact `macos-signed`). „Mac-Release abschliessen“
   startet danach, wartet bis zu 30 Minuten und hängt die DMG nach der Freigabe ans Release. Dauert Apple länger,
   fragt der 30-Minuten-Takt nach – der fällt bei GitHub aber manchmal stundenlang aus, dann von Hand starten
   (`gh workflow run mac-release.yml`). Status bei Apple: `gh workflow run notary-status.yml`.
6. **Prüfen:** `gh release view vX.Y.Z` zeigt beide Dateien; beide README-Links liefern HTTP 200:
   `curl -sIL https://github.com/christinawietig/christinas-mail-sync/releases/latest/download/Christinas-Mail-Sync.dmg`
   (ebenso `…-Setup.exe`).
7. **Screenshots** nur bei sichtbaren Änderungen neu machen (`screenshots.yml`, siehe oben) – am besten vor dem Taggen.

- Die Dateinamen bleiben immer gleich, nur so zeigen die README-Links und der Update-Hinweis in der App
  (`/releases/latest/download/<Datei>`) auf die neueste Version. Die Version steht in den Dateien selbst.
- Sobald das Release „Latest“ ist, zeigen alle installierten Apps ab 1.0.2 beim Start den Update-Hinweis.
- Einen veröffentlichten Tag nie verschieben oder neu bauen: Die Dateien sind schon im Umlauf.
  Bei einem Fehler stattdessen eine neue Patch-Version (X.Y.Z+1).

## Offene Punkte

- Die Windows-Setup.exe ist nicht signiert: SmartScreen warnt beim ersten Start.
- macOS-Mindestversion 12.0 ist ungeprüft; vorausgesetzt wird `/usr/bin/perl` 5.34.
