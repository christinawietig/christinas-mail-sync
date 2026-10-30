# Christinas Mail-Sync

Kopiert Mails vom alten Postfach ins neue. Jede Mail genau einmal, so oft man will.

## ⬇️ [Download für Mac](https://github.com/christinawietig/christinas-mail-sync/releases/latest/download/Christinas-Mail-Sync.dmg)

## ⬇️ [Download für Windows](https://github.com/christinawietig/christinas-mail-sync/releases/latest/download/Christinas-Mail-Sync-Setup.exe)

<p align="center">
  <img src="docs/screenshots/sync.png" alt="Sync unter macOS und Windows">
</p>

## Installieren

**Mac:** Öffne die heruntergeladene Datei und ziehe **Christinas Mail-Sync** auf den Ordner **Programme**.
Starte die App dann aus „Programme“. Beim ersten Start legt sie sich selbst ins Dock.

**Windows:** Öffne die heruntergeladene Datei. Falls „Der Computer wurde durch Windows geschützt“
erscheint: **Weitere Informationen** → **Trotzdem ausführen**. Folge dann den Schritten.

## Einrichten

Beim ersten Start öffnen sich die Einstellungen:

1. Du hast von mir einen **Einrichtungscode** bekommen? Dann kopiere ihn und klicke in der App auf **Einfügen**.
   Ansonsten trage die Werte von Hand ein.
2. Gib die beiden **Passwörter** ein.
3. Klicke auf **Prüfen und speichern**.

Ab dann genügt ein Doppelklick auf die App.

<p align="center">
  <img src="docs/screenshots/einstellungen.png" alt="Einstellungen unter macOS und Windows">
</p>

## Code für einen Kollegen oder eine Kollegin erstellen

1. Klicke in der App auf **Einstellungen**.
2. Trage die E-Mail-Adresse und den Benutzernamen des Kollegen oder der Kollegin ein.
3. Klicke auf **Kopieren** und schicke den Code an ihn oder sie.
4. Klicke auf **Abbrechen** – nicht speichern. Deine eigenen Einstellungen bleiben so, wie sie waren.

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
