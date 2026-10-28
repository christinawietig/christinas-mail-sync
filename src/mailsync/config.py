"""Einstellungen und Speicherorte.

Im Programm stehen keine Servernamen. Sie kommen aus einem Einrichtungscode
(siehe setupcode.py), den man beim ersten Start einfuegt, oder werden von Hand
eingetragen. Gespeichert wird alles in settings.json im
Datenordner, die Passwoerter getrennt im Schluesselbund (siehe credentials.py).
"""
import json
import os
import sys
from dataclasses import asdict, dataclass, field

import certifi

from . import APP_NAME, setupcode

DEFAULT_PORT = 993


def data_dir():
    """Ordner fuer Einstellungen, Statusdatei und Logs (wird angelegt).
    MAILSYNC_DATA_DIR ersetzt ihn (fuer den automatischen Test)."""
    if os.environ.get("MAILSYNC_DATA_DIR"):
        path = os.environ["MAILSYNC_DATA_DIR"]
        os.makedirs(path, exist_ok=True)
        return path
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(path, 0o700)  # nur fuer den eigenen Benutzer lesbar
    return path


def ca_file():
    """Zertifikate, denen bei der Pruefung der Server vertraut wird.
    MAILSYNC_CA_FILE ersetzt sie (fuer den Test-Mailserver im automatischen Test)."""
    return os.environ.get("MAILSYNC_CA_FILE") or certifi.where()


def state_file():
    """Message-IDs aller Mails, die schon im Ziel angekommen sind."""
    return os.path.join(data_dir(), "uebertragen.txt")


def log_dir():
    path = os.path.join(data_dir(), "Logs")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Settings:
    source_host: str = ""
    source_port: int = DEFAULT_PORT
    source_user: str = ""
    target_host: str = ""
    target_port: int = DEFAULT_PORT
    target_user: str = ""
    # Ordner des alten Postfachs, die nie uebertragen werden (genaue Namen)
    exclude_folders: list = field(default_factory=list)
    # "localpart": neuer Benutzername = Teil der alten Adresse vor dem @, "same": gleich
    target_user_rule: str = ""

    @property
    def complete(self):
        return bool(self.source_host and self.source_user and self.target_host and self.target_user)

    def suggest_target_user(self, source_user):
        if self.target_user_rule == "localpart":
            return source_user.split("@", 1)[0].strip()
        if self.target_user_rule == "same":
            return source_user.strip()
        return ""


def _settings_path():
    return os.path.join(data_dir(), "settings.json")


def _from_dict(raw, base=None):
    s = base or Settings()
    for name in Settings.__dataclass_fields__:
        if name in raw:
            setattr(s, name, raw[name])
    return s


def load_settings():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return _from_dict(json.load(f))
    except (OSError, ValueError):
        return Settings()


def save_settings(settings):
    path = _settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def apply_code(code, base):
    """Uebernimmt die Einstellungen aus einem Einrichtungscode in eine Kopie von base.
    Benutzernamen bleiben unberuehrt. Wirft setupcode.CodeError."""
    return _from_dict(setupcode.decode(code), Settings(**asdict(base)))
