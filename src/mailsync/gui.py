"""Oberflaeche: Einrichtung beim ersten Start, danach Fortschritt und Ergebnis."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import asdict
from tkinter import filedialog, ttk

from . import APP_NAME, config, credentials, plan
from .sync import Sync, describe_error

PAD = 20


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
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.events = queue.Queue()
        self.frame = None
        self.sync = None
        self.settings = config.load_settings()

    def run(self):
        pw = self._passwords()
        if self.settings.complete and all(pw):
            self.show_sync(*pw)
        else:
            self.show_setup()
        self.root.after(100, self._poll)
        self.root.mainloop()

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
                if self.frame and hasattr(self.frame, "on_event"):
                    self.frame.on_event(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def quit(self):
        if self.sync:
            self.sync.stop()
        self.root.destroy()


class SetupFrame(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.root, padding=PAD)
        self.app = app
        # Arbeitskopie: wird erst nach erfolgreicher Pruefung uebernommen
        self.draft = config.Settings(**asdict(app.settings))
        s = self.draft
        ttk.Label(self, text="Einrichtung", font=("", 15, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="Einmalig die Zugangsdaten für beide Postfächer eingeben.\n"
                             "Die Passwörter werden sicher im Schlüsselbund dieses Computers gespeichert.",
                  justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

        profile = ttk.Frame(self)
        profile.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Button(profile, text="Einstellungsdatei laden …", command=self._load_profile).pack(side="left")
        self.profile_label = ttk.Label(profile, text="")
        self.profile_label.pack(side="left", padx=(10, 0))
        self._show_profile()

        self.source_host = tk.StringVar(value=s.source_host)
        self.source_user = tk.StringVar(value=s.source_user)
        self.source_pw = tk.StringVar()
        self.target_host = tk.StringVar(value=s.target_host)
        self.target_user = tk.StringVar(value=s.target_user)
        self.target_pw = tk.StringVar()

        row = self._section(3, "Altes Postfach", self.source_host,
                            "E-Mail-Adresse:", self.source_user, self.source_pw)
        row = self._section(row, "Neues Postfach", self.target_host,
                            "Benutzername:", self.target_user, self.target_pw)
        self.source_entry.bind("<FocusOut>", self._suggest_target)

        self.message = ttk.Label(self, text="", foreground="#b00020", wraplength=420, justify="left")
        self.message.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(self)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        if all(app._passwords()):
            ttk.Button(buttons, text="Abbrechen", command=self._cancel).pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(buttons, text="Prüfen und speichern", command=self._save, default="active")
        self.save_button.pack(side="left")
        app.root.bind("<Return>", lambda e: self._save())
        self._focus_first_empty()

    def _section(self, row, title, host_var, user_label, user_var, pw_var):
        ttk.Label(self, text=title, font=("", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
        entries = []
        for i, (label, var, show) in enumerate((("Server:", host_var, ""), (user_label, user_var, ""),
                                                ("Passwort:", pw_var, "•"))):
            ttk.Label(self, text=label).grid(row=row + 1 + i, column=0, sticky="w", padx=(0, 8))
            e = ttk.Entry(self, textvariable=var, show=show, width=34)
            e.grid(row=row + 1 + i, column=1, sticky="we", pady=2)
            entries.append((var, e))
        if not hasattr(self, "source_entry"):
            self.source_entry = entries[1][1]
        self.entries = getattr(self, "entries", []) + entries
        return row + 4

    def _focus_first_empty(self):
        for var, entry in self.entries:
            if not var.get():
                entry.focus_set()
                return

    def _show_profile(self):
        name = self.draft.profile_name
        self.profile_label.configure(text=("Geladen: " + name) if name else "")

    def _load_profile(self):
        path = filedialog.askopenfilename(
            parent=self.app.root, title="Einstellungsdatei auswählen",
            filetypes=[("Einstellungsdatei", "*.json"), ("Alle Dateien", "*")])
        if not path:
            return
        try:
            self.draft = config.load_profile(path, self.draft)
        except config.ProfileError as e:
            self.message.configure(text=str(e), foreground="#b00020")
            return
        self.source_host.set(self.draft.source_host)
        self.target_host.set(self.draft.target_host)
        self.message.configure(text="")
        self._show_profile()
        self._suggest_target(None)
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
            self.message.configure(text="Bitte alle Felder ausfüllen.", foreground="#b00020")
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
            self.message.configure(text=data["text"], foreground="#b00020")
            self.save_button.state(["!disabled"])
        elif kind == "check_ok":
            source_pw, target_pw = data["passwords"]
            old, new = self.app.settings, self.draft
            try:
                credentials.set_password(new.source_host, new.source_user, source_pw)
                credentials.set_password(new.target_host, new.target_user, target_pw)
            except Exception as e:
                self.message.configure(text="Speichern im Schlüsselbund fehlgeschlagen: %s" % e,
                                       foreground="#b00020")
                self.save_button.state(["!disabled"])
                return
            # Alte Eintraege aufraeumen, wenn sich Server oder Benutzer geaendert haben
            for host, user, new_key in ((old.source_host, old.source_user, (new.source_host, new.source_user)),
                                        (old.target_host, old.target_user, (new.target_host, new.target_user))):
                if host and user and (host, user) != new_key:
                    credentials.delete_password(host, user)
            self.app.settings = new
            config.save_settings(new)
            self.app.root.unbind("<Return>")
            self.app.show_sync(source_pw, target_pw)


class SyncFrame(ttk.Frame):
    def __init__(self, app, source_pw, target_pw):
        super().__init__(app.root, padding=PAD)
        self.app = app
        self.copied = 0
        self._folder = (1, 1)
        self.headline = ttk.Label(self, text="Mail-Sync läuft …", font=("", 15, "bold"))
        self.headline.pack(anchor="w")
        self.detail = ttk.Label(self, text="Verbinde mit den Servern …", width=52)
        self.detail.pack(anchor="w", pady=(4, 10))
        self.bar = ttk.Progressbar(self, mode="indeterminate", length=420)
        self.bar.pack(fill="x")
        self.bar.start(15)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(14, 0))
        self.setup_button = ttk.Button(buttons, text="Zugangsdaten ändern", command=app.show_setup)
        self.log_button = ttk.Button(buttons, text="Protokoll öffnen", command=self._open_log)
        self.main_button = ttk.Button(buttons, text="Stopp", command=self._main)
        self.main_button.pack(side="right")

        app.sync = Sync(app.settings, source_pw, target_pw, app.post)
        self.log_path = app.sync.log_path
        app.sync.start()

    def _open_log(self):
        open_path(self.log_path)

    def _main(self):
        if self.app.sync:
            self.main_button.state(["disabled"])
            self.headline.configure(text="Wird abgebrochen …")
            self.app.sync.stop()
        else:
            self.app.quit()

    def on_event(self, kind, data):
        if kind == "status":
            self.detail.configure(text=data["text"])
        elif kind == "folder":
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=data["n"], value=data["i"] - 1)
            self._progress(data["i"], data["n"])
            self._folder = (data["i"], data["n"])
        elif kind == "copied":
            self.copied += 1
            self._progress(*self._folder)
        elif kind == "done":
            r = data["result"]
            if r.stopped:
                self._finish("Sync abgebrochen.", "Beim nächsten Start geht es einfach weiter.", ok=True)
            elif r.failed_folders:
                self._finish("Nicht alles hat geklappt.",
                             "%d Mail(s) übertragen, in %d Ordner(n) gab es Fehler. "
                             "Einfach später nochmal starten." % (r.transferred, r.failed_folders), ok=False)
            elif r.transferred == 0:
                self._finish("Alles aktuell.", "Keine neuen Mails.", ok=True)
            else:
                self._finish("Fertig.", "%d neue Mail(s) übertragen." % r.transferred, ok=True)
        elif kind == "error":
            self._finish("Der Mail-Sync ist fehlgeschlagen.", data["text"], ok=False)

    def _progress(self, i, n):
        self.bar.configure(value=i - 1)
        self.detail.configure(text="Ordner %d von %d – %d neue Mail(s) bisher" % (i, n, self.copied))

    def _finish(self, title, text, ok):
        self.bar.stop()
        self.bar.configure(mode="determinate", maximum=1, value=1 if ok else 0)
        self.headline.configure(text=title)
        self.detail.configure(text=text, wraplength=420)
        self.main_button.configure(text="Schließen")
        self.main_button.state(["!disabled"])
        self.app.sync = None
        self.setup_button.pack(side="left")
        if not ok:
            self.log_button.pack(side="left", padx=(8, 0))
        self.app.root.bell()
        self.app.root.lift()


def main():
    App().run()
