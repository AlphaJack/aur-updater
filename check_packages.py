#!/usr/bin/env python3
"""Print a JSON array of outdated packages: {name, oldver, newver, delta, build}.

Old versions are read from the AUR, so manual updates are picked up.
nvchecker logs go to stderr.

Usage: ./check_packages.py (needs nvchecker and python-packaging)
Env:
  AUR_MAINTAINER  whose (co-)maintained packages to compare against (default: GitHub repository owner)
  GITHUB_TOKEN    raises GitHub API rate limit for nvchecker
  MAX_UPDATES     only output the first N outdated packages, the rest wait for the next run
  PACKAGES        only consider these pkgbases, separated by spaces or commas
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from aur import get, maintainer

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "nvchecker.toml"
OLDVER = ROOT / "old_ver.json"
KEYFILE = ROOT / "keyfile.toml"


def aur_versions(maintainer: str) -> dict[str, str]:
    """Return {pkgbase: pkgver} of AUR packages maintained or co-maintained by maintainer.

    Sections are named after the pkgbase, which may differ from every pkgname.
    Epoch and pkgrel are stripped, as nvchecker reports upstream versions only.
    """
    versions: dict[str, str] = {}
    for by in ("maintainer", "comaintainers"):
        data = json.loads(get(f"https://aur.archlinux.org/rpc/v5/search/{maintainer}?by={by}"))
        for p in data["results"]:
            versions[p["PackageBase"]] = re.sub(r"-[^-]+$", "", re.sub(r"^\d+:", "", p["Version"]))
    return versions


def write_oldver(versions: dict[str, str]) -> None:
    """Write versions to OLDVER in the nvchecker version record format."""
    data = {"version": 2, "data": {k: {"version": v} for k, v in versions.items()}}
    OLDVER.write_text(json.dumps(data, indent=2))


def nvchecker_args() -> list[str]:
    """Return extra nvchecker arguments, writing KEYFILE if GITHUB_TOKEN is set."""
    if token := os.environ.get("GITHUB_TOKEN"):
        KEYFILE.write_text(f'[keys]\n"github.com" = {json.dumps(token)}\n')
        return ["-k", str(KEYFILE)]
    return []


def outdated() -> list[dict]:
    """Run nvchecker and return the packages newer upstream, with their `build` key (default true)."""
    subprocess.run(["nvchecker", "-c", CONFIG, *nvchecker_args(), "--tries", "3"],
                   check=True, stdout=sys.stderr)
    result = subprocess.run(["nvcmp", "-c", CONFIG, "-j", "-n"],
                            check=True, capture_output=True, text=True)
    # nvchecker ignores the per-package `build` key
    config = tomllib.loads(CONFIG.read_text())
    return [{**p, "build": config[p["name"]].get("build", True)} for p in json.loads(result.stdout)]


def only(packages: list[dict], names: str) -> list[dict]:
    """Return the packages listed in names (all if empty), reporting unknown or up-to-date names."""
    wanted = set(re.split(r"[\s,]+", names.strip())) - {""}
    if not wanted:
        return packages
    if missing := wanted - {p["name"] for p in packages}:
        print("PACKAGES not outdated or not in nvchecker.toml:", *sorted(missing), file=sys.stderr)
    return [p for p in packages if p["name"] in wanted]


def limit(packages: list[dict], max_updates: int) -> list[dict]:
    """Return the first max_updates packages (all if 0), reporting the postponed ones."""
    if max_updates and len(packages) > max_updates:
        print(f"MAX_UPDATES={max_updates}, postponing:", *(p["name"] for p in packages[max_updates:]),
              file=sys.stderr)
        return packages[:max_updates]
    return packages


def main() -> None:
    """Print outdated packages as JSON on stdout."""
    write_oldver(aur_versions(maintainer()))
    packages = only(outdated(), os.environ.get("PACKAGES") or "")
    print(json.dumps(limit(packages, int(os.environ.get("MAX_UPDATES") or 0))))


if __name__ == "__main__":
    main()
