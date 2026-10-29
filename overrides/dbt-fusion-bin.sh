# shellcheck shell=bash disable=SC2154
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is set.
# upstream tag 2.0.0-beta.12 is stored in _pkgver, pkgver is derived from it
_pkgver=$(sed -E 's/\.([a-z]+)/-\1/' <<< "$newver")
sed -i "s/^_pkgver=.*/_pkgver=$_pkgver/; s/^pkgver=.*/pkgver=\"\${_pkgver\/-\/.}\"/" PKGBUILD
