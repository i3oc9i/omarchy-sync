# Omarchy Personalization Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manual, USB-based, one-way export/preview/apply CLI for apps and portable Omarchy personalization between two `btw` laptops.

**Architecture:** A stdlib-only Python package captures a versioned, checked archive with a constrained file allowlist and package/tool inventories. A read-only planner compares the archive against a target, rejects mismatches and unsafe removals, and an explicitly confirmed applier installs tools, backs up/copies portable files, then removes approved extras.

**Tech Stack:** Python 3 standard library (`argparse`, `json`, `tarfile`, `hashlib`, `tomllib`, `unittest`), native `omarchy`, `pacman`, `mise`, `uv` commands.

**Spec:** `docs/superpowers/specs/2026-11-05-omarchy-personalization-sync-design.md`

## Global Constraints

- Master and slave username: `btw`; master exports, slave applies, never the reverse.
- Manual USB archive; target has internet for missing installs; no direct master-to-slave connection.
- Slave runs `omarchy update` before apply; refuse different `omarchy version` values.
- Never edit `/usr/share/omarchy/`, copy app configs/credentials/projects, or replace hardware/display/boot state.
- Preview and explicit confirmation before any apply; protect hardware/core packages and report uncertain removals instead of guessing.
- The master has a uv tool `repos-update` from a local `file://` project; report it as manual-only, do not include the project.
- No live apply to the only available machine; use fake homes and fake command runners in tests.

## Review Focus

- Archive containing `../`, absolute paths, links or duplicate entries: reject before changing target (Task 1).
- Web-app launcher with a custom `Exec` rather than `omarchy-launch-webapp`: exclude and report, not copy an executable (Task 2).
- uv receipt pointing at a `file://` project or credential-bearing URL: flag manual-only without leaking source secrets (Task 3).
- Removal preview that includes a kernel/driver or dependency of a wanted package: refuse removal, including `pacman -Rns --print` transitive targets (Task 4).
- Failure halfway through install/copy/removal: keep prior backups, stop further removals and provide safe retry guidance (Tasks 5–6).

---

## File map

- `src/omarchy_sync/archive.py`: archive schema, file hashes, strict tar creation/validation.
- `src/omarchy_sync/portable.py`: allowed Omarchy/Hyprland files, theme/font/background identity and web-app launchers/icons.
- `src/omarchy_sync/inventory.py`: shell command runner; pacman, active mise and uv inventory and source checks.
- `src/omarchy_sync/planning.py`: version/host guards, diff, protected-package classification and package removal preflight.
- `src/omarchy_sync/apply.py`: backups, atomic portable file reconciliation and theme/font/background activation.
- `src/omarchy_sync/operations.py`: ordered package, mise and uv installs/removals; stop on failure.
- `src/omarchy_sync/cli.py`: `export`, `plan`, `apply`, confirmation and display of manual-only items.
- `omarchy-personalization-sync`: executable Python entrypoint (copied with the project/USB to slave).
- `tests/test_archive.py`, `tests/test_portable.py`, `tests/test_inventory.py`, `tests/test_planning.py`, `tests/test_apply.py`, `tests/test_cli.py`: stdlib unittest tests with `TemporaryDirectory` and fake runner.
- `README.md`: installation, USB commands, boundaries, recovery and source-machine warning.

### Task 1: Validated portable archive

**Files:** Create `src/omarchy_sync/__init__.py`, `src/omarchy_sync/archive.py`, `tests/test_archive.py`; initialize a Git repository here and include the approved spec/plan in the first commit.

**Interfaces:** `write_archive(output: Path, manifest: dict, files: dict[str, Path]) -> None`; `read_archive(path: Path) -> tuple[dict, dict[str, bytes]]`. Manifest schema v1 contains `format_version`, `omarchy_version`, `origin_machine_fingerprint`, `username`, `packages`, `mise`, `uv`, `appearance`, `manual_only`, `files` (relative paths mapped to SHA-256). File keys are relative to home; validate their safe path grammar here and apply Task 2's allowlist at the export/plan/apply boundary. Reject duplicate names, links, non-regular tar entries, traversal, excessive declared sizes and bad hashes, before returning file bytes. Do not unpack to filesystem during validation.

- [ ] **Step 1: Write failing archive tests** for a round trip preserving bytes and hash, a modified hash, `../outside`, absolute path, duplicate member, symlink and unsupported format. Assert each unsafe input raises `ValueError` without writing outside the temp directory.
- [ ] **Step 2: Run `python -m unittest tests.test_archive -v`** and verify failures are due to missing archive behavior.
- [ ] **Step 3: Implement `write_archive` and `read_archive`** with tarfile regular-member validation, schema keys, bounded total read size and checksum verification. Keep the archive itself the only export output.
- [ ] **Step 4: Run `python -m unittest tests.test_archive -v`**; require all cases green.
- [ ] **Step 5: Commit** the archive, tests and approved design/plan (`git init` only in this new project, then `git add` named files and `git commit -m 'feat: validate personalization archives'`).

