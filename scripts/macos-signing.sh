#!/bin/bash
# Signierzertifikat und Apple-API-Schluessel auf dem GitHub-Rechner einrichten bzw. entfernen.
#
#   macos-signing.sh setup    braucht P12 (base64), P12_PASSWORD, P8; schreibt
#                             MACOS_SIGN_IDENTITY und NOTARY_KEY nach $GITHUB_ENV
#   macos-signing.sh cleanup
#
# Gibt nie geheime Werte aus, nur Anzahl und oeffentlichen Namen des Zertifikats.
set -euo pipefail

KC="$RUNNER_TEMP/signing.keychain-db"

case "${1:-}" in
  setup)
    KC_PW=$(openssl rand -hex 24)
    security create-keychain -p "$KC_PW" "$KC"
    security set-keychain-settings -lut 21600 "$KC"
    security unlock-keychain -p "$KC_PW" "$KC"
    printf '%s' "$P12" | base64 --decode > "$RUNNER_TEMP/cert.p12"
    # "security import" liest die von der Schluesselbundverwaltung exportierte .p12 hier
    # nicht ("MAC verification failed"). Mit OpenSSL lesen (-legacy: der Schluesselbund
    # verschluesselt mit RC2-40) und mit 3DES/SHA-1 neu verpacken.
    OPENSSL="$(brew --prefix openssl@3)/bin/openssl"
    PEM="$RUNNER_TEMP/cert.pem"
    (umask 077; "$OPENSSL" pkcs12 -legacy -in "$RUNNER_TEMP/cert.p12" -nodes -passin env:P12_PASSWORD -out "$PEM")
    echo "In der .p12: $(grep -c 'BEGIN CERTIFICATE' "$PEM" || true) Zertifikat(e), $(grep -c 'BEGIN .*PRIVATE KEY' "$PEM" || true) privater Schluessel"
    grep -q 'BEGIN CERTIFICATE' "$PEM" && "$OPENSSL" x509 -in "$PEM" -noout -subject -enddate
    "$OPENSSL" pkcs12 -export -in "$PEM" -passout env:P12_PASSWORD -out "$RUNNER_TEMP/cert-classic.p12" \
      -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES -macalg sha1
    rm -f "$PEM"
    security import "$RUNNER_TEMP/cert-classic.p12" -k "$KC" -P "$P12_PASSWORD" -T /usr/bin/codesign
    rm -f "$RUNNER_TEMP/cert.p12" "$RUNNER_TEMP/cert-classic.p12"
    security set-key-partition-list -S apple-tool:,apple: -s -k "$KC_PW" "$KC" >/dev/null
    security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')
    ID=$(security find-identity -v -p codesigning "$KC" | grep -o '"Developer ID Application: [^"]*"' | head -1 | tr -d '"')
    if [ -z "$ID" ]; then echo "Kein Developer-ID-Zertifikat gefunden" >&2; exit 1; fi
    echo "Signiere mit: $ID"
    echo "MACOS_SIGN_IDENTITY=$ID" >> "$GITHUB_ENV"
    (umask 077; printf '%s\n' "$P8" > "$RUNNER_TEMP/notary.p8")
    echo "NOTARY_KEY=$RUNNER_TEMP/notary.p8" >> "$GITHUB_ENV"
    ;;
  cleanup)
    security delete-keychain "$KC" 2>/dev/null || true
    rm -f "$RUNNER_TEMP/notary.p8" "$RUNNER_TEMP/cert.p12" "$RUNNER_TEMP/cert-classic.p12" "$RUNNER_TEMP/cert.pem"
    ;;
  *)
    echo "Aufruf: $0 setup|cleanup" >&2
    exit 2
    ;;
esac
