# shellcheck shell=bash disable=SC2154
# Sourced by update_packages.sh inside the package dir, after pkgver bump. $newver is set.
# The release tag also embeds the Metabase and JDBC versions, e.g. 1.1.19-metabase-v0.61.1-teradata-jdbc-20.00
tag=$(curl -fsS "https://api.github.com/repos/swisscom-bigdata/metabase-teradata-driver/releases" |
  jq -r --arg v "$newver" '[.[].tag_name | select(startswith($v + "-metabase-v"))][0]')
[[ $tag =~ -metabase-v([0-9.]+)-teradata-jdbc-([0-9.]+)$ ]]
sed -i "s/^_pkgvermetabase=.*/_pkgvermetabase=${BASH_REMATCH[1]}/; s/^_pkgverjdbc=.*/_pkgverjdbc=${BASH_REMATCH[2]}/" PKGBUILD
