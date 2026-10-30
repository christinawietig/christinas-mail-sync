"""Oberflaeche: Einrichtung beim ersten Start, danach Fortschritt und Ergebnis."""
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import asdict
from tkinter import ttk

from . import APP_NAME, __version__, config, credentials, plan, setupcode, update
from .sync import Sync, describe_error, estimate_remaining, format_count, format_remaining, support_text

PAD = 20
RED, GREEN, GREY, LINK = "#b00020", "#1b7f3b", "#6b6b6b", "#1a5fd0"
REPO_URL = update.REPO_URL
# Feste Zeichenbreite fuer den Einrichtungscode
MONO = ("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11) if sys.platform == "win32" else ("Courier", 11)


def bundled(*parts):
    """Mitgelieferte Datei (im App-Paket bzw. im Quelltext)."""
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, *parts)


def asset(name):
    return bundled("assets", name)


PASTE_KEYS = "⌘ + V" if sys.platform == "darwin" else "Strg + V"
HELP_TEXT = ("Wenn es weiterhin nicht klappt, schicke mir das Protokoll. Klicke dazu auf „Protokoll kopieren“. "
             "Damit liegt das Protokoll in der Zwischenablage. Füge es in eine neue E-Mail ein und schicke "
             "sie an Christina.")
COPIED_TEXT = ("✓ Das Protokoll liegt jetzt in der Zwischenablage. Öffne eine neue E-Mail, füge es mit %s ein "
               "und schicke die E-Mail an Christina." % PASTE_KEYS)


def system_name():
    if sys.platform == "darwin":
        return "macOS " + platform.mac_ver()[0]
    if sys.platform == "win32":
        return "Windows " + platform.version()
    return platform.platform()


def download_url():
    """Direkter Download der neuesten Version fuer dieses System."""
    name = "Christinas-Mail-Sync-Setup.exe" if sys.platform == "win32" else "Christinas-Mail-Sync.dmg"
    return update.LATEST_URL + "/download/" + name


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


