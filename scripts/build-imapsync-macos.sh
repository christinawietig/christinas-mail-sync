#!/bin/bash
# Baut imapsync fuer Macs mit Apple-Chip (arm64): das Skript und alle noetigen
# Perl-Module als einzelne Dateien, gestartet mit dem Perl von macOS (/usr/bin/perl).
# Ergebnis: vendor/imapsync-macos/ (imapsync + lib/). Beim Nutzer wird weder Homebrew
# noch eine Perl-Installation gebraucht. Einzelne Dateien statt einer gepackten Datei,
# weil Apple nur so jede Datei signieren und die App notarisieren kann.
#
# Voraussetzungen auf dem Build-Rechner: Xcode Command Line Tools, Homebrew mit openssl@3.
# OpenSSL wird statisch eingebaut, damit das Ergebnis nicht von Homebrew abhaengt.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/imapsync-version.sh

OUT="$(pwd)/vendor/imapsync-macos"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PERL=/usr/bin/perl
export ARCHFLAGS="-arch arm64"
# Auch auf aelteren macOS-Versionen lauffaehig (wie LSMinimumSystemVersion in mailsync.spec)
export MACOSX_DEPLOYMENT_TARGET=12.0

echo "== imapsync $IMAPSYNC_VERSION laden"
curl -fsSL -o "$WORK/imapsync.zip" "$IMAPSYNC_URL"
echo "$IMAPSYNC_SHA256  $WORK/imapsync.zip" | shasum -a 256 -c -
unzip -q -j "$WORK/imapsync.zip" "imapsync_${IMAPSYNC_VERSION}/Cook/imapsync" -d "$WORK"

echo "== OpenSSL (nur statische Bibliotheken)"
SSL="$WORK/openssl"
mkdir -p "$SSL/lib"
cp -R "$(brew --prefix openssl@3)/include" "$SSL/"
cp "$(brew --prefix openssl@3)"/lib/lib{ssl,crypto}.a "$SSL/lib/"

echo "== Perl-Module"
# cpanm und alle Module mit fester Version: Jeder Build eines Tags enthaelt denselben Code
curl -fsSL -o "$WORK/cpanm" "https://raw.githubusercontent.com/miyagawa/cpanminus/$CPANM_VERSION/cpanm"
echo "$CPANM_SHA256  $WORK/cpanm" | shasum -a 256 -c -
LOCAL="$WORK/local"
export PERL5LIB="$LOCAL/lib/perl5" PATH="$LOCAL/bin:$PATH"
cpanm() { "$PERL" "$WORK/cpanm" -q --notest -l "$LOCAL" "$@"; }
# Eigenes Net::SSLeay (statisch gegen OpenSSL 3) statt Apples Version gegen /usr/lib/libssl
OPENSSL_PREFIX="$SSL" cpanm --reinstall Net::SSLeay@1.96 IO::Socket::SSL@2.099
cpanm Encode::IMAPUTF7@1.07 IO::Tee@0.65 Mail::IMAPClient@3.43 Unicode::String@2.10 Readonly@2.05 \
      Sys::MemInfo@0.99 File::Tail@1.3 File::Copy::Recursive@0.45 Digest::HMAC_SHA1@1.05 \
      Regexp::Common@2024080801 Term::ReadKey@2.38

BUNDLE="$LOCAL/lib/perl5/darwin-thread-multi-2level/auto/Net/SSLeay/SSLeay.bundle"
[ -f "$BUNDLE" ] || { echo "Net::SSLeay nicht gefunden: $BUNDLE" >&2; exit 1; }
LINKS=$(otool -L "$BUNDLE")
if grep -q libssl <<< "$LINKS"; then
  echo "Net::SSLeay haengt noch an einer libssl-Bibliothek - abgebrochen." >&2
  exit 1
fi

echo "== Zusammenstellen"
STAGE="$WORK/imapsync-macos"
mkdir -p "$STAGE"
cp "$WORK/imapsync" "$STAGE/imapsync"
cp -R "$LOCAL/lib/perl5" "$STAGE/lib"
# Nur was zur Laufzeit gebraucht wird
find "$STAGE/lib" \( -name '*.pod' -o -name '.packlist' -o -name 'perllocal.pod' \) -delete
# Ohne Homebrew und ohne fremde Perl-Einstellungen pruefen
env -i HOME="$WORK" /usr/bin/perl -I "$STAGE/lib" -I "$STAGE/lib/darwin-thread-multi-2level" \
  "$STAGE/imapsync" --version
rm -rf "$OUT"
mkdir -p vendor
mv "$STAGE" "$OUT"
echo "Gebaut: $OUT"
