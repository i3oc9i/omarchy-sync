# Omarchy personalization sync

One-way, USB-carried snapshot from the **master** Omarchy laptop to a **slave** laptop. Both use the Linux username `btw`. This tool is not part of Omarchy and is not installed system-wide.

## First-time setup

Copy `omarchy-personalization-sync` and the entire `src/omarchy_sync/` directory together to a folder on your USB drive. Use the same folder to run the tool on either laptop. Python 3, Omarchy, pacman, mise and uv must be available; there are no Python package dependencies. Do **not** use an archive provided by someone else: it can contain user-owned hooks/plugins that run code after import.

## Transfer

From the folder containing the script on the **master**, with your USB drive mounted:

```bash
python omarchy-personalization-sync export /path/to/USB/personalization.tar.gz
```

On the **slave**, first update Omarchy and restart if required:

```bash
omarchy update
python omarchy-personalization-sync plan /path/to/USB/personalization.tar.gz
python omarchy-personalization-sync apply /path/to/USB/personalization.tar.gz
```

`plan` changes nothing. `apply` prints the plan again and requires typing `APPLY`. It refuses an archive created on the same machine or a different Omarchy version, and needs internet to fetch missing apps/tools. It installs missing packages, mise tools and uv tools before it touches user files, then removes slave-only app/tool candidates after backup and preflight. It protects system/hardware packages and refuses unsafe or unknown removals. Review every listed addition/removal before confirming. On failure, stop and inspect the error; fix the cause and rerun the same `plan` before retrying `apply`.

Portable settings that are changed or removed are backed up under `~/.local/state/omarchy-personalization-sync/backups/<timestamp>/` on the slave. Package removals are **not** undone by these backups. Hyprland/shell may reload; logging out and in may be needed for all changes to take effect. The slave's monitor configuration, bootloader, drivers and firmware remain unchanged.

The snapshot does **not** copy browser logins, app profiles/config, SSH keys, documents, project files, system `/etc` settings or mise/uv caches. User-owned Omarchy settings, portable Hyprland settings, themes, fonts, backgrounds, custom shell plugins, web-app launchers and their icons are included. Web apps may launch signed out. `repos-update` is installed here by uv from a local `file://` project, which this tool deliberately does not copy; the plan will flag it for manual installation on the slave. Other apps from unavailable local or private repositories are likewise reported rather than silently installed.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests operate on fake laptop homes; they do not modify your real Omarchy configuration or packages.
