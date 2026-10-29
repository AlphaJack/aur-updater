#!/usr/bin/env bash
# Usage, with AUR_SSH_PRIVATE_KEY set:
#   ./aur_ssh.sh test        check the key and the AUR host key, before any package is updated
#   ./aur_ssh.sh push PKG    push build/PKG to the AUR
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)

if [[ -z ${AUR_SSH_PRIVATE_KEY:-} ]]; then
  echo "::error::Secret AUR_SSH_PRIVATE_KEY is not set, set it or run with dry_run=true" >&2
  exit 1
fi

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
printf '%s\n' "$AUR_SSH_PRIVATE_KEY" > "$dir/key"
chmod 600 "$dir/key"
# Ed25519 SHA256:RFzBCUItH9LZS0cKB5UE6ceAYhBD5C8GeOBip8Z11+4, as published on https://aur.archlinux.org
echo 'aur.archlinux.org ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEuBKrPzbawxA/k2g6NcyV5jmqwJ2s+zpgZGZ7tpLIcN' > "$dir/known_hosts"

# explicit files only, no ssh config or agent: ssh looks up ~/.ssh in /etc/passwd, not $HOME,
# and GitHub containers set a different $HOME
ssh_cmd=(ssh -F /dev/null -i "$dir/key" -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes
  -o UserKnownHostsFile="$dir/known_hosts" -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519)

case ${1:-} in
  test)
    # ssh exits 255 on its own errors (host key, authentication), otherwise with the remote command status
    rc=0
    "${ssh_cmd[@]}" aur@aur.archlinux.org help > /dev/null || rc=$?
    if ((rc == 255)); then
      echo "::error::Can't log in to the AUR with AUR_SSH_PRIVATE_KEY" >&2
      exit 1
    fi
    echo "AUR SSH login works"
    ;;
  push)
    GIT_SSH_COMMAND="${ssh_cmd[*]}" git -C "$root/build/$2" push "ssh://aur@aur.archlinux.org/$2.git" HEAD:master
    ;;
  *) sed -n '2,4p' "$0"; exit 1 ;;
esac
