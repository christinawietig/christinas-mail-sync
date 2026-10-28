"""Passwoerter im Schluesselbund des Systems.

macOS: Schluesselbundverwaltung, Windows: Anmeldeinformationsverwaltung.
Passwoerter werden nie in Dateien im Datenordner gespeichert und nie ausgegeben.
"""
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from . import APP_NAME


def _key(host, user):
    return "%s@%s" % (user, host)


def get_password(host, user):
    try:
        return keyring.get_password(APP_NAME, _key(host, user))
    except KeyringError:
        return None


def set_password(host, user, password):
    keyring.set_password(APP_NAME, _key(host, user), password)


def delete_password(host, user):
    try:
        keyring.delete_password(APP_NAME, _key(host, user))
    except (PasswordDeleteError, KeyringError):
        pass
