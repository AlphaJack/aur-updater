"""Helpers shared by check_packages.py and update_catalog.py."""

import os
import re
import subprocess
import urllib.request


def get(url: str) -> str:
    """Return the body of url, decoded as UTF-8."""
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()


def maintainer() -> str:
    """Return the AUR account whose packages are managed.

    AUR_MAINTAINER if set, otherwise the GitHub owner of this repository:
    GITHUB_REPOSITORY_OWNER in Actions, the `origin` remote locally.
    """
    if name := os.environ.get("AUR_MAINTAINER") or os.environ.get("GITHUB_REPOSITORY_OWNER"):
        return name
    url = subprocess.run(["git", "remote", "get-url", "origin"],
                         check=True, capture_output=True, text=True).stdout.strip()
    if m := re.search(r"github\.com[:/]([^/]+)/", url):
        return m[1]
    raise SystemExit(f"Can't infer the AUR maintainer from {url}, set AUR_MAINTAINER")
