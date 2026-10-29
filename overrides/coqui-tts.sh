# shellcheck shell=bash disable=SC2154
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is set.
# package() installs a pinned version from PyPI
sed -i "s/coqui-tts==[^']*/coqui-tts==$newver/" PKGBUILD
