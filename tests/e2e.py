"""Ende-zu-Ende-Test der fertigen App mit einem Test-Mailserver (GreenMail).

Startet GreenMail mit zwei Postfaechern ("alt" und "neu") und einem eigenen
Zertifikat, legt Mails im alten Postfach an und laesst die App ohne Oberflaeche
synchronisieren (--sync-headless). Geprueft wird, was die README verspricht:
jede Mail genau einmal, Ordner/Datum/Gelesen bleiben, ausgeschlossene Ordner
und im Ziel geloeschte Mails kommen nicht wieder.

Aufruf (PYTHONPATH=src, braucht das Paket "cryptography"):
  python tests/e2e.py [--java JAVA] [--greenmail GREENMAIL.jar] -- APP-BEFEHL ...
Ohne --greenmail wird GreenMail heruntergeladen und die Pruefsumme kontrolliert.
APP-BEFEHL ist z. B. "dist/Christinas Mail-Sync.exe" oder "python -m mailsync".
"""
import argparse
import datetime
import hashlib
import email.message
import email.utils
import imaplib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

GREENMAIL_URL = ("https://repo1.maven.org/maven2/com/icegreen/greenmail-standalone/2.1.14/"
                 "greenmail-standalone-2.1.14.jar")
GREENMAIL_SHA256 = "0381392f3a44e4d8ae78051778440f58820d01acaf5757c3f43649deda8c1d23"
HOST = "127.0.0.1"
USERS = {"alt": "pw-alt 1$!", "neu": "pw-neu 2#?"}
KEYSTORE_PW = "e2e-keystore"


