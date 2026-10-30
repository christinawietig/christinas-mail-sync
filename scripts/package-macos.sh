#!/bin/bash
# Verpackt die App fuer macOS als DMG zum Reinziehen in "Programme".
# Die Notarisierung ist in zwei Schritte geteilt, damit ein langsames Apple den Build nicht
# aufhaelt (die erste Notarisierung eines neuen Accounts kann Tage dauern):
#
#   package-macos.sh dmg      Unsignierter Build: nur dist/Christinas-Mail-Sync.dmg bauen.
#   package-macos.sh submit   Signierte App -> DMG bauen, signieren, bei Apple einreichen (Apple
#                             prueft dabei auch die App darin), ohne zu warten. Ergebnis in
#                             dist/signed/: die DMG und die Einreichungs-ID. Der Build sichert sie.
#   package-macos.sh finish   Mit dist/signed/: Status bei Apple pruefen. Bei "Accepted" das Ticket
#                             an die DMG heften -> dist/Christinas-Mail-Sync.dmg.
#                             Schreibt nach $GITHUB_OUTPUT: result=accepted|pending|invalid.
#                             Rueckgabe 0 bei accepted/pending, 1 bei invalid.
#   package-macos.sh history  Alle Einreichungen bei Apple mit Status anzeigen.
#
# Umgebungsvariablen:
#   MACOS_SIGN_IDENTITY  "Developer ID Application: ..." (submit)
#   MACOS_TEAM_ID        erwartete Team-ID der Signatur (finish)
#   NOTARY_KEY           Pfad zum API-Schluessel (.p8); NOTARY_KEY_ID, NOTARY_ISSUER
#   NOTARY_WAIT_MINUTES  wie lange finish auf Apple wartet (Standard 0: einmal nachsehen)
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="Christinas Mail-Sync"
APP="dist/$NAME.app"
DMG="dist/Christinas-Mail-Sync.dmg"
SIGNED="dist/signed"
SIGNED_DMG="$SIGNED/Christinas-Mail-Sync.dmg"
NOTARY_ID="$SIGNED/notary-id.txt"

output() { if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >> "$GITHUB_OUTPUT"; fi; }

check_notary_env() {
  : "${NOTARY_KEY:?NOTARY_KEY fehlt}"
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
    : "${MACOS_SIGN_IDENTITY:?MACOS_SIGN_IDENTITY fehlt}"
    build_dmg
    codesign --force -s "$MACOS_SIGN_IDENTITY" --timestamp "$DMG"
    rm -rf "$SIGNED"; mkdir -p "$SIGNED"
    mv "$DMG" "$SIGNED_DMG"
    echo "== Bei Apple einreichen"
    out=$(nt submit "$SIGNED_DMG" --output-format json)
    echo "$out"
    echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' > "$NOTARY_ID"
    echo "Eingereicht: $(cat "$NOTARY_ID")"
    ;;

  finish)
    check_notary_env
    : "${MACOS_TEAM_ID:?MACOS_TEAM_ID fehlt}"
    # Nur eine DMG mit unserer Signatur weiterverarbeiten
    codesign -v "$SIGNED_DMG"
    sig=$(codesign -dv "$SIGNED_DMG" 2>&1)
    grep -qx "TeamIdentifier=$MACOS_TEAM_ID" <<< "$sig" \
      || { echo "DMG ist nicht vom Team $MACOS_TEAM_ID signiert" >&2; exit 1; }
    id=$(tr -d '[:space:]' < "$NOTARY_ID")
    [[ "$id" =~ ^[0-9a-f-]{36}$ ]] || { echo "Ungueltige Einreichungs-ID" >&2; exit 1; }
    echo "== Status bei Apple"
    status=$(wait_status "$id" "${NOTARY_WAIT_MINUTES:-0}")
    case "$status" in
      Accepted) ;;
      Invalid|Rejected)
        nt log "$id" || true
        echo "Apple hat die DMG abgelehnt ($status), siehe Protokoll oben." >&2
        output result=invalid
        exit 1
        ;;
      *)
        echo "Apple prueft noch ($status). Der naechste Lauf fragt wieder nach."
        output result=pending
        exit 0
        ;;
    esac
    cp "$SIGNED_DMG" "$DMG"
    # Ticket anheften: Die DMG oeffnet sich dann auch ohne Internet ohne Warnung
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
    echo "== Pruefen wie Gatekeeper"
    spctl -a -vv -t open --context context:primary-signature "$DMG"
    MNT=$(mktemp -d)
    hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null
    rc=0; spctl -a -vv -t exec "$MNT/$NAME.app" || rc=$?
    hdiutil detach "$MNT" >/dev/null || true
    [ "$rc" -eq 0 ] || exit 1
    output result=accepted
    ;;

  history)
    check_notary_env
    nt history
    ;;

  *)
    echo "Aufruf: $0 dmg|submit|finish|history" >&2
    exit 2
    ;;
esac
echo "Fertig ($1)"
