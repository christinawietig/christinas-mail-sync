"""Ermittelt, welche Mails der Quelle noch nie ins Ziel uebertragen wurden.

Jede Mail wird ueber ihre Message-ID erkannt (Ersatz ohne Message-ID: Hash aus
Datum, Absender, Betreff). Die Liste aller jemals im Ziel gesehenen Mails steht in
der Statusdatei. Was dort steht, wird nie wieder kopiert - egal in welchem Ordner
die Mail in Quelle oder Ziel inzwischen liegt oder ob sie im Ziel geloescht wurde.

Beide Postfaecher werden nur lesend geoeffnet.
"""
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
    for item in data:
        if not isinstance(item, tuple):
            continue
        uid = re.search(rb"UID (\d+)", item[0])
        if not uid:
            raise PlanError("Antwort ohne UID in: " + folder)
        out.append((int(uid.group(1)), mail_key(unfold(item[1]))))
    return out


def uid_set(uids):
    """[1,2,3,7,9,10] -> '1:3,7,9:10'"""
    uids = sorted(uids)
    parts, start, prev = [], uids[0], uids[0]
    for u in uids[1:] + [None]:
        if u is not None and u == prev + 1:
            prev = u
            continue
        parts.append(str(start) if start == prev else "%d:%d" % (start, prev))
        if u is not None:
            start = prev = u
    return ",".join(parts)


def load_state(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.rstrip("\n") for line in f if line.strip()}


def save_state(path, keys):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for k in sorted(keys):
            f.write(k + "\n")
    os.replace(tmp, path)


def update_state(state_path, target, stopped=lambda: False):
    """Alle Mails im Ziel in die Statusdatei aufnehmen.

    target = (host, port, user, password). Liefert (Menge, Anzahl neu vermerkt).
    """
    keys = load_state(state_path)
    before = len(keys)
    m = connect(*target)
    try:
        for f in folders(m):
            if stopped():
                raise Stopped()
            keys.update(k for _, k in scan(m, f))
    finally:
        m.logout()
        save_state(state_path, keys)
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
            # Klassenordner), wird jedes Exemplar uebertragen - wie in der Quelle.
            new = [uid for uid, key in scan(m, f) if key not in known]
            if new:
                out.append((f, uid_set(new), len(new)))
    finally:
        m.logout()
    return out
