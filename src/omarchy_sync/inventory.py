import json
import re
import subprocess
import tomllib
from pathlib import Path

PACKAGE = re.compile(r"^[a-zA-Z0-9@._+-]+$")
TOOL = re.compile(r"^[a-zA-Z0-9_:+./@-]+$")
UV_LINE = re.compile(r"^([a-zA-Z0-9._-]+) v([a-zA-Z0-9._+-]+)(?:\s|$)")


class Runner:
    def run(self, argv: list[str]) -> str:
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout

    def interactive(self, argv: list[str]) -> None:
        subprocess.run(argv, check=True)


def collect_inventory(home: Path, runner: Runner) -> tuple[dict, list[str]]:
    manual = []
    explicit = runner.run(["pacman", "-Qqe"]).splitlines()
    try:
        foreign_output = runner.run(["pacman", "-Qm"])
    except subprocess.CalledProcessError as error:
        if error.returncode != 1 or error.stdout or error.stderr:
            raise
        foreign_output = ""
    local = {line.split()[0] for line in foreign_output.splitlines() if line.split()}
    packages = {}
    for package in explicit:
        if not PACKAGE.fullmatch(package):
            manual.append("unrecognized pacman package name")
            continue
        packages[package] = "local" if package in local else "repo"

    mise = {}
    mise_sources = {}
    for name, versions in json.loads(runner.run(["mise", "ls", "--json"])).items():
        if not TOOL.fullmatch(name) or "://" in name or "@" in name.split(":")[0]:
            manual.append("unsupported mise tool identifier")
            continue
        active = [item for item in versions if item.get("installed") is True and item.get("active") is True]
        if len(active) != 1:
            if active:
                manual.append("ambiguous mise tool: " + name)
            continue
        version = active[0].get("version")
        if not isinstance(version, str) or not re.fullmatch(r"[a-zA-Z0-9._+-]+", version):
            manual.append("unsafe mise version: " + name)
            continue
        mise[name] = version
        source = active[0].get("source") or {}
        source_path = source.get("path") if isinstance(source, dict) else None
        if isinstance(source_path, str) and Path(source_path).is_relative_to(Path(home) / ".config/mise"):
            mise_sources[name] = "user"
        elif isinstance(source_path, str) and Path(source_path).is_relative_to(Path("/etc/mise")):
            mise_sources[name] = "system"
        else:
            mise_sources[name] = "unknown"

    installed_uv = {}
    for line in runner.run(["uv", "tool", "list"]).splitlines():
        match = UV_LINE.match(line)
        if match:
            installed_uv[match.group(1)] = match.group(2)
    uv = {}
    for tool, version in installed_uv.items():
        receipt = Path(home) / ".local/share/uv/tools" / tool / "uv-receipt.toml"
        if not receipt.is_file() or receipt.is_symlink():
            manual.append("uv tool requires manual installation: " + tool)
            continue
        try:
            data = tomllib.loads(receipt.read_text())
            requirements = data["tool"]["requirements"]
            if len(requirements) != 1:
                raise ValueError("unsupported requirements")
            requirement = requirements[0]
            name = requirement["name"]
            if set(requirement) != {"name"} or not isinstance(name, str) or not PACKAGE.fullmatch(name):
                raise ValueError("non-PyPI or private requirement")
            uv[tool] = f"{name}=={version}"
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            manual.append("uv tool requires manual installation: " + tool)
    return {"packages": packages, "mise": mise, "mise_sources": mise_sources, "uv": uv}, manual
