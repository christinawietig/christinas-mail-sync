# Christinas Mail-Sync

Kopiert Mails vom alten Postfach ins neue. Jede Mail genau einmal, so oft man will.

## ⬇️ [Download für Mac](https://github.com/christinawietig/christinas-mail-sync/releases/latest/download/Christinas-Mail-Sync.dmg)

## ⬇️ [Download für Windows](https://github.com/christinawietig/christinas-mail-sync/releases/latest/download/Christinas-Mail-Sync-Setup.exe)

<p align="center">
  <img src="docs/screenshots/sync.png" alt="Sync unter macOS und Windows">
</p>

## Installieren

**Mac:** Die heruntergeladene Datei öffnen und **Christinas Mail-Sync** auf den Ordner **Programme** ziehen.
Dann die App aus „Programme“ starten.

**Windows:** Die heruntergeladene Datei öffnen. Falls „Der Computer wurde durch Windows geschützt“
erscheint: **Weitere Informationen** → **Trotzdem ausführen**. Dann den Schritten folgen.

## Einrichten

Beim ersten Start öffnen sich die Einstellungen:

1. **Einrichtungscode** von der Kollegin kopieren und in der App auf **Einfügen** klicken.
2. Die beiden **Passwörter** eingeben.
3. **Prüfen und speichern** klicken.

Ab dann genügt ein Doppelklick auf die App.

<p align="center">
  <img src="docs/screenshots/einstellungen.png" alt="Einstellungen unter macOS und Windows">
</p>

## Code für eine Kollegin erstellen

1. In der App auf **Einstellungen** klicken.
2. Ihre E-Mail-Adresse und ihren Benutzernamen eintragen.
3. **Kopieren** klicken und den Code an sie schicken.
4. **Abbrechen** klicken – nicht speichern. Die eigenen Einstellungen bleiben so, wie sie waren.

Der Code enthält nie Passwörter.

## Gut zu wissen

- Im alten Postfach wird nichts verändert, im neuen wird nichts gelöscht.
- Ordner, Datum und Gelesen-Markierung bleiben erhalten.
- Eine im neuen Postfach gelöschte Mail kommt nicht wieder.
- **Stopp** schadet nicht. Beim nächsten Start geht es weiter.
- Passwörter liegen im Schlüsselbund (Mac) bzw. in der Anmeldeinformationsverwaltung (Windows),
  alles andere im Ordner `Christinas Mail-Sync` unter `~/Library/Application Support` (Mac)
  bzw. `%APPDATA%` (Windows). Die Verbindungen sind verschlüsselt.

---

[MIT-Lizenz](LICENSE) · [Mitgelieferte Software](THIRD_PARTY.md) · [Entwicklung](CLAUDE.md) ·
Kopiert wird mit [imapsync](https://imapsync.lamiral.info/).
