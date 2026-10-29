# shellcheck shell=bash disable=SC2154,SC2034
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is the major, e.g. 19.0
# odoo_$_major.latest.tar.gz changes every night, keep its checksum skipped
skip_updpkgsums=1
nightly=$(curl -fsS "https://nightly.odoo.com/$newver/nightly/src/" |
  grep -oP "odoo_\K${newver//./\\.}\.\d{8}(?=\.tar\.gz)" | sort | tail -1)
sed -i "s/^_major=.*/_major=$newver/; s/^pkgver=.*/pkgver=$nightly/" PKGBUILD