class App:
    def __init__(self):
        if sys.platform == "win32":
            # Sonst ist das Fenster auf hochaufloesenden Bildschirmen unscharf
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        try:
            self._icon = tk.PhotoImage(file=asset("MailSync-256.png"))
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.events = queue.Queue()
        self.frame = None
        self.banner = None
        self.sync = None
        self.settings = config.load_settings()
        # macOS: Menue "Christinas Mail-Sync" -> "Ueber Christinas Mail-Sync" (Ueber-Dialog)
        if sys.platform == "darwin":
            self.root.createcommand("tkAboutDialog", self.show_about)

    def show_about(self):
        AboutDialog(self)

    def run(self):
        pw = self._passwords()
        if self.settings.complete and all(pw):
            self.show_sync(*pw)
        else:
            self.show_setup()
        self.root.after(100, self._poll)
        # Neue Version? Im Hintergrund nachsehen, ohne Netz passiert einfach nichts
        threading.Thread(target=self._check_update, daemon=True).start()
        if sys.platform == "darwin":
            # Einmalig ins Dock (im Hintergrund, Fehler egal)
            from . import dock
            self.root.after(1500, lambda: threading.Thread(target=dock.add_once, daemon=True).start())
        self.root.mainloop()

    def _check_update(self):
        latest = update.check()
        if latest:
            self.post("update", version=latest)

    def show_update(self, version):
        """Hinweis oben im Fenster, bleibt beim Wechsel zwischen Einstellungen und Sync."""
        if self.banner:
            return
        self.banner = tk.Label(self.root, text="Neue Version %s verfügbar – hier klicken zum Herunterladen" % version,
                               bg="#fff4c2", fg="#1f1f1f", cursor="hand2", padx=PAD, pady=8, anchor="w")
        self.banner.bind("<Button-1>", lambda e: open_path(download_url()))
        if self.frame:
            self.banner.pack(fill="x", before=self.frame)
        else:
            self.banner.pack(fill="x")

    def _passwords(self):
        s = self.settings
        if not s.complete:
            return None, None
        return (credentials.get_password(s.source_host, s.source_user),
                credentials.get_password(s.target_host, s.target_user))

    def _show(self, frame):
        if self.frame:
            self.frame.destroy()
        self.frame = frame
        frame.pack(fill="both", expand=True)
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 3
        self.root.geometry("+%d+%d" % (x, y))
        self.root.lift()
        self.root.focus_force()

    def show_setup(self):
        self._show(SetupFrame(self))

    def show_sync(self, source_pw, target_pw):
        self._show(SyncFrame(self, source_pw, target_pw))

    # Ereignisse aus Hintergrund-Threads werden nur hier im Haupt-Thread verarbeitet
    def post(self, kind, **data):
        self.events.put((kind, data))

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "update":
                    self.show_update(data["version"])
                elif self.frame and hasattr(self.frame, "on_event"):
                    self.frame.on_event(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def quit(self):
        if self.sync:
            self.sync.stop()
            # Den Lauf noch aufraeumen lassen (Passwortdateien loeschen)
            self.sync.join(5)
        self.root.destroy()


class SetupFrame(ttk.Frame):
    """Einstellungen. Darunter dieselben Einstellungen als Einrichtungscode
    (ohne Passwoerter), der sich bei jeder Aenderung sofort mitaendert.
    Kopieren: Code weitergeben. Einfuegen: erhaltenen Code uebernehmen."""

    def __init__(self, app):
        super().__init__(app.root, padding=PAD)
        self.app = app
        # Arbeitskopie: wird erst nach erfolgreicher Pruefung uebernommen
        self.draft = config.Settings(**asdict(app.settings))
        s = self.draft
        pw = app._passwords()
        ttk.Label(self, text="Einstellungen", font=("", 15, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")

        self.source_host = tk.StringVar(value=s.source_host)
        self.source_user = tk.StringVar(value=s.source_user)
        self.source_pw = tk.StringVar(value=pw[0] or "")
        self.target_host = tk.StringVar(value=s.target_host)
        self.target_user = tk.StringVar(value=s.target_user)
        self.target_pw = tk.StringVar(value=pw[1] or "")
        self.entries = []
        row = 1
        for title, host, user_label, user, password in (
                ("Altes Postfach", self.source_host, "E-Mail-Adresse:", self.source_user, self.source_pw),
                ("Neues Postfach", self.target_host, "Benutzername:", self.target_user, self.target_pw)):
            ttk.Label(self, text=title, font=("", 12, "bold")).grid(row=row, column=0, columnspan=2,
                                                                    sticky="w", pady=(10, 4))
            for i, (label, var) in enumerate((("Server:", host), (user_label, user), ("Passwort:", password))):
                ttk.Label(self, text=label).grid(row=row + 1 + i, column=0, sticky="w", padx=(0, 8))
                e = ttk.Entry(self, textvariable=var, width=46, show="•" if var is password else "")
                e.grid(row=row + 1 + i, column=1, sticky="we", pady=2)
                self.entries.append((var, e))
            row += 4
        self.entries[1][1].bind("<FocusOut>", self._suggest_target)

        ttk.Label(self, text="Einrichtungscode", font=("", 12, "bold")).grid(row=row, column=0, columnspan=2,
                                                                          sticky="w", pady=(14, 0))
        ttk.Label(self, text="Diese Einstellungen ohne Passwörter – zum Weitergeben an Kollegen und Kolleginnen.",
                  foreground=GREY).grid(row=row + 1, column=0, columnspan=2, sticky="w")
        self.code_text = tk.Text(self, height=4, width=50, wrap="char", relief="solid", borderwidth=1,
                                 highlightthickness=0, font=MONO, padx=6, pady=4, state="disabled")
        self.code_text.grid(row=row + 2, column=0, columnspan=2, sticky="we", pady=(4, 4))
        code_buttons = ttk.Frame(self)
        code_buttons.grid(row=row + 3, column=0, columnspan=2, sticky="we")
        self.code_status = ttk.Label(code_buttons, text="", wraplength=340, justify="left")
        self.code_status.pack(side="left")
        ttk.Button(code_buttons, text="Einfügen", command=self._paste).pack(side="right")
        self.copy_button = ttk.Button(code_buttons, text="Kopieren", command=self._copy)
        self.copy_button.pack(side="right", padx=(0, 8))
        row += 4

        self.message = ttk.Label(self, text="", foreground=RED, wraplength=440, justify="left")
        self.message.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="we", pady=(12, 0))
        ttk.Button(buttons, text="Über …", command=app.show_about).pack(side="left")
        self.save_button = ttk.Button(buttons, text="Prüfen und speichern", command=self._save, default="active")
        self.save_button.pack(side="right")
        if all(pw):
            ttk.Button(buttons, text="Abbrechen", command=self._cancel).pack(side="right", padx=(0, 8))
        app.root.bind("<Return>", lambda e: self._save())

        for var in (self.source_host, self.source_user, self.target_host, self.target_user):
            var.trace_add("write", lambda *_: self._update_code())
        self._update_code()
        self._focus_first_empty()

    def _focus_first_empty(self):
        for var, entry in self.entries:
            if not var.get():
                entry.focus_set()
                return

    def _code(self):
        """Einrichtungscode aus den Feldern, oder "" solange ein Server fehlt."""
        src, dst = self.source_host.get().strip(), self.target_host.get().strip()
        if not (src and dst):
            return ""
        d = self.draft
        src_user, dst_user = self.source_user.get().strip(), self.target_user.get().strip()
        rule = d.target_user_rule or setupcode.derive_rule(src_user, dst_user)
        if rule and dst_user == config.Settings(target_user_rule=rule).suggest_target_user(src_user):
            dst_user = ""  # ergibt sich beim Einfuegen von selbst aus der alten Adresse
        try:
            return setupcode.encode(src, d.source_port, dst, d.target_port, rule, d.exclude_folders,
                                    src_user, dst_user)
        except ValueError:
            return ""

    def _update_code(self):
        code = self._code()
        self.code_text.configure(state="normal")
        self.code_text.delete("1.0", "end")
        # Zeilen nur zwischen ganzen Fuenfergruppen umbrechen
        groups = code.split("-")
        self.code_text.insert("1.0", "-\n".join("-".join(groups[i:i + 8]) for i in range(0, len(groups), 8)))
        self.code_text.configure(state="disabled")
        self.copy_button.configure(text="Kopieren")
        self.copy_button.state(["!disabled"] if code else ["disabled"])
        if not code:
            self._status("Erscheint, sobald beide Server eingetragen sind.", GREY)
        elif str(self.code_status["foreground"]) == GREY:
            self._status("", "")

    def _status(self, text, color):
        self.code_status.configure(text=text, foreground=color)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._code())
        self.copy_button.configure(text="✓ Kopiert")

    def _paste(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            c = setupcode.decode(text)
        except setupcode.CodeError as e:
            self._status(str(e) if text.strip() else "Erst einen Einrichtungscode kopieren, dann hier einfügen.", RED)
            return
        d = self.draft
        d.source_port, d.target_port = c["source_port"], c["target_port"]
        d.exclude_folders, d.target_user_rule = c["exclude_folders"], c["target_user_rule"]
        self.source_host.set(c["source_host"])
        self.target_host.set(c["target_host"])
        # Benutzernamen nur uebernehmen, wenn der Code welche enthaelt
        if c["source_user"]:
            self.source_user.set(c["source_user"])
            self.target_user.set(c["target_user"] or self.draft.suggest_target_user(c["source_user"]))
        self._suggest_target(None)
        self._status("✓ Übernommen. Jetzt die Passwörter eingeben.", GREEN)
        self._focus_first_empty()

    def _suggest_target(self, _event):
        if not self.target_user.get().strip():
            self.target_user.set(self.draft.suggest_target_user(self.source_user.get()))

    def _cancel(self):
        self.app.root.unbind("<Return>")
        self.app.show_sync(*self.app._passwords())

    def _save(self):
        if str(self.save_button["state"]) == "disabled":
            return
        self._suggest_target(None)
        values = (self.source_host.get().strip(), self.source_user.get().strip(), self.source_pw.get(),
                  self.target_host.get().strip(), self.target_user.get().strip(), self.target_pw.get())
        if not all(values):
            self.message.configure(text="Bitte alle Felder ausfüllen.", foreground=RED)
            self._focus_first_empty()
            return
        d = self.draft
        d.source_host, d.source_user, d.target_host, d.target_user = values[0], values[1], values[3], values[4]
        self.message.configure(text="Prüfe die Anmeldung …", foreground="")
        self.save_button.state(["disabled"])
        threading.Thread(target=self._check, args=(values[2], values[5]), daemon=True).start()

    def _check(self, source_pw, target_pw):
        d = self.draft
        for label, host, port, user, pw in (("alten", d.source_host, d.source_port, d.source_user, source_pw),
                                            ("neuen", d.target_host, d.target_port, d.target_user, target_pw)):
            try:
                plan.check_login(host, port, user, pw)
            except Exception as e:
                self.app.post("check_failed", text="Anmeldung am %s Postfach fehlgeschlagen: %s"
                                                   % (label, describe_error(e)))
                return
        self.app.post("check_ok", passwords=(source_pw, target_pw))

    def on_event(self, kind, data):
        if kind == "check_failed":
            self.message.configure(text=data["text"], foreground=RED)
            self.save_button.state(["!disabled"])
        elif kind == "check_ok":
            source_pw, target_pw = data["passwords"]
            old, new = self.app.settings, self.draft
            try:
                credentials.set_password(new.source_host, new.source_user, source_pw)
                credentials.set_password(new.target_host, new.target_user, target_pw)
            except Exception as e:
                self.message.configure(text="Speichern im Schlüsselbund fehlgeschlagen: %s" % e,
                                       foreground=RED)
                self.save_button.state(["!disabled"])
                return
            # Alte Eintraege aufraeumen, wenn sich Server oder Benutzer geaendert haben.
            # Nie einen, der gerade gespeichert wurde (z. B. alt und neu vertauscht).
            keep = {(new.source_host, new.source_user), (new.target_host, new.target_user)}
            for host, user in ((old.source_host, old.source_user), (old.target_host, old.target_user)):
                if host and user and (host, user) not in keep:
                    credentials.delete_password(host, user)
            self.app.settings = new
            config.save_settings(new)
            self.app.root.unbind("<Return>")
            self.app.show_sync(source_pw, target_pw)


class SyncFrame(ttk.Frame):
    def __init__(self, app, source_pw, target_pw):
        super().__init__(app.root, padding=PAD)
        self.app = app
        self.passwords = (source_pw, target_pw)
        self.copied = 0
        self.total = 0
        self.started = None
        self.previewing = False
        self._folder = (1, 1)
        self.headline = ttk.Label(self, text="Mail-Sync läuft …", font=("", 15, "bold"))
        self.headline.pack(anchor="w")
        self.detail = ttk.Label(self, text="Verbinde mit den Servern …", wraplength=420, justify="left")
        self.detail.pack(anchor="w", pady=(4, 10))
        # Vorschau beim ersten Lauf: neue Mails je Ordner
        self.preview = tk.Text(self, height=8, width=52, relief="solid", borderwidth=1, highlightthickness=0,
                               padx=8, pady=6, wrap="none")
        self.bar = ttk.Progressbar(self, mode="indeterminate", length=420)
        self.bar.pack(fill="x")
        self.bar.start(15)
        self.eta = ttk.Label(self, text="", foreground=GREY)
        self.eta.pack(anchor="w", pady=(4, 0))
        # Nach Fehlern: wie man das Protokoll weitergibt
        self.help = ttk.Label(self, text=HELP_TEXT, wraplength=420, justify="left")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(10, 0))
        self.setup_button = ttk.Button(buttons, text="Einstellungen", command=app.show_setup)
        self.copy_button = ttk.Button(buttons, text="Protokoll kopieren", command=self._copy_log)
        self.log_button = ttk.Button(buttons, text="Protokoll öffnen", command=self._open_log)
        self.about_button = ttk.Button(buttons, text="Über …", command=app.show_about)
        self.main_button = ttk.Button(buttons, text="Stopp", command=self._main)
        self.main_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, text="Abbrechen", command=self._main)

        app.sync = Sync(app.settings, source_pw, target_pw, app.post)
        self.log_path = app.sync.log_path
        app.sync.start()

    def _open_log(self):
        open_path(self.log_path)

    def _copy_log(self):
        """Protokoll in die Zwischenablage, z. B. um es der Person zu schicken, die hilft."""
        self.clipboard_clear()
        self.clipboard_append(support_text(self.log_path, self.passwords, __version__, system_name()))
        self.copy_button.configure(text="✓ Kopiert")
        self.help.configure(text=COPIED_TEXT, foreground=GREEN)

    def _main(self):
        if self.app.sync:
            self.main_button.state(["disabled"])
            self.cancel_button.state(["disabled"])
            self.headline.configure(text="Wird abgebrochen …")
            self.app.sync.stop()
        else:
            self.app.quit()

    def _start(self):
        """Vorschau bestaetigt: jetzt uebertragen."""
        self.previewing = False
        self.preview.pack_forget()
        self.cancel_button.pack_forget()
        self.main_button.configure(text="Stopp", command=self._main, default="normal")
        self.headline.configure(text="Mail-Sync läuft …")
        self.app.root.unbind("<Return>")
        self.app.sync.proceed()

    def on_event(self, kind, data):
        if kind == "status":
            self.detail.configure(text=data["text"])
        elif kind == "preview":
            self._show_preview(data["total"], data["folders"])
        elif kind == "planned":
            self.total = data["total"]
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=max(self.total, 1), value=0)
        elif kind == "folder":
            self._folder = (data["i"], data["n"])
            if self.started is None:
                self.started = time.monotonic()
            self._progress()
        elif kind == "copied":
            self.copied += 1
            self._progress()
        elif kind == "done":
            r = data["result"]
            if r.stopped and self.previewing:
                self._finish("Abgebrochen.", "Es wurde nichts übertragen.", ok=True)
            elif r.stopped:
                self._finish("Sync abgebrochen.", "Beim nächsten Start geht es einfach weiter.", ok=True)
            elif r.failed_folders:
                self._finish("Nicht alles hat geklappt.",
                             "%s Mail(s) übertragen, in %d Ordner(n) gab es Fehler. Starte den Sync einfach "
                             "später noch einmal." % (format_count(r.transferred), r.failed_folders), ok=False)
            elif r.transferred == 0:
                self._finish("Alles aktuell.", "Keine neuen Mails.", ok=True)
            else:
                self._finish("Fertig.", "%s neue Mail(s) übertragen." % format_count(r.transferred), ok=True)
        elif kind == "error":
            self._finish("Der Mail-Sync ist fehlgeschlagen.", data["text"], ok=False)

    def _show_preview(self, total, folders):
        self.previewing = True
        self.bar.stop()
        self.bar.pack_forget()
        self.headline.configure(text="Bereit zum Übertragen")
        self.detail.configure(text="%s neue Mail(s) in %d Ordner(n). Es wird nur kopiert, im alten Postfach "
                                   "bleibt alles, wie es ist." % (format_count(total), len(folders)))
        self.preview.configure(state="normal", height=min(max(len(folders), 3), 10))
        width = max(len(plan.folder_label(f)) for f, _ in folders) + 2
        for f, n in folders:
            self.preview.insert("end", "%-*s%8s\n" % (width, plan.folder_label(f), format_count(n)))
        self.preview.configure(state="disabled", font=MONO)
        self.preview.pack(fill="x", before=self.eta)
        self.main_button.configure(text="Übertragen", command=self._start, default="active")
        self.cancel_button.pack(side="right", padx=(0, 8))
        self.app.root.bind("<Return>", lambda e: self._start())
        self.app.root.lift()

    def _progress(self):
        i, n = self._folder
        done = min(self.copied, self.total) if self.total else self.copied
        self.bar.configure(value=done)
        if self.total:
            self.detail.configure(text="Ordner %d von %d – %s von %s Mail(s)"
                                       % (i, n, format_count(done), format_count(self.total)))
        else:
            self.detail.configure(text="Ordner %d von %d – %s neue Mail(s) bisher" % (i, n, format_count(done)))
        left = estimate_remaining(done, self.total, time.monotonic() - (self.started or time.monotonic()))
        self.eta.configure(text="Noch " + format_remaining(left) if left is not None else "")

    def _finish(self, title, text, ok):
        self.app.root.unbind("<Return>")
        self.preview.pack_forget()
        self.cancel_button.pack_forget()
        if not self.bar.winfo_ismapped():
            self.bar.pack(fill="x", before=self.eta)
        self.bar.stop()
        self.bar.configure(mode="determinate", maximum=1, value=1 if ok else 0)
        self.eta.configure(text="")
        self.headline.configure(text=title)
        self.detail.configure(text=text)
        self.main_button.configure(text="Schließen", command=self._main, default="active")
        self.main_button.state(["!disabled"])
        self.app.sync = None
        self.setup_button.pack(side="left")
        if ok:
            self.about_button.pack(side="left", padx=(8, 0))
        else:
            # Hilfe holen: Protokoll weitergeben oder selbst ansehen
            self.help.pack(anchor="w", pady=(4, 0), before=self.eta)
            self.copy_button.pack(side="left", padx=(8, 0))
            self.log_button.pack(side="left", padx=(8, 0))
        self.app.root.bell()
        self.app.root.lift()


