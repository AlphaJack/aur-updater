# shellcheck shell=bash disable=SC2154,SC2034
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is the major (e.g. 20.0) or, on rebuilds, the full version
# odoo_$_major.latest.tar.gz changes every night, keep its checksum skipped
skip_updpkgsums=1
# a rebuild passes the full version, e.g. 20.0.20261029
major=$(cut -d. -f1-2 <<< "$newver")
nightly=$(curl -fsS "https://nightly.odoo.com/$major/nightly/src/" |
  grep -oP "odoo_\K${major//./\\.}\.\d{8}(?=\.tar\.gz)" | sort | tail -1)
sed -i "s/^_major=.*/_major=$major/; s/^pkgver=.*/pkgver=$nightly/" PKGBUILD
