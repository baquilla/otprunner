#!/bin/sh
# Builds the archive for the KDE Store entry: build/kde-store/otprunner-kde-store.tar.gz
# The entry installs nothing; see packaging/kde-store/README.
set -eu
cd "$(dirname "$0")/.."
src=packaging/kde-store
out=build/kde-store
mkdir -p "$out"
# Flat archive: KRunner's plugin installer looks for install*/uninstall* next to the files.
tar -C "$src" --owner=0 --group=0 --numeric-owner --mtime=@0 --sort=name \
    -czf "$out/otprunner-kde-store.tar.gz" README install.sh uninstall.sh
echo "$out/otprunner-kde-store.tar.gz"
