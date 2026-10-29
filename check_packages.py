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
  REBUILD         with PACKAGES, also build the listed packages that are up to date

Packages depending on python that were last updated before the current Python minor
version reached Arch are added with "python" set, to be rebuilt with pkgrel+1.
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from aur import get, maintainer

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "nvchecker.toml"
OLDVER = ROOT / "old_ver.json"
KEYFILE = ROOT / "keyfile.toml"


def aur_packages(maintainer: str) -> list[dict]:
    """Return AUR info of the packages maintained or co-maintained by maintainer.

    Search results lack dependencies, so they are looked up with info, 100 names per request.
    """
    names: set[str] = set()
    for by in ("maintainer", "comaintainers"):
        data = json.loads(get(f"https://aur.archlinux.org/rpc/v5/search/{maintainer}?by={by}"))
        names |= {p["Name"] for p in data["results"]}
    packages: list[dict] = []
    ordered = sorted(names)
    for i in range(0, len(ordered), 100):
        query = "&".join(f"arg[]={n}" for n in ordered[i:i + 100])
        packages += json.loads(get(f"https://aur.archlinux.org/rpc/v5/info?{query}"))["results"]
    return packages


def aur_versions(packages: list[dict]) -> dict[str, str]:
    """Return {pkgbase: pkgver} of packages.

    Sections are named after the pkgbase, which may differ from every pkgname.
    Epoch and pkgrel are stripped, as nvchecker reports upstream versions only.
    """
    return {p["PackageBase"]: re.sub(r"-[^-]+$", "", re.sub(r"^\d+:", "", p["Version"])) for p in packages}


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


def python_minor() -> str:
    """Return the minor version of Python in the Arch repositories, e.g. 3.14."""
    info = subprocess.run(["pacman", "-Si", "python"], check=True, capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C"}).stdout
    if not (m := re.search(r"^Version\s*:\s*(\S+)", info, re.MULTILINE)):
        raise SystemExit("Can't read the Python version from pacman")
    return ".".join(m[1].split(".")[:2])


def python_since(minor: str) -> int:
    """Return when the first package of the Python minor version reached Arch, as a timestamp.

    Read from the Arch Linux Archive, which lists every published package with its date.
    """
    listing = get("https://archive.archlinux.org/packages/p/python/")
    dates = [datetime.strptime(d, "%d-%b-%Y %H:%M").replace(tzinfo=UTC)
             for d in re.findall(rf'href="python-{re.escape(minor)}\.[^"]+\.pkg\.tar\.\w+"[^\n]*?(\d{{2}}-\w{{3}}-\d{{4}} \d{{2}}:\d{{2}})', listing)]
    return int(min(dates).timestamp())


def python_rebuilds(packages: list[dict], versions: dict[str, str]) -> list[dict]:
    """Return packages depending on python that were last updated before the current minor version."""
    minor = python_minor()
    since = python_since(minor)
    config = tomllib.loads(CONFIG.read_text())
    rebuilds: dict[str, dict] = {}
    for p in packages:
        base = p["PackageBase"]
        depends = {re.split(r"[<>=]", d)[0] for d in p.get("Depends") or []}
        if "python" in depends and p["LastModified"] < since and base in config:
            rebuilds[base] = {"name": base, "oldver": versions[base], "newver": versions[base],
                              "delta": "python", "python": minor,
                              "build": config[base].get("build", True)}
    if rebuilds:
        print(f"Python {minor} since {datetime.fromtimestamp(since, UTC):%Y-%m-%d}, rebuilding:",
              *sorted(rebuilds), file=sys.stderr)
    return list(rebuilds.values())


def only(packages: list[dict], names: str, versions: dict[str, str], rebuild: bool) -> list[dict]:
    """Return the packages listed in names (all if empty).

    With rebuild, listed packages that are up to date are added at their AUR version.
    Unknown or skipped names are reported.
    """
    wanted = set(re.split(r"[\s,]+", names.strip())) - {""}
    if not wanted:
        return packages
    selected = [p for p in packages if p["name"] in wanted]
    missing = wanted - {p["name"] for p in selected}
    if rebuild:
        config = tomllib.loads(CONFIG.read_text())
        for name in sorted(missing & versions.keys() & config.keys()):
            selected.append({"name": name, "oldver": versions[name], "newver": versions[name],
                             "delta": "rebuild", "build": config[name].get("build", True)})
        missing -= {p["name"] for p in selected}
    if missing:
        print("PACKAGES not outdated or not in nvchecker.toml:", *sorted(missing), file=sys.stderr)
    return selected


def limit(packages: list[dict], max_updates: int) -> list[dict]:
    """Return the first max_updates packages (all if 0), reporting the postponed ones."""
    if max_updates and len(packages) > max_updates:
        print(f"MAX_UPDATES={max_updates}, postponing:", *(p["name"] for p in packages[max_updates:]),
              file=sys.stderr)
        return packages[:max_updates]
    return packages


def main() -> None:
    """Print outdated packages as JSON on stdout."""
    aur = aur_packages(maintainer())
    versions = aur_versions(aur)
    write_oldver(versions)
    packages = outdated()
    # an upstream update rebuilds against the current Python anyway
    packages += [p for p in python_rebuilds(aur, versions) if p["name"] not in {q["name"] for q in packages}]
    packages = only(packages, os.environ.get("PACKAGES") or "", versions, bool(os.environ.get("REBUILD")))
    print(json.dumps(limit(packages, int(os.environ.get("MAX_UPDATES") or 0))))


if __name__ == "__main__":
    main()
