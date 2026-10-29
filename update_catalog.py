#!/usr/bin/env python3
"""Append nvchecker sections for AUR packages of MAINTAINER missing from nvchecker.toml.

Sections of packages no longer maintained are removed, together with the comments
in the same paragraph. Idempotent: other sections (also commented-out ones) are never touched.
Sources are guessed from .SRCINFO; unknown ones are appended commented out with a TODO.

Usage: ./update_catalog.py [MAINTAINER]
MAINTAINER defaults to AUR_MAINTAINER, otherwise the GitHub repository owner.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from aur import get, maintainer

MAINTAINER = sys.argv[1] if len(sys.argv) > 1 else maintainer()
CONFIG = Path(__file__).resolve().parent / "nvchecker.toml"
README = CONFIG.with_name("README.md")
# not version based, nvchecker can't track them
SKIP = re.compile(r"-git$")
# max tag picks pre-releases too, unlike GitHub latest release and PyPI
EXCLUDE = "exclude_regex = '.*(dev|rc|alpha|beta|pre).*'"


def maintained() -> set[str]:
    """Return the pkgbases maintained or co-maintained by MAINTAINER."""
    bases: set[str] = set()
    for by in ("maintainer", "comaintainers"):
        data = json.loads(get(f"https://aur.archlinux.org/rpc/v5/search/{MAINTAINER}?by={by}"))
        bases |= {p["PackageBase"] for p in data["results"]}
    return bases


def guess(pkgbase: str) -> tuple[list[str] | None, str, list[str]]:
    """Guess the nvchecker section of pkgbase from its .SRCINFO.

    Return (config lines, or None if the source is unknown; pkgver; source URLs).
    """
    try:
        srcinfo = get(f"https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h={pkgbase}")
    except OSError as e:
        return None, "?", [str(e)]
    pkgver = m[1] if (m := re.search(r"^\tpkgver = (.+)$", srcinfo, re.MULTILINE)) else ""
    sources = re.findall(r"^\tsource(?:_\w+)? = (?:[^:]+::)?(.+)$", srcinfo, re.MULTILINE)
    for src in sources:
        if lines := match(re.sub(r"(?<!:)/{2,}", "/", src), re.escape(pkgver)):
            return lines, pkgver, sources
    return None, pkgver, sources


def match(src: str, ver: str) -> list[str] | None:
    """Return nvchecker config lines for a single source URL embedding the escaped version ver."""
    # tag prefix, e.g. "v" or "name-"
    pre = r"(?P<pre>[^/#=]*?)"
    repo = r"(?P<repo>[^/]+/[^/#]+?)(?:\.git)?"
    rules: list[tuple[str, list[str]]] = [
        (rf"github\.com/{repo}/releases/download/{pre}{ver}/",
         ['source = "github"', 'github = "{repo}"', "use_latest_release = true"]),
        (rf"github\.com/{repo}/archive/(?:refs/tags/)?{pre}{ver}(?:/|\.tar|\.zip)",
         ['source = "github"', 'github = "{repo}"', "use_max_tag = true", EXCLUDE]),
        (rf"^git\+https://github\.com/{repo}#tag={pre}{ver}$",
         ['source = "github"', 'github = "{repo}"', "use_max_tag = true", EXCLUDE]),
        (rf"(?P<host>gitlab\.[^/]+)/(?P<repo>.+?)(?:\.git)?(?:/-/archive/|#tag=){pre}{ver}\b",
         ['source = "gitlab"', 'host = "{host}"', 'gitlab = "{repo}"', "use_max_tag = true", EXCLUDE]),
        (rf"codeberg\.org/{repo}(?:/archive/|#tag=){pre}{ver}\b",
         ['source = "gitea"', 'host = "codeberg.org"', 'gitea = "{repo}"', "use_max_tag = true", EXCLUDE]),
        (rf"^git\+(?P<repo>[^#]+)#tag={pre}{ver}$",
         ['source = "git"', 'git = "{repo}"', EXCLUDE]),
        (r"(?:files\.pythonhosted\.org|pypi\.(?:org|io))/packages/source/./(?P<repo>[^/]+)/(?P<pre>)",
         ['source = "pypi"', 'pypi = "{repo}"']),
        (rf"(?:files\.pythonhosted\.org|pypi\.(?:org|io|python\.org))/packages/.+/(?P<repo>[^/]+?)-(?P<pre>){ver}(?:\.tar|\.zip|-py)",
         ['source = "pypi"', 'pypi = "{repo}"']),
        (rf"(?:cpan\.metacpan\.org|cpan\.org)/authors/id/.+/(?P<repo>[\w-]+)-(?P<pre>){ver}\.tar",
         ['source = "cpan"', 'cpan = "{repo}"']),
        (rf"registry\.npmjs\.org/(?P<repo>(?:@[^/]+/)?[^/]+)/-/[^/]+-(?P<pre>){ver}\.tgz",
         ['source = "npm"', 'npm = "{repo}"']),
    ]
    for pattern, lines in rules:
        if m := re.search(pattern, src):
            fields = m.groupdict()
            lines = [line if line == EXCLUDE else line.format(**fields) for line in lines
                     if line != 'host = "{host}"' or fields.get("host") not in (None, "gitlab.com")]
            # tags may be URL-encoded in sources, e.g. release%2Fv
            return lines + ([f'prefix = "{unquote(m["pre"])}"'] if m["pre"] else [])
    return None


def remove(text: str, pkgs: set[str]) -> tuple[str, list[str]]:
    """Remove the blank-line separated paragraphs holding the sections of pkgs.

    Paragraphs with more than one section are kept, to avoid deleting unrelated ones.
    Return (new text, removed package names).
    """
    paragraphs = re.split(r"\n{2,}", text)
    kept: list[str] = []
    removed: list[str] = []
    for paragraph in paragraphs:
        headers = re.findall(r"^#? ?\[([^\]]+)\]", paragraph, re.MULTILINE)
        if len(headers) == 1 and headers[0] in pkgs:
            removed.append(headers[0])
        else:
            kept.append(paragraph)
    return "\n\n".join(kept), removed


def title(added: list[str], removed: list[str], limit: int = 5) -> str:
    """Return a conventional commit title, e.g. "chore: add a, b; remove c".

    Lists longer than limit are replaced by a count.
    """
    def names(verb: str, pkgs: list[str]) -> str:
        return f"{verb} {', '.join(pkgs)}" if len(pkgs) <= limit else f"{verb} {len(pkgs)} packages"

    parts = [names(verb, pkgs) for verb, pkgs in (("add", added), ("remove", removed)) if pkgs]
    return "chore: " + "; ".join(parts) if parts else "chore: no changes"


def main() -> None:
    """Append missing sections to CONFIG, remove sections no longer maintained, update the README badge."""
    text = CONFIG.read_text()
    present = set(re.findall(r"^#? ?\[([^\]]+)\]", text, re.MULTILINE))
    pkgs = maintained()

    text, removed = remove(text, present - pkgs - {"__config__"})
    if left := sorted(present - pkgs - {"__config__"} - set(removed)):
        print("not maintained, but sharing a paragraph with other sections, remove manually:", " ".join(left))

    added: list[str] = []
    for pkg in sorted(pkgs - present):
        if SKIP.search(pkg):
            continue
        lines, pkgver, sources = guess(pkg)
        if lines is None:
            block = f"\n# TODO pkgver={pkgver} sources: {' '.join(sources) or '-'}\n# [{pkg}]\n"
        else:
            block = f"\n[{pkg}]\n" + "".join(f"{line}\n" for line in lines)
        text += block
        added.append(pkg)
        print(block.strip(), end="\n\n")

    CONFIG.write_text(text)
    # badge with the number of tracked (not commented out) sections
    tracked = len(re.findall(r"^\[(?!__config__\])[^\]]+\]", text, re.MULTILINE))
    README.write_text(re.sub(r"(badge/packages-)\d+", rf"\g<1>{tracked}", README.read_text()))
    # last line, used as commit message and pull request title
    print(title(added, removed))


if __name__ == "__main__":
    main()