def make_certs(tmp):
    """Eigene Test-CA und ein Serverzertifikat fuer localhost/127.0.0.1."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mail-Sync Test-CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(hours=1)).not_valid_after(now + datetime.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(hours=1)).not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address(HOST))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_file = os.path.join(tmp, "ca.pem")
    with open(ca_file, "wb") as f:
        f.write(ca.public_bytes(serialization.Encoding.PEM))
    keystore = os.path.join(tmp, "server.p12")
    with open(keystore, "wb") as f:
        f.write(pkcs12.serialize_key_and_certificates(
            b"server", key, cert, [ca], serialization.BestAvailableEncryption(KEYSTORE_PW.encode())))
    return ca_file, keystore


def download_greenmail(tmp):
    path = os.path.join(tmp, "greenmail.jar")
    with urllib.request.urlopen(GREENMAIL_URL, timeout=120) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != GREENMAIL_SHA256:
        raise SystemExit("GreenMail: falsche Pruefsumme")
    with open(path, "wb") as f:
        f.write(data)
    return path


def free_port():
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def start_greenmail(java, jar, keystore, port, tmp):
    log = open(os.path.join(tmp, "greenmail.log"), "w")
    proc = subprocess.Popen([
        java, "-Dgreenmail.imaps.hostname=" + HOST, "-Dgreenmail.imaps.port=%d" % port, "-Dgreenmail.startup.timeout=60000",
        "-Dgreenmail.users=" + ",".join("%s:%s" % u for u in USERS.items()),
        "-Dgreenmail.tls.keystore.file=" + keystore, "-Dgreenmail.tls.keystore.password=" + KEYSTORE_PW,
        "-jar", jar], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            login("alt").logout()
            return proc
        except (OSError, imaplib.IMAP4.error):
            # Der Server nimmt schon Verbindungen an, bevor die Testkonten angelegt sind
            if proc.poll() is not None:
                break
            time.sleep(0.5)
    proc.kill()
    log.close()
    print(open(log.name).read())
    raise SystemExit("GreenMail ist nicht gestartet")


def login(user):
    from mailsync import plan
    return plan.connect(HOST, PORT, user, USERS[user])


def make_mail(subject, message_id=True):
    msg = email.message.EmailMessage()
    msg["From"] = "Schulleitung <leitung@alte-schule.example.org>"
    msg["To"] = "erika.muster@alte-schule.example.org"
    msg["Subject"] = subject
    msg["Date"] = email.utils.format_datetime(datetime.datetime(2025, 3, 14, 9, 30, tzinfo=datetime.timezone.utc))
    if message_id:
        msg["Message-ID"] = email.utils.make_msgid(domain="alte-schule.example.org")
    msg.set_content("Testmail: %s\n" % subject)
    return msg.as_bytes()


# Feste INTERNALDATE, um zu pruefen, dass das Empfangsdatum erhalten bleibt
RECEIVED = imaplib.Time2Internaldate(time.mktime((2025, 3, 14, 10, 0, 0, 0, 0, -1)))


def append(m, folder, subject, seen=False, message_id=True):
    typ, _ = m.append('"%s"' % folder, "(\\Seen)" if seen else "()", RECEIVED, make_mail(subject, message_id))
    assert typ == "OK", (folder, subject)


def contents(user):
    """{ordner: {betreff: (flags, internaldate)}} - wirft bei doppelten Betreffs."""
    from mailsync import plan
    m = login(user)
    out = {}
    try:
        for f in plan.folders(m):
            mails = {}
            typ, data = m.select(plan.quote(f), readonly=True)
            if int(data[0] or 0):
                _, data = m.fetch("1:*", "(FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                for item in data:
                    if not isinstance(item, tuple):
                        continue
                    subject = re.search(r"Subject: (.*)", item[1].decode()).group(1).strip()
                    flags = set(re.search(rb"FLAGS \(([^)]*)\)", item[0]).group(1).decode().split())
                    date = re.search(rb'INTERNALDATE "([^"]+)"', item[0]).group(1).decode()
                    assert subject not in mails, "doppelt in %s: %s" % (f, subject)
                    mails[subject] = (flags, date)
            out[f] = mails
    finally:
        m.logout()
    return out


def by_leaf(box):
    """GreenMail meldet kein NAMESPACE, daher raet imapsync Trennzeichen und Praefix
    im Ziel (z. B. "Archiv 2025" -> "INBOX/Archiv 2025"). Echte Server melden es.
    Verglichen wird deshalb der letzte Teil des Ordnernamens."""
    return {re.split(r"[./]", f)[-1]: mails for f, mails in box.items()}


def all_subjects(box):
    subjects = [s for mails in box.values() for s in mails]
    assert len(subjects) == len(set(subjects)), "Mail mehrfach im Ziel: %s" % subjects
    return set(subjects)


def run_app(app, data_dir, tmp, run):
    out = os.path.join(tmp, "result-%d.json" % run)
    env = dict(os.environ, MAILSYNC_DATA_DIR=data_dir,
               MAILSYNC_PASSWORD1=USERS["alt"], MAILSYNC_PASSWORD2=USERS["neu"])
    p = subprocess.run(app + ["--sync-headless", out], env=env, timeout=900)
    log = os.path.join(data_dir, "Logs", "letzter-lauf.txt")
    if os.path.exists(log):
        # Kein Passwort darf im Protokoll stehen
        text = open(log, encoding="utf-8", errors="replace").read()
        assert not any(pw in text for pw in USERS.values()), "Passwort im Protokoll!"
    if p.returncode != 0 or not os.path.exists(out):
        if os.path.exists(log):
            print(text)
        raise SystemExit("App-Lauf %d fehlgeschlagen (Rueckgabewert %s)" % (run, p.returncode))
    with open(out, encoding="utf-8") as f:
        result = json.load(f)
    print("Lauf %d: %s" % (run, result))
    if not (result["kind"] == "done" and not result["stopped"] and result["failed_folders"] == 0):
        if os.path.exists(log):
            print(text)
        raise SystemExit("App-Lauf %d: %s" % (run, result))
    return result


def check(name, ok):
    print(("  OK      " if ok else "  FEHLER  ") + name)
    if not ok:
        check.failed = True


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--java", default="java")
    ap.add_argument("--greenmail")
    ap.add_argument("app", nargs="+")
    args = ap.parse_args()
    check.failed = False

    tmp = tempfile.mkdtemp(prefix="mailsync-e2e-")
    ca_file, keystore = make_certs(tmp)
    os.environ["MAILSYNC_CA_FILE"] = ca_file  # fuer diesen Test und die App
    PORT = free_port()
    jar = os.path.abspath(args.greenmail) if args.greenmail else download_greenmail(tmp)
    server = start_greenmail(args.java, jar, keystore, PORT, tmp)
    try:
        m = login("alt")
        _, data = m.list('""', '""')
        d = re.search(rb'"(.)"', data[0]).group(1).decode()
        klasse, trash = "INBOX%sKlasse 7b" % d, "INBOX%sTrash" % d
        archiv, eltern = "Archiv 2025", "Elternbriefe &AMQ-"  # Elternbriefe mit grossem A-Umlaut (IMAP-UTF-7)
        for f in (klasse, trash, archiv, eltern):
            assert m.create('"%s"' % f)[0] == "OK", f
        append(m, "INBOX", "A Begruessung")
        append(m, "INBOX", "B Gelesen", seen=True)
        append(m, "INBOX", "C Konferenz")
        append(m, klasse, "D Elternabend")
        append(m, klasse, "E Ausflug")
        append(m, archiv, "G Zeugnisse")
        append(m, archiv, "H Ohne Message-ID", message_id=False)
        append(m, eltern, "I Umlaut-Ordner")
        append(m, trash, "T Papierkorb")
        m.logout()

        data_dir = os.path.join(tmp, "daten")
        os.makedirs(data_dir)
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"source_host": HOST, "source_port": PORT, "source_user": "alt",
                       "target_host": HOST, "target_port": PORT, "target_user": "neu",
                       "exclude_folders": [trash]}, f)
        app = args.app

        print("Lauf 1: alles Neue uebertragen")
        r = run_app(app, data_dir, tmp, 1)
        n = r["transferred"]
        check("Vorschau vor dem ersten Lauf mit 8 Mails (gemeldet: %s)" % r["preview"], r["preview"] == 8)
        box = contents("neu")
        check("8 Mails uebertragen (gemeldet: %d)" % n, n == 8)
        check("jede Mail genau einmal im Ziel", all_subjects(box) == {
            "A Begruessung", "B Gelesen", "C Konferenz", "D Elternabend", "E Ausflug",
            "G Zeugnisse", "H Ohne Message-ID", "I Umlaut-Ordner"})
        leaf = by_leaf(box)
        check("Ordner erhalten", set(leaf.get("INBOX", {})) == {"A Begruessung", "B Gelesen", "C Konferenz"}
              and set(leaf.get("Klasse 7b", {})) == {"D Elternabend", "E Ausflug"}
              and set(leaf.get("Archiv 2025", {})) == {"G Zeugnisse", "H Ohne Message-ID"}
              and set(leaf.get(eltern, {})) == {"I Umlaut-Ordner"})
        check("Papierkorb nicht uebertragen", "T Papierkorb" not in all_subjects(box))
        check("Gelesen-Markierung erhalten", "\\Seen" in box["INBOX"]["B Gelesen"][0]
              and "\\Seen" not in box["INBOX"]["A Begruessung"][0])
        check("Empfangsdatum erhalten", box["INBOX"]["B Gelesen"][1] == contents("alt")["INBOX"]["B Gelesen"][1])

        print("Lauf 2: nichts Neues")
        r = run_app(app, data_dir, tmp, 2)
        n = r["transferred"]
        check("keine Vorschau mehr beim zweiten Lauf", r["preview"] is None)
        check("0 Mails uebertragen (gemeldet: %d)" % n, n == 0)
        log = open(os.path.join(data_dir, "Logs", "letzter-lauf.txt"), encoding="utf-8").read()
        check("keine Mail mehr als neu erkannt", "Neue Mails: 0 " in log)
        check("Ziel unveraendert", contents("neu") == box)

        print("Lauf 3: im Ziel geloescht, in der Quelle verschoben, eine neue Mail")
        m = login("neu")
        m.select("INBOX")
        _, data = m.search(None, "SUBJECT", '"A Begruessung"')
        m.store(data[0].decode(), "+FLAGS", "\\Deleted")
        m.expunge()
        m.logout()
        m = login("alt")
        m.select('"%s"' % klasse)
        _, data = m.search(None, "SUBJECT", '"D Elternabend"')
        m.copy(data[0].decode(), '"%s"' % archiv)
        m.store(data[0].decode(), "+FLAGS", "\\Deleted")
        m.expunge()
        append(m, "INBOX", "F Neu")
        m.logout()
        r = run_app(app, data_dir, tmp, 3)
        n = r["transferred"]
        check("Fortschritt kennt die Gesamtzahl (gemeldet: %s)" % r["planned"], r["planned"] == 1)
        box = contents("neu")
        subjects = all_subjects(box)
        check("1 Mail uebertragen (gemeldet: %d)" % n, n == 1)
        check("neue Mail angekommen", "F Neu" in box.get("INBOX", {}))
        check("im Ziel geloeschte Mail kommt nicht wieder", "A Begruessung" not in subjects)
        check("verschobene Mail nicht doppelt", "D Elternabend" in subjects)
        check("insgesamt 8 Mails im Ziel", subjects == set(
            ["B Gelesen", "C Konferenz", "D Elternabend", "E Ausflug", "F Neu",
             "G Zeugnisse", "H Ohne Message-ID", "I Umlaut-Ordner"]))
    finally:
        server.kill()
        server.wait()
    if check.failed:
        raise SystemExit("Ende-zu-Ende-Test fehlgeschlagen (Dateien in %s)" % tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Ende-zu-Ende-Test bestanden")


if __name__ == "__main__":
    main()
