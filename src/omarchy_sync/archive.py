import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
from pathlib import Path

MAX_FILES = 2048
MAX_BYTES = 512 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
REQUIRED = {"format_version", "omarchy_version", "origin_machine_fingerprint", "username",
            "packages", "mise", "uv", "appearance", "manual_only", "files"}
PKG = re.compile(r"^[a-zA-Z0-9@._+][a-zA-Z0-9@._+-]*$")
MISE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_:+./@-]*$")
UV_SPEC = re.compile(r"^[a-zA-Z0-9._-]+==[a-zA-Z0-9.!+_-]+$")


def safe_name(name: str) -> bool:
    return (bool(name) and not name.startswith("/") and "\\" not in name and "\x00" not in name
            and all(part not in ("", ".", "..") for part in name.split("/")))


def checked_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict) or not REQUIRED <= manifest.keys():
        raise ValueError("invalid manifest fields")
    if type(manifest["format_version"]) is not int or manifest["format_version"] != 1:
        raise ValueError("unsupported archive version")
    if not isinstance(manifest["files"], dict) or len(manifest["files"]) > MAX_FILES:
        raise ValueError("invalid file inventory")
    for name, digest in manifest["files"].items():
        if not isinstance(name, str) or not safe_name(name) or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("invalid file entry")
    for key in ("omarchy_version", "origin_machine_fingerprint", "username"):
        value = manifest[key]
        if not isinstance(value, str) or not value or len(value) > 128 or any(c in value for c in "\r\n\x00"):
            raise ValueError("invalid " + key)
    if manifest["username"] != "btw":
        raise ValueError("unexpected username")
    for key, allowed in (("packages", {"repo", "local"}), ("mise", None), ("uv", None)):
        value = manifest[key]
        if not isinstance(value, dict) or len(value) > 4096:
            raise ValueError("invalid " + key)
        for name, detail in value.items():
            if not isinstance(name, str) or not (MISE if key == "mise" else PKG).fullmatch(name) or "://" in name:
                raise ValueError("invalid " + key + " name")
            if key == "packages":
                valid = detail in allowed if isinstance(detail, str) else False
            elif key == "mise":
                valid = isinstance(detail, str) and bool(re.fullmatch(r"[a-zA-Z0-9._+-]+", detail))
            else:
                valid = isinstance(detail, str) and bool(UV_SPEC.fullmatch(detail))
            if not valid:
                raise ValueError("invalid " + key + " spec")
    if not isinstance(manifest["appearance"], dict) or not {"theme", "font", "background_filename"} <= manifest["appearance"].keys():
        # Empty appearance is permitted in archive-only tests, but not in a real export.
        if manifest["appearance"] != {}:
            raise ValueError("invalid appearance")
    for key, value in manifest["appearance"].items():
        if key not in {"theme", "font", "background_filename"} or not isinstance(value, str) or len(value) > 256 or any(c in value for c in "/\r\n\x00"):
            raise ValueError("invalid appearance value")
    if not isinstance(manifest["manual_only"], list) or any(not isinstance(w, str) or len(w) > 500 for w in manifest["manual_only"]):
        raise ValueError("invalid manual-only inventory")
    modes = manifest.get("modes", {})
    if not isinstance(modes, dict) or not modes.keys() <= manifest["files"].keys() or any(type(mode) is not int or not 0 <= mode <= 0o777 for mode in modes.values()):
        raise ValueError("invalid file modes")


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def write_archive(output: Path, manifest: dict, files: dict[str, Path]) -> None:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("archive output already exists")
    archive_manifest = {**manifest, "files": {}}
    payload = {}
    modes = {}
    for name, path in sorted(files.items()):
        if not safe_name(name) or not Path(path).is_file() or Path(path).is_symlink():
            raise ValueError("unsafe source file")
        content = Path(path).read_bytes()
        payload[name] = content
        modes[name] = stat.S_IMODE(Path(path).stat().st_mode)
        archive_manifest["files"][name] = hashlib.sha256(content).hexdigest()
    archive_manifest["modes"] = modes
    checked_manifest(archive_manifest)
    if sum(map(len, payload.values())) > MAX_BYTES:
        raise ValueError("archive too large")
    encoded = json.dumps(archive_manifest, sort_keys=True).encode()
    if len(encoded) > MAX_MANIFEST:
        raise ValueError("manifest too large")
    fd, temporary = tempfile.mkstemp(prefix=".omarchy-sync-", dir=output.parent)
    os.close(fd)
    try:
        with tarfile.open(temporary, "w:gz") as tar:
            for name, data in [("manifest.json", encoded), *[("files/" + n, b) for n, b in payload.items()]]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o600
                tar.addfile(info, io.BytesIO(data))
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_archive(path: Path) -> tuple[dict, dict[str, bytes]]:
    entries = {}
    total = 0
    try:
        with tarfile.open(path, "r:gz") as tar:
            for member in tar:
                if member.name in entries:
                    raise ValueError("duplicate archive member")
                if not safe_name(member.name):
                    raise ValueError("unsafe archive path")
                if not member.isfile():
                    raise ValueError("only regular archive entries are allowed")
                if member.name != "manifest.json" and not member.name.startswith("files/"):
                    raise ValueError("unexpected archive entry")
                if member.size < 0 or member.size > MAX_BYTES:
                    raise ValueError("oversized archive member")
                total += member.size
                if total > MAX_BYTES + MAX_MANIFEST or len(entries) >= MAX_FILES + 1:
                    raise ValueError("archive too large")
                if member.name == "manifest.json" and member.size > MAX_MANIFEST:
                    raise ValueError("manifest too large")
                stream = tar.extractfile(member)
                if stream is None:
                    raise ValueError("missing archive content")
                entries[member.name] = stream.read(member.size + 1)
                if len(entries[member.name]) != member.size:
                    raise ValueError("truncated archive member")
    except (tarfile.TarError, OSError, UnicodeError) as exc:
        raise ValueError("invalid archive") from exc
    if "manifest.json" not in entries:
        raise ValueError("missing manifest")
    try:
        manifest = json.loads(entries.pop("manifest.json"), object_pairs_hook=_json_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid manifest JSON") from exc
    checked_manifest(manifest)
    files = {}
    for name, content in entries.items():
        relative = name.removeprefix("files/")
        if not name.startswith("files/") or relative not in manifest["files"]:
            raise ValueError("unexpected archive file")
        if hashlib.sha256(content).hexdigest() != manifest["files"][relative]:
            raise ValueError("file hash mismatch")
        files[relative] = content
    if set(files) != set(manifest["files"]):
        raise ValueError("missing archive file")
    return manifest, files
