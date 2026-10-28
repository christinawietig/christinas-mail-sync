# Christinas Mail-Sync

Kopiert Mails von einem alten IMAP-Postfach in ein neues, zum Beispiel beim Wechsel des Mailanbieters.
Für Windows und Mac, ohne Installation von Zusatzprogrammen.

- **Jede Mail wird genau einmal übertragen.** Man kann so oft synchronisieren, wie man will.
- **Nur eine Richtung:** Im alten Postfach wird nichts verändert, im neuen wird nichts gelöscht.
- **Ordner bleiben erhalten**, ebenso Datum und Gelesen-Markierung.

<p align="center">
  <img src="docs/screenshots/macos-2-sync.png" height="150" alt="Sync läuft unter macOS">
  <img src="docs/screenshots/windows-3-fertig.png" height="150" alt="Sync fertig unter Windows">
</p>
<p align="center"><em>Ein Doppelklick genügt – links macOS während des Syncs, rechts Windows danach</em></p>

## Herunterladen

Unter [Releases](https://github.com/christinawietig/christinas-mail-sync/releases/latest):

- **Windows:** `Christinas-Mail-Sync-Windows.exe`
- **Mac (mit Apple-Chip, ab 2020):** `Christinas-Mail-Sync-macOS.zip`

## Erster Start

Die App ist nicht bei Apple oder Microsoft registriert. Deshalb warnt der Computer beim ersten Start einmalig.

**Mac**

1. Die ZIP-Datei doppelklicken und **Christinas Mail-Sync** in den Ordner **Programme** ziehen.
2. Die App doppelklicken. Es erscheint eine Warnung. Auf **Fertig** klicken.
3. **Systemeinstellungen → Datenschutz & Sicherheit** öffnen, ganz nach unten scrollen und bei
   „Christinas Mail-Sync“ auf **Dennoch öffnen** klicken.

**Windows**

1. Die Datei doppelklicken. Falls „Der Computer wurde durch Windows geschützt“ erscheint:
   auf **Weitere Informationen** und dann auf **Trotzdem ausführen** klicken.

**Danach** öffnet die App einmalig die Einstellungen:

1. Hat man einen **Einrichtungscode** bekommen (beginnt mit `MS1-`): ihn kopieren und in der App auf
   **Einfügen** klicken. Server und Benutzernamen sind dann eingetragen.
   Ohne Code füllt man die Felder von Hand aus.
2. Die beiden **Passwörter** eingeben.
3. Auf **Prüfen und speichern** klicken.

<p align="center">
  <img src="docs/screenshots/macos-1-einstellungen.png" height="420" alt="Einstellungen unter macOS">
  <img src="docs/screenshots/windows-1-einstellungen.png" height="420" alt="Einstellungen unter Windows">
</p>
<p align="center"><em>Einstellungen mit eingefügtem Code – links macOS, rechts Windows</em></p>

Ab dann genügt ein Doppelklick: Die App synchronisiert sofort und zeigt am Ende, wie viele Mails übertragen wurden.

## Einrichtungscode weitergeben

Unten in den Einstellungen steht immer der Einrichtungscode zu den Feldern darüber.
Er ändert sich bei jeder Eingabe sofort mit. **Kopieren** klicken und den Code zum Beispiel per Mail verschicken.

- Der Code enthält Server, Benutzernamen und ausgeschlossene Ordner, **aber nie die Passwörter.**
- **Kolleginnen und Kollegen einrichten:** In den Einstellungen deren Adresse und Benutzernamen eintragen,
  **Kopieren** klicken und dann **Abbrechen**. Die eigenen Einstellungen bleiben unverändert.
  Die Kollegin fügt den Code ein und gibt nur noch ihre Passwörter ein.
- Leerzeichen, Zeilenumbrüche und Groß-/Kleinschreibung sind egal. Eine Prüfsumme erkennt,
  wenn der Code unvollständig kopiert oder vertippt wurde.

## Tipps

- Neue Mails am besten zuerst im **alten** Postfach in Ordner einsortieren und dann synchronisieren.
  Sie landen dann gleich im passenden Ordner im neuen Postfach.
- Was nach der Übertragung verschoben oder gelöscht wird, gilt nur in dem Postfach, in dem man es tut.
  Eine im neuen Postfach gelöschte Mail kommt nicht wieder.
- Ausgeschlossene Ordner (z. B. der Papierkorb) werden nicht übertragen. Sie kommen mit dem Einrichtungscode.
- Ein Abbruch mit **Stopp** schadet nicht. Beim nächsten Start geht es einfach weiter.

## Wo die Daten liegen

Alles bleibt auf dem eigenen Computer:

| Was | Wo |
|---|---|
| Passwörter | Schlüsselbund (Mac) bzw. Anmeldeinformationsverwaltung (Windows) |
| Server, Benutzernamen, Liste der übertragenen Mails, Protokolle | Mac: `~/Library/Application Support/Christinas Mail-Sync/`<br>Windows: `%APPDATA%\Christinas Mail-Sync\` |

Die Datei `uebertragen.txt` in diesem Ordner merkt sich, welche Mails schon übertragen wurden.
Wer sie löscht, bekommt Mails, die im neuen Postfach gelöscht wurden, beim nächsten Mal erneut.

## So funktioniert es

1. Die App liest die Message-IDs aller Mails in beiden Postfächern, nur lesend, und ermittelt die Mails,
   die noch nie übertragen wurden (`src/mailsync/plan.py`).
2. [imapsync](https://imapsync.lamiral.info/) kopiert Ordner für Ordner genau diese Mails (`src/mailsync/sync.py`).
3. Alles, was jetzt im neuen Postfach liegt, wird in `uebertragen.txt` vermerkt.

Die Verbindungen sind verschlüsselt, und die Zertifikate der Server werden geprüft.

## Entwicklung

Voraussetzungen: Python 3.13 mit Tk. Für den Mac-Build zusätzlich die Xcode Command Line Tools und Homebrew mit `openssl@3`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/build-imapsync-macos.sh          # imapsync -> vendor/imapsync
.venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python tests/e2e.py -- .venv/bin/python -m mailsync   # braucht Java und "cryptography"
PYTHONPATH=src .venv/bin/python -m mailsync  # App aus dem Quelltext starten
.venv/bin/pyinstaller --noconfirm mailsync.spec   # -> dist/
```

Die Windows-Version wird automatisch auf GitHub gebaut (`.github/workflows/build.yml`).
Dabei synchronisiert die fertige App für Windows und Mac jedes Mal zwei Postfächer auf einem
Test-Mailserver ([GreenMail](https://greenmail-mail-test.github.io/greenmail/), `tests/e2e.py`):
genau einmal übertragen, Ordner, Datum und Gelesen erhalten, Papierkorb ausgelassen,
im Ziel gelöschte Mails kommen nicht wieder.
Die Screenshots erstellt der Workflow „Screenshots“ (`scripts/screenshots.py`, mit Beispieldaten).
Ein neues Release entsteht mit `git tag v1.x.y && git push --tags`.

## Lizenz

[MIT](LICENSE). Die mitgelieferte Software und ihre Lizenzen stehen in [THIRD_PARTY.md](THIRD_PARTY.md).
