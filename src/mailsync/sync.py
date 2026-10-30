"""Ein Sync-Lauf: Plan erstellen, neue Mails mit imapsync kopieren, Status vermerken.

Jede Mail wird genau einmal uebertragen: plan.py merkt sich alle uebertragenen
Mails (Message-ID) in der Statusdatei, und imapsync bekommt pro Ordner nur die
UIDs der noch nie uebertragenen Mails. Sortieren/Loeschen in Quelle oder Ziel
fuehrt daher nie zu Duplikaten. Nur eine Richtung, es wird nichts geloescht.

Passwoerter gehen nur ueber temporaere Dateien (nur fuer den Nutzer lesbar) an
imapsync und werden am Ende des Laufs geloescht. Sie erscheinen nie in Logs.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

from . import config, plan

TRANSFERRED_RE = re.compile(r"^Messages transferred\s*:\s*(\d+)")


class AlreadyRunning(Exception):
    pass


@dataclass
class Result:
    transferred: int = 0
    failed_folders: int = 0
    stopped: bool = False


def ssl_args():
    """Serverzertifikate pruefen (imapsync tut das von sich aus nicht)."""
    ca = config.ca_file()
    return ["--sslargs1", "SSL_verify_mode=1", "--sslargs1", "SSL_ca_file=" + ca,
            "--sslargs2", "SSL_verify_mode=1", "--sslargs2", "SSL_ca_file=" + ca]


def selftest(host1, host2, port=config.DEFAULT_PORT):
    """Startet imapsync und baut ohne Anmeldung eine gepruefte Verbindung zu
    beiden Servern auf. Liefert (Rueckgabewert, Ausgabe). Fuer den Build-Test."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [*imapsync_cmd(), "--justconnect", "--nolog", "--noreleasecheck", "--tmpdir", tmp,
               "--host1", host1, "--port1", str(port), "--ssl1",
               "--host2", host2, "--port2", str(port), "--ssl2", *ssl_args()]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, cwd=tmp, timeout=300, env=_env(),
                           creationflags=flags, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0 and "Exiting after a justconnect" in p.stdout
    return (0 if ok else 1), p.stdout + p.stderr


def imapsync_cmd():
    """Befehl zum Starten von imapsync, als Liste.

    Windows: imapsync.exe. macOS: das imapsync-Skript mit seinen Modulen, gestartet
    mit dem Perl von macOS. Gesucht wird im App-Paket, im Quelltext in vendor/.
    """
    if getattr(sys, "frozen", False):
        bases = [os.path.join(sys._MEIPASS, "imapsync"),
                 # macOS-App: Contents/MacOS/<app> -> Contents/Resources/imapsync/
                 os.path.join(os.path.dirname(sys.executable), "..", "Resources", "imapsync")]
    else:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bases = [os.path.join(root, "vendor", "imapsync-macos"), os.path.join(root, "vendor")]
    for base in bases:
        if sys.platform == "win32":
            exe = os.path.join(base, "imapsync.exe")
            if os.path.isfile(exe):
                return [exe]
        else:
            script, lib = os.path.join(base, "imapsync"), os.path.join(base, "lib")
            if os.path.isfile(script) and os.path.isdir(lib):
                return ["/usr/bin/perl", "-I", lib, "-I", os.path.join(lib, "darwin-thread-multi-2level"), script]
    found = shutil.which("imapsync")
    if found:
        return [found]
    raise FileNotFoundError("imapsync wurde nicht gefunden.")


