"""Ermittelt, welche Mails der Quelle noch nie ins Ziel uebertragen wurden.

Jede Mail wird ueber ihre Message-ID erkannt (Ersatz ohne Message-ID: Hash aus
Datum, Absender, Betreff). Die Liste aller jemals im Ziel gesehenen Mails steht in
der Statusdatei. Was dort steht, wird nie wieder kopiert - egal in welchem Ordner
die Mail in Quelle oder Ziel inzwischen liegt oder ob sie im Ziel geloescht wurde.
Die Statusdatei gilt nur fuer das Zielpostfach, fuer das sie angelegt wurde.

Beide Postfaecher werden nur lesend geoeffnet.
"""
import base64
import hashlib
import imaplib
import os
import re
import ssl

from . import config

FETCH_ITEMS = "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE FROM SUBJECT)])"
LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?P<sep>"[^"]*"|NIL) (?P<name>.+)$')


class PlanError(Exception):
    pass


class Stopped(Exception):
    pass


def connect(host, port, user, password):
    m = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(cafile=config.ca_file()), timeout=60)
    m.login(user, password)
    return m


def check_login(host, port, user, password):
    """Wirft imaplib.IMAP4.error bzw. OSError, wenn die Anmeldung scheitert."""
    connect(host, port, user, password).logout()


def folders(m):
    typ, data = m.list()
    if typ != "OK":
        raise PlanError("Ordnerliste nicht lesbar")
    out = []
    for line in data:
        if not line:
            continue
        if isinstance(line, tuple):
            # Ordnername als IMAP-Literal: (b'(\\Flags) "." {12}', b'Ordner name')
            mm = LIST_RE.match(re.sub(rb"\{\d+\}$", b'""', line[0]))
            name = line[1].decode()
        else:
            mm = LIST_RE.match(line)
            name = None
        if not mm:
            raise PlanError("Unerwartete LIST-Antwort: %r" % (line,))
        if b"\\noselect" in mm.group("flags").lower():
            continue
        if name is None:
            name = mm.group("name").decode()
            if name.startswith('"') and name.endswith('"'):
                name = re.sub(r'\\(.)', r'\1', name[1:-1])
        out.append(name)
    return out


def quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unfold(header_bytes):
    return re.sub(r"\r?\n[ \t]+", " ", header_bytes.decode("utf-8", "replace"))


def field(headers, name):
    mm = re.search(r"^%s:[ \t]*(.*)$" % name, headers, re.I | re.M)
    return mm.group(1).strip() if mm else ""


def mail_key(headers):
    mid = re.search(r"<[^<>\s]+>", field(headers, "Message-ID"))
    # "<UID@imapsync>" hat imapsync (--addheader) einer Mail ohne Message-ID im Ziel
    # gegeben. Sie zaehlt nicht, sonst passte die Kopie nicht mehr zum Original.
    if mid and not re.fullmatch(r"<\d+@imapsync>", mid.group(0)):
        return mid.group(0)
    raw = "|".join(field(headers, n) for n in ("Date", "From", "Subject"))
    return "nomid:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def decode_folder(name):
    """Ordnernamen lesbar machen: IMAP-UTF-7 ('Elternbriefe &AMQ-' -> 'Elternbriefe Ä')."""
    def utf7(mm):
        b64 = mm.group(1)
        if not b64:
            return "&"
        b64 = b64.replace(",", "/")
        try:
            return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return mm.group(0)
    return re.sub(r"&([A-Za-z0-9+,]*)-", utf7, name)


def folder_label(name):
    """Ordnername fuer die Anzeige: lesbar, INBOX heisst Posteingang."""
    name = decode_folder(name)
    if name.upper() == "INBOX":
        return "Posteingang"
    if name[:6].upper() in ("INBOX.", "INBOX/"):
        return "Posteingang / " + name[6:]
    return name


