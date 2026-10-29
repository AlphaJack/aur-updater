#!/usr/bin/env bash
# One subcommand per workflow step, working in build/PKG:
#   ./update_packages.sh prepare PKG NEWVER   clone PKG from the AUR, bump to NEWVER, update checksums and .SRCINFO
#   ./update_packages.sh deps PKG             install repo and AUR dependencies (via yay) listed in .SRCINFO
#   ./update_packages.sh verify PKG           download and verify sources
#   ./update_packages.sh build PKG            build the package
#   ./update_packages.sh commit PKG NEWVER    commit PKGBUILD and .SRCINFO
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)

prepare() {
  local pkg=$1 newver=$2 dir=$root/build/$1
  # newver comes from upstream and ends up in sed and in a sourced PKGBUILD
  if [[ ! $newver =~ ^[[:alnum:]._+]+$ ]]; then
    echo "Refusing invalid pkgver: $newver" >&2
    exit 1
  fi

  rm -rf "$dir"
  git clone "https://aur.archlinux.org/$pkg.git" "$dir"
  cd "$dir"

  # only a new version resets pkgrel, a rebuild of the same version keeps it
  if [[ $(grep -oP '^pkgver=\K.*' PKGBUILD) != "$newver" ]]; then
    sed -i "s/^pkgver=.*/pkgver=$newver/; s/^pkgrel=.*/pkgrel=1/" PKGBUILD
  fi
  if [[ -f $root/overrides/$pkg.sh ]]; then
    # shellcheck source=/dev/null
    newver=$newver source "$root/overrides/$pkg.sh"
  fi

  # an override can set skip_updpkgsums=1, e.g. for sources that change every day
  [[ -n ${skip_updpkgsums:-} ]] || updpkgsums
  makepkg --printsrcinfo > .SRCINFO
}

deps() {
  local deps
  cd "$root/build/$1"
  mapfile -t deps < <(grep -oP '^\t(make|check)?depends(_x86_64)? = \K.*' .SRCINFO)
  ((${#deps[@]})) || return 0
  if ! command -v yay > /dev/null; then
    git clone https://aur.archlinux.org/yay-bin.git "$root/build/yay-bin"
    (cd "$root/build/yay-bin" && makepkg --syncdeps --install --noconfirm)
  fi
  yay -S --needed --asdeps --noconfirm \
    --answerclean None --answerdiff None --answeredit None "${deps[@]}"
}

verify() {
  cd "$root/build/$1"
  makepkg --verifysource --noconfirm
}

build() {
  cd "$root/build/$1"
  # keep logs short: makepkg steps on success, full log (collapsed) and its tail on failure
  if makepkg --force --noconfirm > makepkg.log 2>&1; then
    grep '^==>' makepkg.log
  else
    echo "::group::Full makepkg log"
    cat makepkg.log
    echo "::endgroup::"
    tail -n 50 makepkg.log
    return 1
  fi
}

commit() {
  cd "$root/build/$1"
  git add PKGBUILD .SRCINFO
  if git diff --cached --quiet; then
    echo "$1: nothing to update"
    return
  fi
  git commit -m "Update to $2"
  git --no-pager show HEAD -- PKGBUILD
}

case ${1:-} in
  prepare) prepare "$2" "$3" ;;
  deps) deps "$2" ;;
  verify) verify "$2" ;;
  build) build "$2" ;;
  commit) commit "$2" "$3" ;;
  *) sed -n '2,7p' "$0"; exit 1 ;;
esac