def _env():
    """Umgebung fuer imapsync: ohne fremde Perl-Einstellungen des Nutzers."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PERL")}


class Lock:
    """Nie zwei Laeufe gleichzeitig, sonst Duplikate. Das Betriebssystem gibt
    die Sperre frei, wenn der Prozess endet - auch nach einem Absturz."""

    def __init__(self, path):
        self.path = path
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise AlreadyRunning()
        return self

    def __exit__(self, *exc):
        self.fh.close()


class Sync:
    """Fuehrt einen Lauf in einem eigenen Thread aus.

    on_event(art, **daten) wird aus diesem Thread aufgerufen:
      status(text) | planned(total, folders) | preview(total, folders) | folder(i, n, name)
      | copied() | done(result) | error(text)
    folders = [(Ordnername, Anzahl neuer Mails), ...]

    Beim ersten Lauf in ein Zielpostfach wartet der Lauf nach "preview", bis proceed()
    (Uebertragen) oder stop() (Abbrechen) aufgerufen wird.
    """

    def __init__(self, settings, source_password, target_password, on_event):
        self.source = (settings.source_host, settings.source_port, settings.source_user, source_password)
        self.target = (settings.target_host, settings.target_port, settings.target_user, target_password)
        self.exclude = ["^%s$" % re.escape(f) for f in settings.exclude_folders]
        self.on_event = on_event
        self._stop = threading.Event()
        self._go = threading.Event()
        self._proc = None
        self._thread = None
        self.log_path = os.path.join(config.log_dir(), "letzter-lauf.txt")
        self._log = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout):
        """Kurz auf das Ende warten, damit die Passwortdateien geloescht werden."""
        if self._thread:
            self._thread.join(timeout)

    def proceed(self):
        """Nach der Vorschau: wirklich uebertragen."""
        self._go.set()

    def stop(self):
        self._stop.set()
        self._go.set()
        p = self._proc
        if p and p.poll() is None:
            if sys.platform == "win32":
                # imapsync.exe startet intern einen weiteren Prozess - ganzen Baum beenden
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                p.terminate()

    def _say(self, text):
        self._log.write(text + "\n")
        self._log.flush()

    def _run(self):
        try:
            # Erst sperren, dann das Protokoll leeren - sonst loescht ein zweiter
            # Start das Protokoll des laufenden Syncs
            with Lock(os.path.join(config.data_dir(), "sync.lock")):
                with open(self.log_path, "w", encoding="utf-8") as self._log:
                    self._say("%s  Start" % time.strftime("%Y-%m-%d %H:%M:%S"))
                    result = self._sync()
                    self._say("Uebertragen gesamt: %d" % result.transferred)
            self.on_event("done", result=result)
        except AlreadyRunning:
            self.on_event("error", text="Ein Sync läuft bereits. Bitte warten, bis er fertig ist.")
        except plan.Stopped:
            self.on_event("done", result=Result(stopped=True))
        except Exception as e:  # alles andere dem Nutzer melden statt still abzustuerzen
            self.on_event("error", text=describe_error(e))

    def _sync(self):
        exe = imapsync_cmd()
        state = config.state_file()
        self.on_event("status", text="Prüfe die Postfächer …")
        owner = plan.state_owner(self.target)
        first = not is_confirmed(owner)
        todo = plan.plan(state, self.source, self.target, self.exclude, self._stop.is_set)
        total = sum(n for _, _, n in todo)
        self._say("Neue Mails: %d in %d Ordner(n)" % (total, len(todo)))
        folders = [(f, n) for f, _, n in todo]
        if first and total:
            # Erster Lauf in dieses Ziel: erst zeigen, was kommt, dann auf Bestaetigung warten
            self._say("Erster Lauf: warte auf Bestaetigung")
            self.on_event("preview", total=total, folders=folders)
            self._go.wait()
            if self._stop.is_set():
                raise plan.Stopped()
            set_confirmed(owner)
            self._say("Bestaetigt")
        self.on_event("planned", total=total, folders=folders)

        result = Result()
        remove_stale_tempdirs()
        tmp = tempfile.mkdtemp(prefix=TMP_PREFIX)
        open(os.path.join(tmp, TMP_MARKER), "w").close()
        try:
            pass1 = self._passfile(tmp, "p1", self.source[3])
            pass2 = self._passfile(tmp, "p2", self.target[3])
            for i, (folder, uids, n) in enumerate(todo, 1):
                if self._stop.is_set():
                    result.stopped = True
                    break
                self.on_event("folder", i=i, n=len(todo), name=folder)
                self._say("Ordner %d/%d: %s (%d neu)" % (i, len(todo), folder, n))
                copied, rc = self._imapsync(exe, tmp, pass1, pass2, folder, uids)
                result.transferred += copied
                if rc != 0 and not self._stop.is_set():
                    result.failed_folders += 1
            if self._stop.is_set():
                result.stopped = True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # Was jetzt im Ziel liegt, als uebertragen vermerken (auch nach Abbruch).
        # Ohne Uebertragung gibt es nichts Neues: Das Ziel wurde eben erst gelesen.
        if result.transferred:
            self.on_event("status", text="Merke mir die übertragenen Mails …")
            _, noted = plan.update_state(state, self.target)
            self._say("Neu vermerkt: %d" % noted)
        return result

    @staticmethod
    def _passfile(tmp, name, password):
        path = os.path.join(tmp, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(password + "\n")
        return path

    def _imapsync(self, exe, tmp, pass1, pass2, folder, uids):
        # --automap        Spezialordner (Gesendet, Entwuerfe, Spam, Archiv) zuordnen
        # --subscribeall   Zielordner abonnieren, damit Mailprogramme sie anzeigen
        # --noresyncflags  Flags nur beim Kopieren setzen, spaeter nie ueberschreiben
        # --addheader      Mails ohne Message-ID auch kopieren (sonst uebergeht imapsync sie)
        # ssl_args()       Serverzertifikate pruefen
        # --folder/--search1  nur dieser Ordner, nur diese UIDs (aus plan.py)
        # Bewusst NICHT gesetzt: --delete1, --delete2, --delete2folders, --expunge1.
        host1, port1, user1, _ = self.source
        host2, port2, user2, _ = self.target
        cmd = [
            *exe,
            "--host1", host1, "--port1", str(port1), "--ssl1", "--user1", user1, "--passfile1", pass1,
            "--host2", host2, "--port2", str(port2), "--ssl2", "--user2", user2, "--passfile2", pass2,
            "--automap", "--subscribeall", "--noresyncflags", "--addheader", *ssl_args(),
            "--tmpdir", tmp, "--nolog", "--noreleasecheck",
            "--folder", folder, "--search1", "UID " + uids,
        ]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=tmp, env=_env(), creationflags=flags, text=True, encoding="utf-8", errors="replace")
        copied = 0
        for line in self._proc.stdout:
            self._log.write(line)
            if "copied to" in line:
                self.on_event("copied")
            m = TRANSFERRED_RE.match(line)
            if m:
                copied = int(m.group(1))
        rc = self._proc.wait()
        self._log.flush()
        return copied, rc


def _confirmed_path():
    return os.path.join(config.data_dir(), "bestaetigt.txt")


def is_confirmed(owner):
    """Wurde der erste Lauf in dieses Zielpostfach schon bestaetigt?"""
    try:
        with open(_confirmed_path(), encoding="utf-8") as f:
            return f.read().strip() == owner
    except OSError:
        return False


def set_confirmed(owner):
    with open(_confirmed_path(), "w", encoding="utf-8") as f:
        f.write(owner + "\n")


def format_count(n):
    """1243 -> '1.243'"""
    return "{:,}".format(n).replace(",", ".")


def format_remaining(seconds):
    """Restzeit grob und freundlich: 'unter einer Minute', 'ca. 5 Minuten', 'ca. 2 Std. 10 Min.'"""
    minutes = int(round(seconds / 60.0))
    if minutes < 1:
        return "unter einer Minute"
    if minutes == 1:
        return "ca. 1 Minute"
    if minutes < 60:
        return "ca. %d Minuten" % minutes
    if minutes >= 600:
        return "ca. %d Stunden" % round(minutes / 60.0)
    # Ueber einer Stunde auf 10 Minuten runden, das genuegt
    h, m = divmod(int(round(minutes / 10.0)) * 10, 60)
    return "ca. %d Std." % h if m == 0 else "ca. %d Std. %d Min." % (h, m)


def estimate_remaining(done, total, elapsed):
    """Sekunden bis zum Ende oder None, solange die Schaetzung zu unsicher ist."""
    if done < 10 or elapsed < 20 or total <= done:
        return None
    return elapsed / done * (total - done)


SUPPORT_HEAD, SUPPORT_TAIL = 60, 1500


def support_text(log_path, secrets, version, system):
    """Protokoll zum Weitergeben (z. B. per Mail an die Person, die hilft).

    Passwoerter stehen nie im Protokoll; zur Sicherheit werden sie trotzdem ersetzt.
    Sehr lange Protokolle werden in der Mitte gekuerzt: Anfang und Ende zaehlen.
    """
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = ["(Kein Protokoll vorhanden)"]
    if len(lines) > SUPPORT_HEAD + SUPPORT_TAIL:
        skipped = len(lines) - SUPPORT_HEAD - SUPPORT_TAIL
        lines = lines[:SUPPORT_HEAD] + ["… %d Zeilen ausgelassen …" % skipped] + lines[-SUPPORT_TAIL:]
    text = "\n".join(["Christinas Mail-Sync %s, %s" % (version, system), ""] + lines) + "\n"
    for secret in secrets:
        if secret:
            text = text.replace(secret, "********")
    return text


TMP_PREFIX = "christinas-mail-sync-"
TMP_MARKER = "christinas-mail-sync.tmp"


def remove_stale_tempdirs():
    """Passwortdateien frueherer Laeufe loeschen, die nicht aufraeumen konnten (Absturz,
    App beendet). Nur unter der Sync-Sperre aufrufen: dann laeuft kein anderer Sync.
    Geloescht wird nur, was die App selbst angelegt und markiert hat."""
    for path in glob.glob(os.path.join(tempfile.gettempdir(), TMP_PREFIX + "*")):
        if os.path.isfile(os.path.join(path, TMP_MARKER)):
            shutil.rmtree(path, ignore_errors=True)


def describe_error(e):
    """Verstaendliche Meldung fuer Nicht-Techniker."""
    import imaplib
    import socket
    import ssl
    if isinstance(e, imaplib.IMAP4.error):
        if re.search(r"auth|login|credential|password", str(e), re.I):
            return "Die Anmeldung wurde abgelehnt. Bitte die Zugangsdaten prüfen."
        return "Der Mailserver meldet einen Fehler: %s" % e
    if isinstance(e, (socket.gaierror, ConnectionError, TimeoutError, socket.timeout)):
        return "Keine Verbindung zum Mailserver. Ist das Internet verfügbar?"
    if isinstance(e, ssl.SSLError):
        return "Die sichere Verbindung zum Mailserver ist fehlgeschlagen."
    if isinstance(e, FileNotFoundError):
        return "Ein Programmteil fehlt (%s). Bitte die App neu herunterladen." % e
    return "Unerwarteter Fehler: %s" % e