### Task 2: Portable file and appearance discovery

**Files:** Create `src/omarchy_sync/portable.py`, `tests/test_portable.py`.

**Interfaces:** `collect_portable(home: Path, runner: Runner) -> tuple[dict[str, Path], dict, list[str]]` returns safe relative path-to-file map, appearance `{theme, font, background_filename}`, and manual-only warnings. `is_allowed(path: str) -> bool` is shared with Task 1's archive reader and Task 5's writer; avoid circular imports. Allowlisted user Omarchy files/dirs, portable Hyprland files, Omarchy web-app desktop launchers and their referenced user icons only. Exclude `hypr/monitors.lua`, `hypr/xdph.conf`, hardware/post-update hooks, `.bak`, application configs, device state and all links to outside the managed roots. Query `omarchy theme current`, `omarchy font current` and the selected background's filename, but never export the current theme's generated state directory.

- [ ] **Step 1: Write failing portable tests** in fake homes: collect shell config, custom `btw.idle` plugin, safe theme hook, theme asset, a valid WhatsApp web-app launcher plus its icon; exclude monitor file, hardware hook, browser profile, unrelated `.desktop` and a custom-Exec launcher (report that launcher). Test a symlink escaping home is rejected.
- [ ] **Step 2: Run `python -m unittest tests.test_portable -v`** and confirm expected red cases.
- [ ] **Step 3: Implement `collect_portable` and `is_allowed`** with a fixed path policy, resolved-path checks and web-app identification. Do not read `.claude/skills/` or include it in archive traversal.
- [ ] **Step 4: Run the targeted tests and `python -m unittest discover -s tests -v`**; require green.
- [ ] **Step 5: Commit** this tested discovery boundary.

### Task 3: Package, mise and uv inventories

**Files:** Create `src/omarchy_sync/inventory.py`, `tests/test_inventory.py`.

**Interfaces:** `Runner.run(argv: list[str]) -> str` raises on nonzero exit; `collect_inventory(home: Path, runner: Runner) -> tuple[dict, list[str]]`. Inventory keys: `packages` (explicit package names with repo/local source), `mise` (tool name to exact active installed version), `uv` (tool name to safe reinstall spec/version). `manual_only` warns about unportable sources and never contains auth tokens. Read `pacman -Qqe`, `pacman -Qm`, `mise ls --json`, and uv tool receipt metadata via `tomllib`; prefer uv's own metadata to parsing human-readable output. Exclude inactive/uninstalled mise declarations and old cached versions. A file/url source which cannot be reinstalled from slave's repositories must not be marked installable. Inventory does not copy any tool state or config.

- [ ] **Step 1: Write failing inventory tests** for one repo package, one local-only package, installed/active versus cached/declaration-only mise tools, a PyPI uv tool, and `repos-update` from `file:///home/btw/Projects/tools/repos_update`. Verify URL credentials never appear in manifest/warning output.
- [ ] **Step 2: Run `python -m unittest tests.test_inventory -v`**; verify the tests fail on absent behavior.
- [ ] **Step 3: Implement `Runner` and `collect_inventory`** with structured parsing and a stable output schema. For unsupported uv specs, put tool names in manual-only, not a broken install command; do not export `~/.config/mise/config.toml` wholesale.
- [ ] **Step 4: Run targeted tests and the full unittest discovery**; require green.
- [ ] **Step 5: Commit** the inventory boundary and tests.

### Task 4: Read-only diff and removal protection

**Files:** Create `src/omarchy_sync/planning.py`, `tests/test_planning.py`.

**Interfaces:** `build_plan(manifest: dict, files: dict[str, bytes], target: dict, home: Path, runner: Runner) -> dict` returns install/remove/manual/keep file, package, mise and uv operations and preflight errors; it does not mutate the target. `target` has the same inventory schema plus `omarchy_version`, `username`, and `machine_fingerprint`. `pacman -Rns --print --print-format '%n'` preflights every candidate; never use cascade/force removal. Protect `base`, `omarchy`, kernel, firmware, bootloader, GPU/CPU and session/display packages and any wanted/protected package in the simulated transitive removal list; ambiguous extras go to manual review. Refuse same machine, wrong user/version, missing sources and invalid archive metadata before proposing apply.

