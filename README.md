# aur-updater

[![packages](https://img.shields.io/badge/packages-165-brightgreen)](nvchecker.toml)
[![update_packages](https://img.shields.io/github/actions/workflow/status/AlphaJack/aur-updater/update_packages.yml?branch=main&label=update_packages)](https://github.com/AlphaJack/aur-updater/actions/workflows/update_packages.yml)
[![update_catalog](https://img.shields.io/github/actions/workflow/status/AlphaJack/aur-updater/update_catalog.yml?branch=main&label=update_catalog)](https://github.com/AlphaJack/aur-updater/actions/workflows/update_catalog.yml)

Automatically update AUR packages

- `update_packages.yml` checks upstream versions with [nvchecker](https://nvchecker.readthedocs.io/), then bumps, verifies (or builds) and pushes each outdated package to the AUR.
- `update_catalog.yml` opens a pull request adding newly adopted packages to `nvchecker.toml` and removing disowned ones.

## Setup

- Locally: `pacman -S nvchecker python-packaging`
- GitHub:
  - Secret `AUR_SSH_PRIVATE_KEY` of the AUR account maintaining the packages
  - Optional variable `MAX_UPDATES` to limit packages that are updated in one run
  - Optional variable `DRY_RUN` set to `true` to commit in the runner only, without pushing to the AUR
  - Settings > Actions > General > "Allow GitHub Actions to create and approve pull requests" for `update_catalog.yml`

## Add a package

Run `./update_catalog.py` to append sections for newly adopted packages, then review each new entry:

1. Sections are named after the AUR pkgbase ([sources](https://nvchecker.readthedocs.io/en/latest/usage.html#configuration-table)):
   ```toml
   [foo-bin]
   source = "github"
   github = "owner/foo"
   use_latest_release = true
   prefix = "v"
   # only download and verify sources instead of building, e.g. for slow builds
   # build = false
   ```
   Packages that can't be tracked stay commented out as `# [foo]` with a `# manual:` reason, so `update_catalog.py` leaves them alone.
2. Check that the reported version matches the PKGBUILD `pkgver`:
   ```sh
   nvchecker -c nvchecker.toml -e foo-bin
   ```
3. If bumping `pkgver` is not enough (e.g. hashes or other variables in source URLs), add `overrides/foo-bin.sh`. It is sourced in the package dir after the bump, with `$newver` set; setting `skip_updpkgsums=1` keeps checksums as they are.
4. Test from the CLI after pushing to GitHub. With `-f dry_run=true` nothing is pushed to the AUR.
   Runs use the workflow and files committed on GitHub, not local changes:
   ```sh
   gh workflow run update_packages.yml -f dry_run=true         # dry run
   gh workflow run update_packages.yml --ref my-branch         # another pushed branch
   gh workflow run update_packages.yml -f max_updates=1        # one package only
   gh workflow run update_packages.yml -f packages=foo-bin     # only this package, if outdated
   gh workflow run update_packages.yml -f packages=foo-bin -f rebuild=true  # also if up to date
   gh workflow run update_packages.yml -f dry_run=false        # push, even if DRY_RUN=true
   gh run watch
   ```
