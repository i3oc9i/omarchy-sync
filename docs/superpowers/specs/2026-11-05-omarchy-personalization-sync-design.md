# One-way Omarchy personalization sync — design

## Intent

The current laptop (`btw`) is always the master; a second Omarchy laptop (also `btw`) is a disposable target for personalization. After manually running `omarchy update` on the slave, export a snapshot on the master, carry it on USB, preview it, and apply it on the slave. The result should have the same installed applications, Omarchy appearance and portable settings. This is **not** a whole-home backup or a disk clone.

## What the user decided

- One-way, manual transfer via USB; no network connection between laptops is required. The slave can access the internet to install packages/tools.
- Use the same small CLI on both laptops: export an archive on master, preview/apply it on slave.
- Match apps including web-app desktop shortcuts. Remove slave-only apps/tools after a clear preview and confirmation.
- Include active mise-managed tools and uv-installed tools, reinstalling them rather than copying caches or executables.
- Do not copy app configuration, browser profiles, accounts, credentials, documents, or other personal files.
- Keep the slave's hardware-specific settings and packages intact. Both Linux usernames are `btw`.
- Keep the project in `~/Projects/omarchy-personalization-sync`.

## CLI and artifact

Implement a standalone Python 3 CLI using the standard library for archive handling, plan generation and file operations, and the installed native tools (`pacman`, `omarchy`, `mise`, `uv`) for inventory/apply. Provide `export OUTPUT.tar.gz`, `plan ARCHIVE.tar.gz`, and `apply ARCHIVE.tar.gz` commands. The user copies the CLI to the slave once (or carries it with the archive); the archive itself is a versioned tarball containing a JSON manifest and only allowed portable files. The manifest records the Omarchy version, origin machine identifier fingerprint, package/tool names and versions or install specs, portable file inventory, and SHA-256 hashes. Never embed executable installers or credentials in the archive. Refuse malformed archives, unexpected paths/links, missing files, checksum mismatch, unsupported format versions, mismatched Omarchy versions, or applying a snapshot on its origin machine. Archive contents and copied hooks/plugins are trusted user-owned code: show their paths in the preview and warn not to import an untrusted USB archive.

`plan` is read-only and displays exact install/remove/replace/keep lists, including packages that cannot safely be classified. `apply` displays the same plan and asks for an explicit confirmation before any changes. No unattended `--yes` in the initial release. Re-running `apply` with the same archive should be idempotent. Missing install sources or failed installs stop before any removals; errors should be reported clearly. Only the slave is modified by `apply`; no automatic schedule or remote access.

## Package-managed applications

Export explicitly installed pacman package names (`pacman -Qqe`) plus origin/source metadata as an inventory, not a promise to copy all 1,084 system packages or pin versions. The master currently has 197 explicitly installed packages; these mix actual apps with the kernel, firmware, bootloader, Intel/NVIDIA drivers and core Omarchy components. After the slave's Omarchy update, install missing application and user-facing CLI packages available from its configured sources. Never copy package files or system config from master. Display unavailable packages as blockers instead of silently omitting them.

For removal, compare *explicitly installed* slave packages with the manifest. Classify hardware, kernel/boot, firmware, Omarchy/base, display/session and their required dependency closure as protected; never remove protected packages, even if absent on the master. Present each remaining slave-only candidate by name for review. Simulate the package manager's entire removal set before execution; refuse a removal that would take protected packages or dependencies of desired packages with it. Package removals happen last and only after explicit confirmation. Packages that cannot be confidently classified are marked `manual review`, not automatically deleted. An exact package-level mirror is impossible across differing laptop hardware; this is intentionally an app mirror, not a system-package mirror.

Do not remove package-owned launchers directly. Omarchy's native package commands are preferred where appropriate; apply must never edit `/usr/share/omarchy/`. Repository availability, package renames and conflicts may require manual resolution rather than destructive guessing. Package installation/removal is not transactionally reversible even though portable settings are backed up.

## Mise and uv tools