class AboutDialog(tk.Toplevel):
    """Wer die App gemacht hat, Lizenz mit vollstaendigem Haftungsausschluss."""

    def __init__(self, app):
        super().__init__(app.root)
        self.title("Über " + APP_NAME)
        self.resizable(False, False)
        self.transient(app.root)
        f = ttk.Frame(self, padding=PAD)
        f.pack(fill="both", expand=True)

        head = ttk.Frame(f)
        head.pack(fill="x")
        try:
            self._icon = tk.PhotoImage(file=asset("MailSync-256.png")).subsample(4)
            ttk.Label(head, image=self._icon).pack(side="left", padx=(0, 14))
        except tk.TclError:
            pass
        text = ttk.Frame(head)
        text.pack(side="left", anchor="n")
        ttk.Label(text, text=APP_NAME, font=("", 15, "bold")).pack(anchor="w")
        ttk.Label(text, text="Version " + __version__, foreground=GREY).pack(anchor="w")
        ttk.Label(text, text="Ein privates Projekt von Christina Wietig").pack(anchor="w", pady=(6, 0))
        link = ttk.Label(text, text=REPO_URL.replace("https://", ""), foreground=LINK, cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: open_path(REPO_URL))

        ttk.Label(f, text="Nutzung auf eigene Gefahr: Die Software wird ohne jede Gewährleistung und ohne "
                          "Haftung bereitgestellt. Maßgeblich ist die folgende Lizenz.",
                  wraplength=520, justify="left", font=("", 12, "bold")).pack(anchor="w", pady=(16, 6))
        box = ttk.Frame(f)
        box.pack(fill="both")
        lic = tk.Text(box, height=16, width=74, wrap="word", relief="solid", borderwidth=1,
                      highlightthickness=0, font=MONO, padx=8, pady=6)
        scroll = ttk.Scrollbar(box, command=lic.yview)
        lic.configure(yscrollcommand=scroll.set)
        lic.pack(side="left", fill="both")
        scroll.pack(side="right", fill="y")
        try:
            with open(bundled("LICENSE"), encoding="utf-8") as fh:
                lic.insert("1.0", unwrap(fh.read()))
        except OSError:
            lic.insert("1.0", "MIT License – siehe " + REPO_URL + "/blob/main/LICENSE")
        lic.configure(state="disabled")

        third = ttk.Label(f, text="Mitgelieferte Software (u. a. imapsync) und ihre Lizenzen",
                          foreground=LINK, cursor="hand2")
        third.pack(anchor="w", pady=(8, 0))
        third.bind("<Button-1>", lambda e: open_path(REPO_URL + "/blob/main/THIRD_PARTY.md"))
        ttk.Button(f, text="Schließen", command=self.destroy, default="active").pack(anchor="e", pady=(12, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_reqwidth()) // 2
        self.geometry("+%d+%d" % (max(x, 0), max(app.root.winfo_rooty() - 40, 20)))
        self.grab_set()


def unwrap(text):
    """Absaetze zu je einer Zeile zusammenfuegen, damit das Textfeld selbst umbricht."""
    paras = text.strip().split("\n\n")
    return "\n\n".join(" ".join(line.strip() for line in p.splitlines()) for p in paras)


def main():
    App().run()
