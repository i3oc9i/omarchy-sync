# omarchy-sync

One-way, USB-carried snapshot from the **master** Omarchy laptop to a **slave** laptop. Both use the Linux username `btw`. This is a standalone CLI installed with uv, not part of Omarchy.

## Install on both laptops

Like `repos_update`, install the project from its directory with:

```bash
uv tool install .
```

To install it on the slave without copying the project sources, build a wheel on the master and carry it on the USB drive:

```bash
uv build
cp dist/omarchy_sync-*.whl /path/to/USB/
```

On the slave, install that wheel (use the actual wheel filename):

```bash
uv tool install /path/to/USB/omarchy_sync-0.1.0-py3-none-any.whl
```

For a later local rebuild, run `uv tool install . --force` in the project directory; for a new wheel on the slave, use `uv tool install --force /path/to/USB/<new-wheel>.whl`. Python 3.11+, Omarchy, pacman, mise and uv must be available; the CLI has no Python runtime dependencies. Ensure your uv tool bin directory is on `PATH` (see `uv tool update-shell`). Do **not** use an archive provided by someone else: it can contain user-owned hooks/plugins that run code after import.

## Transfer

On the **master**, with your USB drive mounted:

```bash
omarchy-sync export /path/to/USB/personalization.tar.gz
```

On the **slave**, first update Omarchy and restart if required:

```bash
omarchy update
omarchy-sync plan /path/to/USB/personalization.tar.gz
omarchy-sync apply /path/to/USB/personalization.tar.gz
```

`plan` changes nothing. `apply` prints the plan again and requires typing `APPLY`. It refuses an archive created on the same machine or a different Omarchy version, and needs internet to fetch missing apps/tools. It installs missing packages, mise tools and uv tools before it touches user files, then removes slave-only app/tool candidates after backup and preflight. It protects system/hardware packages and refuses unsafe or unknown removals. Only slave-only pacman packages with a desktop launcher qualify for automatic removal; extra command-line packages appear as manual-review items. Review every listed addition/removal **including `package_removal_details`** before confirming. On failure, stop and inspect the error; fix the cause and rerun the same `plan` before retrying `apply`.

Portable settings that are changed or removed are backed up under `~/.local/state/omarchy-personalization-sync/backups/<timestamp>/` on the slave. Package removals are **not** undone by these backups. Hyprland/shell may reload; logging out and in may be needed for all changes to take effect. The slave's monitor configuration, bootloader, drivers and firmware remain unchanged.

The snapshot does **not** copy browser logins, app profiles/config, SSH keys, documents, project files, system `/etc` settings or mise/uv caches. User-owned Omarchy settings, portable Hyprland settings, themes, fonts, backgrounds, custom shell plugins, web-app launchers and their icons are included. Web apps may launch signed out. `repos-update` is installed here by uv from a local `file://` project, which this tool deliberately does not copy; the plan will flag it for manual installation on the slave. Other apps from unavailable local or private repositories are likewise reported rather than silently installed.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests operate on fake laptop homes; they do not modify your real Omarchy configuration or packages.
