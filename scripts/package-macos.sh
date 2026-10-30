#!/bin/bash
# Verpackt die App fuer macOS. Drei Schritte, damit ein langsames Apple den Build nicht
# aufhaelt (die erste Notarisierung eines neuen Accounts kann Tage dauern):
#
#   package-macos.sh dmg      Unsignierter Build: nur dist/Christinas-Mail-Sync.dmg bauen.
#   package-macos.sh submit   Signierte App zippen und bei Apple einreichen, ohne zu warten.
#                             Ergebnis in dist/signed/: App-Zip und Einreichungs-ID. Diese
#                             Dateien sichert der Build; die App darin ist genau die eingereichte.
#   package-macos.sh finish   Mit dist/signed/: Status bei Apple pruefen. Bei "Accepted" Ticket
#                             an die App heften, DMG bauen, signieren, notarisieren, heften.
#                             Noch in Pruefung: "pending=true" nach $GITHUB_OUTPUT, Rueckgabe 0.
#
# Umgebungsvariablen fuer submit/finish:
#   MACOS_SIGN_IDENTITY  "Developer ID Application: ..."
#   NOTARY_KEY           Pfad zum API-Schluessel (.p8)
#   NOTARY_KEY_ID, NOTARY_ISSUER
#   NOTARY_WAIT_MINUTES  wie lange finish auf die App-Freigabe wartet (Standard 20)
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="Christinas Mail-Sync"
APP="dist/$NAME.app"
DMG="dist/Christinas-Mail-Sync.dmg"
SIGNED="dist/signed"
APP_ZIP="$SIGNED/Christinas-Mail-Sync-app.zip"
APP_ID="$SIGNED/notary-app-id.txt"

check_notary_env() {
  : "${NOTARY_KEY:?NOTARY_KEY fehlt}" "${MACOS_SIGN_IDENTITY:?MACOS_SIGN_IDENTITY fehlt}"
  # Leerzeichen/Zeilenumbrueche aus kopierten Werten entfernen
  NOTARY_KEY_ID=$(printf '%s' "${NOTARY_KEY_ID:-}" | tr -d '[:space:]')
  NOTARY_ISSUER=$(printf '%s' "${NOTARY_ISSUER:-}" | tr -d '[:space:]')
  if ! [[ "$NOTARY_KEY_ID" =~ ^[A-Z0-9]{10}$ ]]; then
    echo "NOTARY_KEY_ID ist keine Key ID (10 Zeichen, wie im Dateinamen AuthKey_XXXXXXXXXX.p8)" >&2
    exit 1
  fi
  if ! [[ "$NOTARY_ISSUER" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
    echo "NOTARY_ISSUER_ID ist keine Issuer ID (Form xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx," >&2
    echo "steht in App Store Connect oben auf der Seite der Teamschluessel)" >&2
    exit 1
  fi
}

nt() { xcrun notarytool "$@" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER"; }

submit_file() {
  # Gibt die Einreichungs-ID aus
  local out
  out=$(nt submit "$1" --output-format json)
  echo "$out" >&2
  echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

# Status abfragen, bis Accepted/Invalid oder die Wartezeit um ist. Netzaussetzer
# zaehlen als "?" und es wird weiter gefragt. Ausgabe: der letzte Status.
wait_status() {
  local id=$1 minutes=$2 status deadline
  deadline=$(( $(date +%s) + minutes * 60 ))
  while :; do
    status=$(nt info "$id" --output-format json 2>/dev/null \
             | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null || echo "?")
    echo "$(date -u +%H:%M) $id: $status" >&2
    case "$status" in
      Accepted|Invalid|Rejected) echo "$status"; return ;;
    esac
    if [ "$(date +%s)" -ge "$deadline" ]; then echo "$status"; return; fi
    sleep 60
  done
}

fail_with_log() {
  nt log "$1" || true
  echo "Notarisierung abgelehnt: $2" >&2
  exit 1
}

build_dmg() {
  rm -f "$DMG"
  dmgbuild -s installer/dmg-settings.py "$NAME" "$DMG"
}

case "${1:-}" in
  dmg)
    build_dmg
    ;;

  submit)
    check_notary_env
    rm -rf "$SIGNED"; mkdir -p "$SIGNED"
    ditto -c -k --keepParent "$APP" "$APP_ZIP"
    echo "== App bei Apple einreichen"
    submit_file "$APP_ZIP" > "$APP_ID"
    echo "Eingereicht: $(cat "$APP_ID")"
    ;;

  finish)
    check_notary_env
    id=$(tr -d '[:space:]' < "$APP_ID")
    echo "== Status der App bei Apple"
    status=$(wait_status "$id" "${NOTARY_WAIT_MINUTES:-20}")
    case "$status" in
      Accepted) ;;
      Invalid|Rejected) fail_with_log "$id" "$APP_ZIP" ;;
      *)
        echo "Apple prueft noch ($status). Spaeter erneut versuchen."
        [ -n "${GITHUB_OUTPUT:-}" ] && echo "pending=true" >> "$GITHUB_OUTPUT"
        exit 0
        ;;
    esac
    rm -rf "$APP"
    ditto -x -k "$APP_ZIP" dist
    # Nur unsere eigene, unveraenderte App weiterverarbeiten
    codesign -v --strict --deep "$APP"
    sig=$(codesign -dvv "$APP" 2>&1)
    grep -qF "Authority=$MACOS_SIGN_IDENTITY" <<< "$sig" \
      || { echo "App ist nicht mit $MACOS_SIGN_IDENTITY signiert" >&2; exit 1; }
    # Ticket in die App heften: Sie oeffnet sich dann auch ohne Internet ohne Warnung
    xcrun stapler staple "$APP"

    echo "== DMG bauen"
    build_dmg
    codesign --force -s "$MACOS_SIGN_IDENTITY" --timestamp "$DMG"
    echo "== DMG notarisieren"
    dmg_id=$(submit_file "$DMG")
    status=$(wait_status "$dmg_id" "${NOTARY_DMG_WAIT_MINUTES:-240}")
    [ "$status" = Accepted ] || fail_with_log "$dmg_id" "$DMG ($status)"
    xcrun stapler staple "$DMG"
    echo "== Pruefen wie Gatekeeper"
    spctl -a -vv -t open --context context:primary-signature "$DMG"
    spctl -a -vv -t exec "$APP"
    [ -n "${GITHUB_OUTPUT:-}" ] && echo "pending=false" >> "$GITHUB_OUTPUT"
    ;;

  *)
    echo "Aufruf: $0 dmg|submit|finish" >&2
    exit 2
    ;;
esac
echo "Fertig ($1)"
