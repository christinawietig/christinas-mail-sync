"""Einrichtungscode: die Einstellungen in einem kurzen Text zum Einfuegen, z. B. "MS1-8D2KQ-...".

Enthalten: Server, Ports, Benutzernamen, ausgeschlossene Ordner, Benutzernamen-Regel.
Nie enthalten: Passwoerter.

Robust gegen Tipp- und Kopierfehler:
- Crockford-Base32: Gross-/Kleinschreibung egal, O wird als 0 und I/L als 1 gelesen.
- Leerzeichen, Bindestriche und Zeilenumbrueche werden ueberall ignoriert.
- CRC-32-Pruefsumme: vertippte oder abgeschnittene Codes werden erkannt.
"""
import re
import zlib

PREFIX = "MS1"
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_VALUE = {c: i for i, c in enumerate(ALPHABET)}
_VALUE.update({"O": 0, "I": 1, "L": 1})
DEFAULT_PORT = 993
# Benutzernamen-Regel als ein Zeichen im Code
_RULES = {"localpart": "l", "same": "s", "": ""}


class CodeError(ValueError):
    pass


def _b32encode(data):
    bits = "".join("{:08b}".format(b) for b in data)
    bits += "0" * (-len(bits) % 5)
    return "".join(ALPHABET[int(bits[i:i + 5], 2)] for i in range(0, len(bits), 5))


def _b32decode(text):
    try:
        bits = "".join("{:05b}".format(_VALUE[c]) for c in text)
    except KeyError as e:
        raise CodeError("Der Code enthält ein ungültiges Zeichen (%s)." % e.args[0])
    extra = len(bits) % 8
    if extra >= 5 or "1" in bits[len(bits) - extra:]:
        # Fuellbits muessen 0 sein, sonst bliebe ein Tippfehler im letzten Zeichen unbemerkt
        raise CodeError("Der Code ist unvollständig oder vertippt. Bitte nochmal komplett kopieren.")
    bits = bits[:len(bits) - extra]
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def encode(source_host, source_port, target_host, target_port, target_user_rule, exclude_folders,
           source_user="", target_user=""):
    """exclude_folders: Ordnernamen des alten Postfachs, die nie uebertragen werden.
    Benutzernamen sind optional (leer = nicht im Code)."""
    fields = [source_host, "" if source_port == DEFAULT_PORT else str(source_port),
              target_host, "" if target_port == DEFAULT_PORT else str(target_port),
              _RULES[target_user_rule], source_user, target_user] + list(exclude_folders)
    if any("\n" in f for f in fields):
        raise ValueError("Zeilenumbrueche sind in den Feldern nicht erlaubt")
    raw = "\n".join(fields).encode("utf-8")
    packed = zlib.compress(raw, 9)[2:-4]  # reines Deflate ohne Kopf, wenn kuerzer
    body = (b"\x01" + packed) if len(packed) < len(raw) else (b"\x00" + raw)
    data = body + zlib.crc32(body).to_bytes(4, "big")
    text = _b32encode(data)
    return "-".join([PREFIX] + [text[i:i + 5] for i in range(0, len(text), 5)])


def derive_rule(source_user, target_user):
    """Benutzernamen-Regel aus einem Beispiel ableiten (fuer Codes ohne Regel)."""
    if source_user and target_user:
        if target_user == source_user:
            return "same"
        if target_user == source_user.split("@", 1)[0]:
            return "localpart"
    return ""


def normalize(code):
    return re.sub(r"[\s\-]+", "", code).upper()


def decode(code):
    """Liefert ein dict mit den Feldern von config.Settings. Fehlende Benutzernamen sind leer."""
    text = normalize(code)
    if not text:
        raise CodeError("Bitte den Einrichtungscode einfügen.")
    if not text.startswith(PREFIX):
        raise CodeError("Das ist kein Einrichtungscode (er beginnt mit %s-)." % PREFIX)
    data = _b32decode(text[len(PREFIX):])
    if len(data) < 6 or zlib.crc32(data[:-4]).to_bytes(4, "big") != data[-4:]:
        raise CodeError("Der Code ist unvollständig oder vertippt. Bitte nochmal komplett kopieren.")
    flag, payload = data[0], data[1:-4]
    try:
        raw = zlib.decompress(payload, -15) if flag == 1 else payload
        fields = raw.decode("utf-8").split("\n")
        src, src_port, dst, dst_port, rule, src_user, dst_user = fields[:7]
        rules = {v: k for k, v in _RULES.items()}
        if not src or not dst:
            raise ValueError()
        return {
            "source_host": src,
            "source_port": int(src_port or DEFAULT_PORT),
            "target_host": dst,
            "target_port": int(dst_port or DEFAULT_PORT),
            "target_user_rule": rules[rule],
            "exclude_folders": fields[7:],
            "source_user": src_user,
            "target_user": dst_user,
        }
    except (zlib.error, UnicodeDecodeError, ValueError, KeyError):
        raise CodeError("Dieser Code stammt von einer anderen Version und ist hier nicht lesbar.")
