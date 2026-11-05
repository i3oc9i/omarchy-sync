import os
import re
import shlex
from pathlib import Path

from .archive import safe_name

OMARCHY_FILES = {"shell.json", "shell.toml", "defaults/agent", "defaults/dictation",
                 "branding/about.txt", "branding/screensaver.txt"}
OMARCHY_TREES = ("plugins/", "themes/", "backgrounds/", "extensions/", "themed/",
                 "hooks/theme-set.d/", "hooks/font-set.d/")
HYPR_FILES = {"hyprland.lua", "bindings.lua", "input.lua", "looknfeel.lua",
              "autostart.lua", "hyprsunset.conf"}
ICON_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")


def is_allowed(path: str) -> bool:
    if not safe_name(path) or path.startswith(".") and not path.startswith((".config/", ".local/")):
        return False
    if "/.git/" in path or path.endswith((".bak", ".sample")) or ".bak." in path:
        return False
    if path.startswith(".config/omarchy/"):
        relative = path.removeprefix(".config/omarchy/")
        return relative in OMARCHY_FILES or any(relative.startswith(p) and len(relative) > len(p) for p in OMARCHY_TREES)
    if path.startswith(".config/hypr/"):
        return path.removeprefix(".config/hypr/") in HYPR_FILES
    if path.startswith(".local/share/applications/"):
        return path.count("/") == 3 and path.endswith(".desktop")
    if path.startswith(".local/share/icons/hicolor/"):
        return ("/apps/" in path and path.endswith((".png", ".svg", ".webp"))
                and path.count("/") == 6)
    return False


def _safe_file(home: Path, path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        path.relative_to(home)
        return path.resolve().is_relative_to(home.resolve())
    except (ValueError, OSError):
        return False


def _webapp_icon(text: str) -> str | None:
    values = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith(("#", " ")):
            key, value = line.split("=", 1)
            values[key] = value.strip()
    try:
        args = shlex.split(values.get("Exec", ""))
    except ValueError:
        return None
    if len(args) != 2 or args[0] != "omarchy-launch-webapp" or not args[1].startswith(("https://", "http://")):
        return None
    icon = values.get("Icon", "")
    return icon if ICON_NAME.fullmatch(icon) else ""


def collect_portable(home: Path, runner) -> tuple[dict[str, Path], dict, list[str]]:
    home = Path(home)
    files = {}
    warnings = []
    for directory in (home / ".config/omarchy", home / ".config/hypr"):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for current, dirs, names in os.walk(directory, followlinks=False):
            dirs[:] = [d for d in dirs if d != ".git" and not (Path(current) / d).is_symlink()]
            for name in names:
                path = Path(current) / name
                relative = path.relative_to(home).as_posix()
                if is_allowed(relative) and _safe_file(home, path):
                    files[relative] = path
    launcher_dir = home / ".local/share/applications"
    icons = set()
    if launcher_dir.is_dir() and not launcher_dir.is_symlink():
        for path in launcher_dir.glob("*.desktop"):
            if not _safe_file(home, path):
                continue
            icon = _webapp_icon(path.read_text(errors="replace"))
            if icon is None:
                warnings.append("not a portable Omarchy web app: " + path.name)
                continue
            files[path.relative_to(home).as_posix()] = path
            if icon:
                icons.add(icon)
    icon_root = home / ".local/share/icons/hicolor"
    if icon_root.is_dir() and not icon_root.is_symlink():
        for size_dir in icon_root.iterdir():
            apps = size_dir / "apps"
            if not size_dir.is_dir() or size_dir.is_symlink() or not apps.is_dir() or apps.is_symlink():
                continue
            for path in apps.iterdir():
                relative = path.relative_to(home).as_posix()
                if path.stem in icons and is_allowed(relative) and _safe_file(home, path):
                    files[relative] = path
    background = home / ".local/state/omarchy/current/background"
    appearance = {
        "theme": runner.run(["omarchy", "theme", "current"]).strip(),
        "font": runner.run(["omarchy", "font", "current"]).strip(),
        "background_filename": background.resolve().name if background.exists() else "",
    }
    return files, appearance, warnings