def scan(m, folder):
    """Liefert [(uid, key), ...] fuer einen Ordner (nur lesend geoeffnet)."""
    typ, data = m.select(quote(folder), readonly=True)
    if typ != "OK":
        raise PlanError("Ordner nicht lesbar: " + folder)
    if int(data[0] or 0) == 0:
        return []
    typ, data = m.uid("FETCH", "1:*", FETCH_ITEMS)
    if typ != "OK":
        raise PlanError("Mails nicht lesbar in: " + folder)
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, tuple):
            continue
        uid = re.search(rb"UID (\d+)", item[0])
        if not uid and i + 1 < len(data) and isinstance(data[i + 1], bytes):
            # Manche Server senden die UID erst nach dem Literal: b' UID 42)'
            uid = re.search(rb"UID (\d+)", data[i + 1])
        if not uid:
            raise PlanError("Antwort ohne UID in: " + folder)
        out.append((int(uid.group(1)), mail_key(unfold(item[1]))))
    return out


def uid_set(wanted, present=None):
    """UID-Menge fuer IMAP, moeglichst kurz: [1,2,3,7,9,10] -> '1:3,7,9:10'.

    present = alle UIDs im Ordner. Dann reicht ein Bereich ueber Luecken hinweg, die
    zu keiner Mail gehoeren (geloeschte Mails): Ohne das wird die Liste bei grossen
    Ordnern so lang, dass Windows den Befehl ablehnt (max. 32767 Zeichen).
    """
    wanted = set(wanted)
    order = sorted(set(present) | wanted) if present is not None else sorted(wanted)
    parts, start, prev = [], None, None
    for u in order + [None]:
        # Ohne present nur lueckenlose Folgen zusammenfassen (uebersprungene UIDs koennten Mails sein)
        if u is not None and u in wanted and (start is None or present is not None or u == prev + 1):
            if start is None:
                start = u
            prev = u
            continue
        if start is not None:
            parts.append(str(start) if start == prev else "%d:%d" % (start, prev))
            start = None
        if u is not None and u in wanted:
            start = prev = u
    return ",".join(parts)


def state_owner(target):
    """Kennung des Zielpostfachs fuer die erste Zeile der Statusdatei."""
    host, _, user, _ = target
    return "# Ziel: %s %s" % (host.lower(), user.lower())


def load_state(path, owner=None):
    """Vermerkte Mails. Gehoert die Datei zu einem anderen Zielpostfach (Einstellungen
    geaendert), zaehlt sie nicht - sonst kaemen dort bekannte Mails nie im neuen Ziel an."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]
    if lines and lines[0].startswith("#"):
        if owner is not None and lines[0] != owner:
            return set()
        lines = lines[1:]
    return set(lines)


def save_state(path, keys, owner=None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if owner:
            f.write(owner + "\n")
        for k in sorted(keys):
            f.write(k + "\n")
    os.replace(tmp, path)


def _logout(m):
    # Bei abgerissener Verbindung scheitert auch das Abmelden - der eigentliche Fehler zaehlt
    try:
        m.logout()
    except Exception:
        pass


def update_state(state_path, target, stopped=lambda: False):
    """Alle Mails im Ziel in die Statusdatei aufnehmen.

    target = (host, port, user, password). Liefert (Menge, Anzahl neu vermerkt).
    """
    owner = state_owner(target)
    keys = load_state(state_path, owner)
    before = len(keys)
    m = connect(*target)
    try:
        for f in folders(m):
            if stopped():
                raise Stopped()
            keys.update(k for _, k in scan(m, f))
    finally:
        # Auch bei Abbruch: was bis hierhin gesehen wurde, bleibt vermerkt
        save_state(state_path, keys, owner)
        _logout(m)
    return keys, len(keys) - before


def plan(state_path, source, target, excludes, stopped=lambda: False):
    """Liefert [(ordner, uid_menge, anzahl), ...] fuer alle Quellordner mit neuen Mails."""
    known, _ = update_state(state_path, target, stopped)
    exclude_re = [re.compile(e) for e in excludes]
    out = []
    m = connect(*source)
    try:
        for f in folders(m):
            if stopped():
                raise Stopped()
            if any(r.search(f) for r in exclude_re):
                continue
            # Liegt eine neue Mail in mehreren Quellordnern (z. B. Gesendet und
            # Klassenordner), wird jedes Exemplar uebertragen, das im selben Lauf neu ist.
            # Kommt ein weiteres Exemplar erst spaeter dazu, gilt die Mail schon als bekannt.
            mails = scan(m, f)
            new = [uid for uid, key in mails if key not in known]
            if new:
                out.append((f, uid_set(new, [uid for uid, _ in mails]), len(new)))
    finally:
        _logout(m)
    return out
