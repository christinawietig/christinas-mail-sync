"""Oberflaeche: Einrichtung beim ersten Start, danach Fortschritt und Ergebnis."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import asdict
from tkinter import ttk

from . import APP_NAME, __version__, config, credentials, plan, setupcode
from .sync import Sync, describe_error

PAD = 20
RED, GREEN, GREY, LINK = "#b00020", "#1b7f3b", "#6b6b6b", "#1a5fd0"
REPO_URL = "https://github.com/christinawietig/christinas-mail-sync"
# Feste Zeichenbreite fuer den Einrichtungscode
MONO = ("Menlo", 12) if sys.platform == "darwin" else ("Consolas", 11) if sys.platform == "win32" else ("Courier", 11)


def bundled(*parts):
    """Mitgelieferte Datei (im App-Paket bzw. im Quelltext)."""
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, *parts)


def asset(name):
    return bundled("assets", name)


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
        if sys.platform == "darwin":
            # Einmalig ins Dock (im Hintergrund, Fehler egal)
            from . import dock
            self.root.after(1500, lambda: threading.Thread(target=dock.add_once, daemon=True).start())
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
                e = ttk.Entry(self, textvariable=var, width=40, show="•" if var is password else "")
                e.grid(row=row + 1 + i, column=1, sticky="we", pady=2)
                self.entries.append((var, e))
            row += 4
        self.entries[1][1].bind("<FocusOut>", self._suggest_target)

        ttk.Label(self, text="Einrichtungscode", font=("", 12, "bold")).grid(row=row, column=0, columnspan=2,
                                                                          sticky="w", pady=(14, 0))
        ttk.Label(self, text="Diese Einstellungen ohne Passwörter – zum Weitergeben an Kollegen und Kolleginnen.",
                  foreground=GREY).grid(row=row + 1, column=0, columnspan=2, sticky="w")
        self.code_text = tk.Text(self, height=4, width=50, wrap="char", relief="solid", borderwidth=1,
                                 highlightthickness=0, font=MONO, state="disabled")
        self.code_text.grid(row=row + 2, column=0, columnspan=2, sticky="we", pady=(4, 4))
        code_buttons = ttk.Frame(self)
        code_buttons.grid(row=row + 3, column=0, columnspan=2, sticky="we")
        self.code_status = ttk.Label(code_buttons, text="", wraplength=280, justify="left")
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
        self.setup_button = ttk.Button(buttons, text="Einstellungen", command=app.show_setup)
        self.log_button = ttk.Button(buttons, text="Protokoll öffnen", command=self._open_log)
        self.about_button = ttk.Button(buttons, text="Über …", command=app.show_about)
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
        self.about_button.pack(side="left", padx=(8, 0))
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
                lic.insert("1.0", fh.read())
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


def main():
    App().run()
