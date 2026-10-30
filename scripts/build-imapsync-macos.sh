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
curl -fsSL -o "$WORK/cpanm" https://cpanmin.us
LOCAL="$WORK/local"
export PERL5LIB="$LOCAL/lib/perl5" PATH="$LOCAL/bin:$PATH"
cpanm() { "$PERL" "$WORK/cpanm" -q --notest -l "$LOCAL" "$@"; }
# Eigenes Net::SSLeay (statisch gegen OpenSSL 3) statt Apples Version gegen /usr/lib/libssl
OPENSSL_PREFIX="$SSL" cpanm --reinstall Net::SSLeay IO::Socket::SSL
cpanm Encode::IMAPUTF7 IO::Tee Mail::IMAPClient Unicode::String Readonly Sys::MemInfo \
      File::Tail File::Copy::Recursive Digest::HMAC_SHA1 Regexp::Common Term::ReadKey

if otool -L "$LOCAL"/lib/perl5/darwin-thread-multi-2level/auto/Net/SSLeay/SSLeay.bundle | grep -q libssl; then
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
