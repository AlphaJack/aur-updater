#!/usr/bin/env bash
# One subcommand per workflow step, working in build/PKG:
#   ./update_packages.sh prepare PKG NEWVER   clone PKG from the AUR, bump to NEWVER, update checksums and .SRCINFO
#                                             with PYTHON set (e.g. 3.15), increase pkgrel to rebuild for that Python
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

  # a new version resets pkgrel, a rebuild for a new Python increases it, other rebuilds keep it
  if [[ $(grep -oP '^pkgver=\K.*' PKGBUILD) != "$newver" ]]; then
    sed -i "s/^pkgver=.*/pkgver=$newver/; s/^pkgrel=.*/pkgrel=1/" PKGBUILD
  elif [[ -n ${PYTHON:-} ]]; then
    local pkgrel
    pkgrel=$(grep -oP '^pkgrel=\K[0-9]+' PKGBUILD)
    sed -i "s/^pkgrel=.*/pkgrel=$((pkgrel + 1))/" PKGBUILD
  fi
  if [[ -f $root/overrides/$pkg.sh ]]; then
    # shellcheck source=/dev/null
    newver=$newver source "$root/overrides/$pkg.sh"
  fi

  # an override can set skip_updpkgsums=1, e.g. for sources that change every day
  # packages without sources (e.g. venvs installing from PyPI in package()) have nothing to update
  if [[ -z ${skip_updpkgsums:-} ]] && makepkg --printsrcinfo | grep '^[[:space:]]source' > /dev/null; then
    updpkgsums
  fi
  makepkg --printsrcinfo > .SRCINFO
}

deps() {
  local deps
  cd "$root/build/$1"
  mapfile -t deps < <(grep -oP '^\t(make|check)?depends(_x86_64)? = \K.*' .SRCINFO)
  ((${#deps[@]})) || return 0
  # unmaintained AUR packages are replaced by a fork that provides them
  local -A forks=([python-albumentations]=python-albumentationsx)
  # AUR packages are built from source, unless a prebuilt -bin variant exists
  local i name query="" bins aur=()
  for i in "${!deps[@]}"; do
    name=${deps[i]%%[<>=]*}
    if [[ -n ${forks[$name]:-} ]]; then
      deps[i]=${forks[$name]}
      name=${deps[i]}
    fi
    pacman -Sp --print-format '%n' "$name" > /dev/null 2>&1 || query+="&arg[]=$name-bin"
  done
  if [[ -n $query ]]; then
    if ! bins=$(curl -fsS --globoff --retry 3 "https://aur.archlinux.org/rpc/v5/info?v=5${query}" | jq -r '.results[].Name'); then
      echo "::warning::Could not look up -bin variants on the AUR, building AUR dependencies from source"
    fi
    for i in "${!deps[@]}"; do
      name=${deps[i]%%[<>=]*}
      [[ $query == *"&arg[]=$name-bin"* ]] || continue
      grep -qx "$name-bin" <<< "$bins" && deps[i]=$name-bin
      aur+=("${deps[i]}")
    done
  fi
  echo "Dependencies: ${deps[*]}"
  echo "From the AUR: ${aur[*]:-none}"
  if ! command -v yay > /dev/null; then
    git clone https://aur.archlinux.org/yay-bin.git "$root/build/yay-bin"
    (cd "$root/build/yay-bin" && makepkg --syncdeps --install --noconfirm)
  fi
  # dependencies are only installed, so skip their test suites; our packages still run check()
  yay -S --needed --asdeps --noconfirm --mflags --nocheck \
    --answerclean None --answerdiff None --answeredit None "${deps[@]}"
}

verify() {
  cd "$root/build/$1"
  makepkg --verifysource --noconfirm
}

build() {
  cd "$root/build/$1"
  # live output in a collapsed group, repeat the tail outside of it on failure
  echo "::group::makepkg output"
  if makepkg --force --noconfirm 2>&1 | tee makepkg.log; then
    echo "::endgroup::"
    grep '^==> Finished' makepkg.log
  else
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
  if [[ -n ${PYTHON:-} ]]; then
    git commit -m "Rebuild for Python $PYTHON"
  else
    git commit -m "Update to $2"
  fi
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
