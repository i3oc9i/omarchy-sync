import io
import json
import tarfile
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.archive import read_archive, write_archive


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {
            "format_version": 1,
            "omarchy_version": "4.5.0-3",
            "origin_machine_fingerprint": "master",
            "username": "btw",
            "packages": {},
            "mise": {},
            "uv": {},
            "appearance": {},
            "manual_only": [],
            "files": {},
        }

    def make_tar(self, names):
        output = self.root / "snapshot.tar.gz"
        with tarfile.open(output, "w:gz") as tar:
            for name, value in names:
                info = tarfile.TarInfo(name)
                if isinstance(value, tuple):
                    info.type = tarfile.SYMTYPE
                    info.linkname = value[0]
                    tar.addfile(info)
                else:
                    info.size = len(value)
                    tar.addfile(info, io.BytesIO(value))
        return output

    def sample(self):
        source = self.root / "shell.json"
        source.write_bytes(b'{"idle": 150}')
        output = self.root / "snapshot.tar.gz"
        write_archive(output, self.manifest, {".config/omarchy/shell.json": source})
        return output

    def test_round_trip_preserves_file_and_sha256(self):
        manifest, files = read_archive(self.sample())
        self.assertEqual(files, {".config/omarchy/shell.json": b'{"idle": 150}'})
        self.assertEqual(len(manifest["files"][".config/omarchy/shell.json"]), 64)

    def test_modified_bytes_fail_checksum(self):
        archive = self.sample()
        with tarfile.open(archive, "r:gz") as tar:
            manifest = tar.extractfile("manifest.json").read()
        self.make_tar([
            ("manifest.json", manifest),
            ("files/.config/omarchy/shell.json", b"tampered"),
        ])
        with self.assertRaisesRegex(ValueError, "hash"):
            read_archive(archive)

    def test_traversal_and_absolute_paths_rejected(self):
        manifest = json.dumps(self.manifest).encode()
        for unsafe in ("files/../outside", "/absolute", "files/a/../../outside"):
            with self.subTest(path=unsafe):
                archive = self.make_tar([("manifest.json", manifest), (unsafe, b"x")])
                with self.assertRaises(ValueError):
                    read_archive(archive)
                self.assertFalse((self.root / "outside").exists())

    def test_duplicate_members_rejected(self):
        archive = self.make_tar([("manifest.json", b"{}"), ("manifest.json", b"{}")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            read_archive(archive)

    def test_symlink_member_rejected(self):
        archive = self.make_tar([("manifest.json", b"{}"), ("files/link", ("/etc/passwd",))])
        with self.assertRaisesRegex(ValueError, "regular"):
            read_archive(archive)

    def test_unsupported_format_rejected(self):
        archive = self.sample()
        with tarfile.open(archive, "r:gz") as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read())
            data = tar.extractfile("files/.config/omarchy/shell.json").read()
        manifest["format_version"] = 999
        self.make_tar([("manifest.json", json.dumps(manifest).encode()),
                       ("files/.config/omarchy/shell.json", data)])
        with self.assertRaisesRegex(ValueError, "version"):
            read_archive(archive)

    def test_malformed_manifest_types_and_option_like_tools_rejected(self):
        for field, value in (("packages", []), ("mise", {"--evil": "1"}),
                             ("uv", {"helper": "--force"}), ("modes", {"x": 0o7777})):
            with self.subTest(field=field):
                manifest = {**self.manifest, field: value}
                archive = self.make_tar([("manifest.json", json.dumps(manifest).encode())])
                with self.assertRaises(ValueError):
                    read_archive(archive)


if __name__ == "__main__":
    unittest.main()
