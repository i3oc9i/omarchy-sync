import hashlib
import re
import subprocess
from pathlib import Path

from .archive import checked_manifest
from .portable import _webapp_icon, collect_portable, is_allowed

CORE = {"base", "base-devel", "omarchy", "omarchy-keyring", "hyprland", "quickshell", "sddm",
        "systemd", "glibc", "sudo", "pacman", "networkmanager", "pipewire", "wireplumber",
        "mise-bin", "uv", "limine", "grub", "mkinitcpio", "btrfs-progs", "zram-generator"}
PROTECTED = re.compile(r"^(?:linux(?:-|$)|nvidia(?:-|$)|lib32-nvidia|intel-(?:ucode|media|gpu)|"
                       r"vulkan-|sof-firmware|linux-firmware|amd-ucode|mesa|xf86-|"
                       r"hyprland(?:-|$)|omarchy(?:-|$)|systemd(?:-|$)|efibootmgr|"
                       r"base(?:-|$)|sddm(?:-|$)|grub(?:-|$)|limine(?:-|$)|"
                       r"pipewire(?:-|$)|wireplumber|networkmanager|quickshell(?:-|$))")


def protected(package: str) -> bool:
    return package in CORE or bool(PROTECTED.match(package))


def _webapp(name: str, data: bytes) -> bool:
    return not name.startswith(".local/share/applications/") or _webapp_icon(data.decode("utf-8", "replace")) is not None


def build_plan(manifest: dict, files: dict[str, bytes], target: dict, home: Path, runner) -> dict:
    checked_manifest(manifest)
    if (target.get("machine_fingerprint") == manifest["origin_machine_fingerprint"] or
            target.get("omarchy_version") != manifest["omarchy_version"] or
            target.get("username") != manifest["username"] or target.get("username") != "btw"):
        raise ValueError("origin machine, Omarchy version or username mismatch")
    if set(files) != set(manifest["files"]):
        raise ValueError("file inventory mismatch")
    for name, data in files.items():
        if not is_allowed(name) or not _webapp(name, data):
            raise ValueError("file outside portable allowlist")
        if hashlib.sha256(data).hexdigest() != manifest["files"][name]:
            raise ValueError("file hash mismatch")

    result = {"packages_install": [], "packages_remove": [], "mise_install": {}, "mise_remove": [],
              "uv_install": {}, "uv_remove": [], "files_write": [], "files_delete": [],
              "manual_only": list(manifest["manual_only"]), "blockers": [],
              "appearance": manifest["appearance"]}
    desired = manifest["packages"]
    current = target["packages"]
    for package in sorted(desired.keys() - current.keys()):
        if protected(package):
            result["manual_only"].append("machine package not copied: " + package)
        elif desired[package] != "repo":
            result["blockers"].append("package needs a configured source: " + package)
        else:
            try:
                runner.run(["pacman", "-Si", package])
            except (subprocess.CalledProcessError, OSError):
                result["blockers"].append("package unavailable: " + package)
            else:
                result["packages_install"].append(package)
    for package in sorted(current.keys() - desired.keys()):
        if protected(package):
            continue
        try:
            output = runner.run(["pacman", "-Rns", "--print", "--print-format", "%n", package])
            removed = set(output.splitlines())
        except (subprocess.CalledProcessError, OSError):
            removed = set()
        if not removed or package not in removed or any(protected(p) or p in desired for p in removed):
            result["manual_only"].append("package removal needs manual review: " + package)
        else:
            result["packages_remove"].append(package)
    for system in ("mise", "uv"):
        wanted, existing = manifest[system], target[system]
        result[system + "_install"] = {name: value for name, value in sorted(wanted.items())
                                       if existing.get(name) != value}
        result[system + "_remove"] = sorted(existing.keys() - wanted.keys())

    existing_files, current_appearance, warnings = collect_portable(Path(home), runner)
    result["appearance_change"] = {key: value for key, value in manifest["appearance"].items()
                                    if value and current_appearance.get(key) != value}
    result["modes"] = manifest.get("modes", {})
    result["manual_only"].extend(warnings)
    for name, data in sorted(files.items()):
        path = Path(home) / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != Path(home).parent):
            result["blockers"].append("unsafe target path: " + name)
        elif not path.is_file() or path.read_bytes() != data:
            result["files_write"].append(name)
    result["files_delete"] = sorted(existing_files.keys() - files.keys())
    return result