Export only the actively installed mise tool specs (`mise ls --json`, filtering both `installed` and `active`), not cached prior versions or all declared-but-uninstalled defaults. Export uv-installed tools and reconstruct their safe install specs from uv's own inventory/metadata, including extras or sources where supported; never serialize credentials embedded in tool URLs. On slave, show additions, version changes and slave-only tool removals, and use mise/uv to reinstall the selected specs. Preserve user app state; do not copy `~/.local/share/mise`, uv tool environments, caches, or auth state. If a tool cannot be reconstructed safely, report it for manual handling, not a silent omission. In particular, this master has a `repos-update` uv tool installed from `file:///home/btw/Projects/tools/repos_update`; because projects are out of scope, report it as manual-only rather than exporting its local source or claiming it will install on the slave. Avoid copying `~/.config/mise/config.toml` wholesale: it belongs to the target's tool configuration, and tool activation must be planned explicitly without overwriting unrelated settings. Do not uninstall Omarchy's packaged `mise`/`uv` binaries while reconciling tools.

## Portable appearance and Omarchy settings

Allowlist user-owned Omarchy settings and assets under `~/.config/omarchy/`: shell settings (`shell.json`, `shell.toml`), bar/menu extensions, plugins including the custom AC-power idle behavior, user backgrounds/themes, branding, and portable defaults. Allowlist portable Hyprland files such as bindings, input, look-and-feel, autostart, and night-light settings. Export current theme `Retro 82`, font `CaskaydiaMono Nerd Font`, and any Omarchy-selected wallpaper state. Apply theme/font using Omarchy's commands after copying user-owned theme assets, so generated app theme files on the slave are created by Omarchy rather than copied from the master. Preserve the slave's `hypr/monitors.lua` and its display-specific settings.

Omit app-specific config directories (browsers, editors, terminals, agents, etc.), secrets, OS-wide `/etc` state, hardware/boot scripts and hardware-specific Omarchy hooks (e.g. fingerprint setup) by default. Portable hooks that are included must be listed individually in the plan and copied only after inspection. Theme- and font-set hooks can execute when those commands run: apply theme/font before importing hooks, and never invoke newly imported hooks as part of apply. Exclude stale `.bak` files, caches and generated state. Preserve unrelated slave files outside the explicit allowlist. Within managed portable paths, show differences and back up overwritten/deleted slave files under a timestamped directory in the slave home before replacement. Restore permissions as needed; never follow archive links outside the managed tree. Validate JSON and Hyprland settings before/reload after applying, and report if the shell needs restart or a new login is required. Do not overwrite `/usr/share/omarchy/`.

## Web apps

Export Omarchy web-app launchers under `~/.local/share/applications` identified by `omarchy-launch-webapp` or the shipped HEY/Zoom web-app handlers, plus their user-owned icon assets in `~/.local/share/icons/hicolor` if present. Preview additions, changed launchers and slave-only web-app launchers; back up any modified/removed slave launchers/icons before reconciling. Never blindly sync all `.desktop` files, browser profiles, cookies or credentials. Web apps may start signed out on the slave. If a launcher refers to a user-installed executable not supplied by package/mise/uv, flag it as requiring manual action rather than pretending it works.

## Safety and verification

- Export and plan are read-only. No settings or packages are changed on the master.
- Apply requires matching Omarchy version and matching expected username, and refuses the origin machine. Require internet only on slave for missing installs, not for reading the archive.
- Validate source paths, archive entry types, hashes and allowed targets before any mutations. No extraction into arbitrary paths, no traversal, no replacing symlinks into protected areas.
- Create a recoverable backup of every affected portable file before touching it. Settings changes should be atomic where practical; never claim package removal is reversible by that backup.
- Apply installation first, validated portable settings and web apps next, then reviewed extra-tool/app removals last; stop safely on partial failures, with clear resume guidance.
- Test export/plan/apply logic with temporary fake homes and command stubs. Verify archive validation, no master mutation, version/host guards, classification and protected removals, dry-run, idempotence, tool reinstall specs, web-app icons, backups, and failure recovery. Manually verify Omarchy/Hyprland commands and real inventories before any live apply. Never use the user's only master laptop as a simulated slave.

## Explicit non-goals and open implementation choices

No continuous syncing, package version rollback, live filesystem cloning, app logins/config sync, hardware/firmware/boot configuration sync, project files, or portable copies of locally unpacked binaries. Initial implementation should make the source/install distinction visible if a package or tool needs a non-standard repository. Exact file allowlists, the protected package classifier, uv spec extraction, backup location, and command output format are builder choices subject to the safety requirements above; if these cannot reliably distinguish apps from system components, fail closed and report candidates for manual confirmation instead of removing them.
