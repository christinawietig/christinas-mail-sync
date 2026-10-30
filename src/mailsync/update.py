"""Gibt es eine neuere Version? Fragt die oeffentliche Release-Seite auf GitHub.

Verschickt werden keine Daten: Die App ruft nur .../releases/latest auf, GitHub leitet
auf das neueste Release weiter (.../releases/tag/v1.2.3), daraus kommt die Versionsnummer.
Bewusst nicht die GitHub-API: Die laesst ohne Anmeldung nur wenige Abrufe je Stunde zu.
"""
import re
import ssl
import urllib.request

from . import __version__, config

REPO_URL = "https://github.com/christinawietig/christinas-mail-sync"
LATEST_URL = REPO_URL + "/releases/latest"
TAG_RE = re.compile(r"/releases/tag/v?(\d+(?:\.\d+)*)$")


def parse(version):
    """'1.0.10' -> (1, 0, 10); None, wenn es keine Versionsnummer ist."""
    if not re.fullmatch(r"\d+(\.\d+)*", version or ""):
        return None
    parts = [int(p) for p in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(latest, current=__version__):
    a, b = parse(latest), parse(current)
    return a is not None and b is not None and a > b


def latest_version(timeout=10):
    """Versionsnummer des neuesten Releases. Wirft bei Netzfehlern."""
    ctx = ssl.create_default_context(cafile=config.ca_file())
    req = urllib.request.Request(LATEST_URL, method="HEAD", headers={"User-Agent": "Christinas-Mail-Sync"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        url = r.geturl()
    m = TAG_RE.search(url)
    if not m:
        raise ValueError("Unerwartete Adresse: " + url)
    return m.group(1)


def check():
    """Neuere Version oder None. Fehler (offline, GitHub nicht erreichbar) zaehlen als None."""
    try:
        latest = latest_version()
    except Exception:
        return None
    return latest if is_newer(latest) else None
