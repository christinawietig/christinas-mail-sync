# Welche imapsync-Version eingebaut wird. Das offizielle Paket enthaelt
# imapsync.exe (Windows) und den Quelltext (Cook/imapsync, fuer den Mac-Build).
IMAPSYNC_VERSION=2.314
# Das Archiv old_releases/ behaelt jede Version; dist/ nur die neueste
IMAPSYNC_URL="https://imapsync.lamiral.info/dist/old_releases/${IMAPSYNC_VERSION}/imapsync_${IMAPSYNC_VERSION}.zip"
IMAPSYNC_SHA256=61972bf94532bf186dd6d6ee54a4c70bb7ab3bdb79f324321cd742fd50953a0c
# cpanm (installiert die Perl-Module fuer den Mac-Build)
CPANM_VERSION=1.7049
CPANM_SHA256=137e8c5856e09867f6d7631d6d67a5e7778166962e29830c573cbbbab6ed2e21
