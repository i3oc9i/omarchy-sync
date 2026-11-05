import argparse
import getpass
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .apply import apply_files
from .archive import read_archive, write_archive
from .inventory import Runner, collect_inventory
from .operations import install_missing, remove_extras
from .planning import build_plan
from .portable import collect_portable


def _args(argv: list[str]):
    parser = argparse.ArgumentParser(description="Export and apply portable Omarchy personalization")
    subcommands = parser.add_subparsers(dest="action", required=True)
    for action in ("export", "plan", "apply"):
        command = subcommands.add_parser(action)
        command.add_argument("archive", type=Path)
    return parser.parse_args(argv)


def machine_fingerprint() -> str:
    return hashlib.sha256(Path("/etc/machine-id").read_bytes()).hexdigest()


def _target(home: Path, runner, fingerprint: str) -> dict:
    inventory, _ = collect_inventory(home, runner)
    return {**inventory, "omarchy_version": runner.run(["omarchy", "version"]).strip(),
            "machine_fingerprint": fingerprint, "username": getpass.getuser()}


def run_command(argv: list[str], home: Path, runner, confirm, fingerprint: str) -> int:
    arguments = _args(argv)
    home = Path(home)
    try:
        if arguments.action == "export":
            files, appearance, portable_warnings = collect_portable(home, runner)
            inventory, inventory_warnings = collect_inventory(home, runner)
            manifest = {
                "format_version": 1,
                "omarchy_version": runner.run(["omarchy", "version"]).strip(),
                "origin_machine_fingerprint": fingerprint,
                "username": getpass.getuser(),
                **inventory,
                "appearance": appearance,
                "manual_only": portable_warnings + inventory_warnings,
                "files": {},
            }
            write_archive(arguments.archive, manifest, files)
            print("Exported", arguments.archive)
            for warning in manifest["manual_only"]:
                print("Manual:", warning)
            return 0
        manifest, files = read_archive(arguments.archive)
        target = _target(home, runner, fingerprint)
        plan = build_plan(manifest, files, target, home, runner)
        print(json.dumps(plan, indent=2, sort_keys=True))
        if plan["blockers"]:
            print("Cannot apply until blockers are resolved.", file=sys.stderr)
            return 2
        if arguments.action == "plan":
            return 0
        if confirm("Type APPLY to confirm install, file changes and removals: ") != "APPLY":
            print("Cancelled; no changes made.")
            return 1
        install_missing(plan, runner)
        backup = apply_files(plan, files, home, runner)
        remove_extras(plan, runner)
        print("Applied. Portable file backups:", str(backup) if backup else "none needed")
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print("Sync stopped:", error, file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    return run_command(sys.argv[1:] if argv is None else argv, Path.home(), Runner(), input, machine_fingerprint())
