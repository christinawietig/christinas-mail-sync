#!/bin/bash
# Macht aus dist/Christinas Mail-Sync.app die DMG zum Reinziehen in "Programme":
# dist/Christinas-Mail-Sync.dmg. Vorher: pyinstaller mailsync.spec (signiert die App).
#
# Mit Apple-Zugang (Umgebungsvariablen) wird notarisiert, sonst nur gebaut:
#   MACOS_SIGN_IDENTITY  "Developer ID Application: ..." (signiert die DMG)
#   NOTARY_KEY           Pfad zum API-Schluessel (.p8)
#   NOTARY_KEY_ID, NOTARY_ISSUER
set -euo pipefail
cd "$(dirname "$0")/.."

APP="dist/Christinas Mail-Sync.app"
DMG="dist/Christinas-Mail-Sync.dmg"

notarize() {
  # notarytool meldet "Invalid" nicht ueber den Rueckgabewert, daher Status pruefen
  local out id
  out=$(xcrun notarytool submit "$1" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" \
        --issuer "$NOTARY_ISSUER" --wait --output-format json)
  echo "$out"
  id=$(echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  if ! echo "$out" | grep -q '"status" *: *"Accepted"'; then
    xcrun notarytool log "$id" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER"
    echo "Notarisierung abgelehnt: $1" >&2
    exit 1
  fi
}

if [ -n "${NOTARY_KEY:-}" ]; then
  echo "== App notarisieren"
  ditto -c -k --keepParent "$APP" dist/notarize-app.zip
  notarize dist/notarize-app.zip
  rm dist/notarize-app.zip
  # Ticket in die App heften: Sie oeffnet sich dann auch ohne Internet ohne Warnung
  xcrun stapler staple "$APP"
fi

echo "== DMG bauen"
rm -f "$DMG"
dmgbuild -s installer/dmg-settings.py "Christinas Mail-Sync" "$DMG"

if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
  codesign --force -s "$MACOS_SIGN_IDENTITY" --timestamp "$DMG"
fi
if [ -n "${NOTARY_KEY:-}" ]; then
  echo "== DMG notarisieren"
  notarize "$DMG"
  xcrun stapler staple "$DMG"
  echo "== Pruefen wie Gatekeeper"
  spctl -a -vv -t open --context context:primary-signature "$DMG"
  spctl -a -vv -t exec "$APP"
fi
echo "Fertig: $DMG"
