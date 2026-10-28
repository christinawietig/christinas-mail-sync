"""Ein Sync-Lauf: Plan erstellen, neue Mails mit imapsync kopieren, Status vermerken.

Jede Mail wird genau einmal uebertragen: plan.py merkt sich alle uebertragenen
Mails (Message-ID) in der Statusdatei, und imapsync bekommt pro Ordner nur die
UIDs der noch nie uebertragenen Mails. Sortieren/Loeschen in Quelle oder Ziel
fuehrt daher nie zu Duplikaten. Nur eine Richtung, es wird nichts geloescht.

Passwoerter gehen nur ueber temporaere Dateien (nur fuer den Nutzer lesbar) an
imapsync und werden am Ende des Laufs geloescht. Sie erscheinen nie in Logs.
"""
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
        cmd = [imapsync_path(), "--justconnect", "--nolog", "--noreleasecheck", "--tmpdir", tmp,
               "--host1", host1, "--port1", str(port), "--ssl1",
               "--host2", host2, "--port2", str(port), "--ssl2", *ssl_args()]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, cwd=tmp, timeout=300,
                           creationflags=flags, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0 and "Exiting after a justconnect" in p.stdout
    return (0 if ok else 1), p.stdout + p.stderr


def imapsync_path():
    """imapsync aus dem App-Paket, im Quelltext aus vendor/, sonst aus dem PATH."""
    name = "imapsync.exe" if sys.platform == "win32" else "imapsync"
    if getattr(sys, "frozen", False):
        candidates = [
            os.path.join(sys._MEIPASS, "imapsync", name),
            # macOS-App: Contents/MacOS/<app> -> Contents/Resources/imapsync/
            os.path.join(os.path.dirname(sys.executable), "..", "Resources", "imapsync", name),
        ]
    else:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [os.path.join(root, "vendor", name)]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError("imapsync wurde nicht gefunden.")


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
      status(text) | folder(i, n, name) | copied() | done(result) | error(text)
    """

    def __init__(self, settings, source_password, target_password, on_event):
        self.source = (settings.source_host, settings.source_port, settings.source_user, source_password)
        self.target = (settings.target_host, settings.target_port, settings.target_user, target_password)
        self.exclude = ["^%s$" % re.escape(f) for f in settings.exclude_folders]
        self.on_event = on_event
        self._stop = threading.Event()
        self._proc = None
        self.log_path = os.path.join(config.log_dir(), "letzter-lauf.txt")
        self._log = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
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
            with open(self.log_path, "w", encoding="utf-8") as self._log:
                self._say("%s  Start" % time.strftime("%Y-%m-%d %H:%M:%S"))
                with Lock(os.path.join(config.data_dir(), "sync.lock")):
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
        exe = imapsync_path()
        state = config.state_file()
        self.on_event("status", text="Prüfe die Postfächer …")
        todo = plan.plan(state, self.source, self.target, self.exclude, self._stop.is_set)
        total = sum(n for _, _, n in todo)
        self._say("Neue Mails: %d in %d Ordner(n)" % (total, len(todo)))

        result = Result()
        tmp = tempfile.mkdtemp(prefix="mailsync-")
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

        # Was jetzt im Ziel liegt, als uebertragen vermerken (auch nach Abbruch)
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
            exe,
            "--host1", host1, "--port1", str(port1), "--ssl1", "--user1", user1, "--passfile1", pass1,
            "--host2", host2, "--port2", str(port2), "--ssl2", "--user2", user2, "--passfile2", pass2,
            "--automap", "--subscribeall", "--noresyncflags", "--addheader", *ssl_args(),
            "--tmpdir", tmp, "--logdir", config.log_dir(), "--noreleasecheck",
            "--folder", folder, "--search1", "UID " + uids,
        ]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=tmp, creationflags=flags, text=True, encoding="utf-8", errors="replace")
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