- [ ] **Step 1: Write failing planner tests** for matching app install/remove, no changes on second run, version mismatch, same-machine guard, slave-only NVIDIA/Intel driver and kernel protection, a simulated package removal that also removes a wanted dependency, web-app differences, mise/uv extras, and the master-only local uv tool as manual-only. Assert no runner mutation call is made by the planner.
- [ ] **Step 2: Run `python -m unittest tests.test_planning -v`**; confirm expected red cases.
- [ ] **Step 3: Implement `build_plan`** with a conservative classifier, preflight and deterministic, human-readable plan fields. If classification/source checks cannot prove safety, require manual review and do not put the package in automated removals.
- [ ] **Step 4: Run targeted tests and full unittest discovery**; require green.
- [ ] **Step 5: Commit** the planner and tests.

### Task 5: Backed-up portable settings apply

**Files:** Create `src/omarchy_sync/apply.py`, `tests/test_apply.py`.

**Interfaces:** `apply_files(plan: dict, files: dict[str, bytes], home: Path, runner: Runner) -> Path | None` returns backup directory for actual changes, or `None` on no-op. Revalidate `is_allowed` and safe destination parents before writing; stage writes atomically, back up every overwritten/removed managed file under `~/.local/state/omarchy-personalization-sync/backups/<timestamp>/`, preserving relative names and permissions. Order user theme assets before Omarchy theme/font/background commands and copy portable hooks **after** these commands so import never triggers newly copied hooks. Reconcile only managed web-app launchers/icons; never delete an unrelated `.desktop` entry. Validate shell JSON and Hyprland config, then reload/restart as appropriate; report needed login if any.

- [ ] **Step 1: Write failing apply tests** using fake homes and runner: backup existing shell config and replaced web app, keep slave monitor file and unrelated app config unchanged, block destination symlink escape, apply theme before copied theme hook exists, and test partial failure retains backups and stops further file removals.
- [ ] **Step 2: Run `python -m unittest tests.test_apply -v`**; verify missing behavior is the failure.
- [ ] **Step 3: Implement `apply_files`** with explicit staging, backups, allowlist recheck, hook ordering and actionable error output. Do not operate on real `~/.config` in these tests.
- [ ] **Step 4: Run targeted tests and full unittest discovery**; require green.
- [ ] **Step 5: Commit** settings application and tests.

### Task 6: Ordered tool/package operations and CLI

**Files:** Create `src/omarchy_sync/operations.py`, `src/omarchy_sync/cli.py`, `omarchy-personalization-sync`, `tests/test_cli.py`, `README.md`.

**Interfaces:** `install_missing(plan: dict, runner: Runner) -> None`; `remove_extras(plan: dict, runner: Runner) -> None` use argument arrays (never shell interpolation) and stop on failures. `main(argv: list[str] | None = None) -> int` implements `export OUTPUT.tar.gz`, `plan ARCHIVE.tar.gz`, `apply ARCHIVE.tar.gz` with re-read/re-plan just before apply and a typed confirmation; exit nonzero on blockers. Export calls Tasks 1–3; plan calls Tasks 1, 3–4; apply calls Task 4 then install, `apply_files`, and finally remove extras. For user-owned mise tools, use `mise use --global --pin tool@version` to activate without overwriting unrelated settings, and `mise unuse --global tool` only for slave-only declarations in the target's global config; tools declared by `/etc/mise` but absent on master go to manual review instead. uv tool reinstall/uninstall uses safe specs only. Never run `sudo` non-interactively; this CLI runs in a terminal and Omarchy/pacman may prompt for a password.

- [ ] **Step 1: Write failing CLI tests** with fake homes/runner: end-to-end export and plan are read-only; apply rejection leaves target unchanged; confirmed apply installs before file changes before removals; failed install blocks removals; rerun of a successful apply is a no-op; uncertain uv `file://` tool is reported, not installed; different Omarchy versions block all writes.
- [ ] **Step 2: Run `python -m unittest tests.test_cli -v`** and confirm missing behavior causes failures.
- [ ] **Step 3: Implement `operations`, `cli`, entrypoint and README** with the specified commands, USB transfer example, initial CLI setup on both laptops, backup/retry instructions, and warning that `repos-update` needs its project installed separately.
- [ ] **Step 4: Run `python -m unittest discover -s tests -v`**, `python omarchy-personalization-sync --help`, a real-master `export`, and `plan` only against a fake slave fixture. Confirm the real export validates and contains no secrets; verify that trying to plan it on the real master is refused by the origin-machine guard. Never simulate a slave or apply on this master.
- [ ] **Step 5: Commit** CLI, docs and tests, then report the real dry-run, manual-only tools and unverified live-slave behavior.
