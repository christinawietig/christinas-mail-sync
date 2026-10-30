# Laedt das offizielle imapsync-Paket, prueft die Pruefsumme und legt
# imapsync.exe nach vendor\. Version und Pruefsumme stehen in imapsync-version.sh.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $PSScriptRoot "imapsync-version.sh") | Where-Object { $_ -match '^IMAPSYNC_(VERSION|SHA256)=' }
$version = ($cfg | Where-Object { $_ -match 'VERSION' }) -replace '.*=', ''
$sha256 = ($cfg | Where-Object { $_ -match 'SHA256' }) -replace '.*=', ''
# Das Archiv old_releases/ behaelt jede Version; dist/ nur die neueste
$url = "https://imapsync.lamiral.info/dist/old_releases/$version/imapsync_$version.zip"

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("imapsync-" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
try {
    $zip = Join-Path $tmp "imapsync.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $sha256) { throw "Pruefsumme falsch: $actual" }
    Expand-Archive $zip -DestinationPath $tmp
    New-Item -ItemType Directory -Force (Join-Path $root "vendor") | Out-Null
    Copy-Item (Join-Path $tmp "imapsync_$version\imapsync.exe") (Join-Path $root "vendor\imapsync.exe")
    Write-Host "imapsync $version -> vendor\imapsync.exe"
} finally {
    Remove-Item -Recurse -Force $tmp
}
