# shellcheck shell=bash disable=SC2154
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is set.
# The release zip is named CyberChef_<commit>.zip, so look up the asset name.
asset=$(curl -fsS ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
  "https://api.github.com/repos/gchq/CyberChef/releases/tags/v$newver" |
  jq -r '.assets[].name | select(test("^CyberChef_[0-9a-f]+\\.zip$"))')
sed -i "s/CyberChef_[0-9a-f]*\.zip/$asset/" PKGBUILD
