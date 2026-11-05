import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .portable import _webapp_icon, is_allowed


def _destination(home: Path, name: str) -> Path:
    if not is_allowed(name):
        raise ValueError("path outside portable allowlist: " + name)
    path = home / name
    if path.is_symlink():
        raise ValueError("symlinked target: " + name)
    current = path.parent
    while current != home:
        if current.is_symlink() or not current.is_relative_to(home):
            raise ValueError("symlinked target parent: " + name)
        current = current.parent
    return path


def _copy_atomic(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _is_hook(name: str) -> bool:
    return name.startswith(".config/omarchy/hooks/")


def apply_files(plan: dict, files: dict[str, bytes], home: Path, runner) -> Path | None:
    home = Path(home)
    changes = list(plan["files_write"])
    deletions = list(plan["files_delete"])
    appearance = plan.get("appearance_change", {})
    if not changes and not deletions and not appearance:
        return None
    if len(changes) != len(set(changes)) or len(deletions) != len(set(deletions)) or set(changes) & set(deletions):
        raise ValueError("invalid file operation plan")
    targets = {name: _destination(home, name) for name in changes + deletions}
    for name in changes:
        if name not in files:
            raise ValueError("missing planned file: " + name)
        if name.endswith(".json"):
            json.loads(files[name])
        if name.startswith(".local/share/applications/") and _webapp_icon(files[name].decode("utf-8", "replace")) is None:
            raise ValueError("not an Omarchy web app: " + name)
    for name in deletions:
        path = targets[name]
        if name.startswith(".local/share/applications/") and path.exists():
            if _webapp_icon(path.read_text(errors="replace")) is None:
                raise ValueError("refusing to remove non-web-app launcher: " + name)
    modes = plan.get("modes", {})
    for name in changes:
        value = modes.get(name, 0o644)
        if type(value) is not int or value < 0 or value > 0o777:
            raise ValueError("invalid file mode: " + name)

    backup_root = home / ".local/state/omarchy-personalization-sync/backups"
    current = backup_root
    while current != home:
        if current.is_symlink():
            raise ValueError("unsafe backup directory")
        current = current.parent
    backup = backup_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    for name, path in targets.items():
        if path.exists():
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    backup.mkdir(parents=True, exist_ok=True)

    try:
        for name in changes:
            if not _is_hook(name):
                path = targets[name]
                mode = modes.get(name, path.stat().st_mode & 0o777 if path.exists() else 0o644)
                _copy_atomic(path, files[name], mode)
        if appearance.get("theme"):
            runner.run(["omarchy", "theme", "set", appearance["theme"]])
        if appearance.get("font"):
            runner.run(["omarchy", "font", "set", appearance["font"]])
        if appearance.get("background_filename"):
            theme = plan["appearance"]["theme"]
            slug = theme.lower().replace(" ", "-")
            directory = Path(runner.run(["omarchy", "theme", "dir", slug]).strip())
            background = directory / "backgrounds" / appearance["background_filename"]
            if not background.is_file() or not background.resolve().is_relative_to(directory.resolve()):
                raise ValueError("selected background is unavailable on slave")
            runner.run(["omarchy", "theme", "bg", "set", str(background)])
        for name in changes:
            if _is_hook(name):
                path = targets[name]
                mode = modes.get(name, path.stat().st_mode & 0o777 if path.exists() else 0o644)
                _copy_atomic(path, files[name], mode)
        for name in deletions:
            targets[name].unlink(missing_ok=True)
        if any(name.startswith(".config/hypr/") for name in changes + deletions):
            runner.run(["hyprctl", "reload"])
            errors = runner.run(["hyprctl", "configerrors"])
            if errors.strip():
                raise RuntimeError("Hyprland reported config errors: " + errors.strip())
        if any(name.startswith(".config/omarchy/plugins/") or name == ".config/omarchy/shell.json"
               for name in changes + deletions):
            runner.run(["omarchy", "restart", "shell"])
    except Exception as error:
        raise RuntimeError(f"apply stopped; original files backed up at {backup}; review before retry") from error
    return backup
