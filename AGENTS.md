# Project decisions for omarchy-sync

- This is a **one-way** USB workflow: the current `btw` laptop is always the master, and the second `btw` laptop is the slave. Do not implement reverse or automatic synchronization.
- The slave runs `omarchy update` first and has internet access for installs. `export` creates the archive, `plan` is read-only, and `apply` re-plans and requires the user to type `APPLY`.
- Never run a real `apply` against the master. No real-slave apply has been verified yet; review the first slave `plan` and especially `package_removal_details` before confirming.
- Sync installed applications, portable Omarchy/Hyprland personalization, web-app shortcuts, active mise tools, and reinstallable uv tools. Do not transfer app profiles, accounts, credentials, projects, personal files, caches, or system `/etc` state.
- Preserve the slave's hardware-specific packages and settings (including monitors, drivers, firmware, and boot state). Uncertain package or tool removals require manual review rather than guessing. Back up managed files before replacing or deleting them.
- The master's `repos-update` uv tool comes from a local `file://` project; report it as manual-only, never copy the project or claim it can be reinstalled from the archive.
- Keep the project and executable named `omarchy-sync`. Package the stdlib Python CLI with Hatchling/uv as in `pyproject.toml`: `uv build` and `uv tool install .`. Do not add runtime dependencies without a reason.
- GitHub repository: `i3oc9i/omarchy-sync` (public). Prefer the SSH Git remote `git@github.com:i3oc9i/omarchy-sync.git`; if an agent session lacks `SSH_AUTH_SOCK`, diagnose SSH agent access rather than switching the remote to HTTPS. Never request or record an SSH passphrase.
- Run `python -m unittest discover -s tests -v` and verify the uv build/install path when changing packaging. Tests use fake homes; they must not alter a real Omarchy installation.

See `README.md` for the user workflow and `docs/superpowers/specs/2026-11-05-omarchy-sync-design.md` for the detailed design.
