import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.cli import run_command


class FakeRunner:
    def __init__(self, home, version="4.5.0-3", packages=None, fail_install=False):
        self.home = home
        self.version = version
        self.packages = packages or {"omarchy"}
        self.fail_install = fail_install
        self.calls = []

    def run(self, argv):
        self.calls.append(tuple(argv))
        if argv == ["omarchy", "version"]:
            return self.version + "\n"
        if argv == ["omarchy", "theme", "current"]:
            return "Retro 82\n"
        if argv == ["omarchy", "font", "current"]:
            return "CaskaydiaMono Nerd Font\n"
        if argv == ["pacman", "-Qqe"]:
            return "\n".join(sorted(self.packages)) + "\n"
        if argv == ["pacman", "-Qm"]:
            return ""
        if argv == ["mise", "ls", "--json"]:
            return "{}"
        if argv == ["uv", "tool", "list"]:
            return "repos-update v2.2.0\n" if "chromium" in self.packages else ""
        if argv[:2] == ["pacman", "-Si"]:
            return "Repository: extra\n"
        if argv[:3] == ["pacman", "-Rns", "--print"]:
            return argv[-1] + "\n"
        if argv[:3] == ["omarchy", "pkg", "add"]:
            if self.fail_install:
                raise RuntimeError("download failed")
            self.packages.update(argv[3:])
            return ""
        if argv[:3] == ["omarchy", "pkg", "drop"]:
            if not (self.home / ".config/omarchy/shell.json").is_file():
                raise AssertionError("removed packages before copying files")
            self.packages.difference_update(argv[3:])
            return ""
        return ""


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / "master"
        self.slave = self.root / "slave"
        self.master.mkdir()
        self.slave.mkdir()
        source = self.master / ".config/omarchy/shell.json"
        source.parent.mkdir(parents=True)
        source.write_text('{"idle": {"screensaver": 150}}')
        self.receipt = self.master / ".local/share/uv/tools/repos-update/uv-receipt.toml"
        self.receipt.parent.mkdir(parents=True)
        self.receipt.write_text('[[tool.requirements]]\nname = "repos-update"\ndirectory = "file:///home/btw/Projects/tools/repos_update"\n')
        self.archive = self.root / "snapshot.tar.gz"
        self.master_runner = FakeRunner(self.master, packages={"omarchy", "chromium"})
        self.slave_runner = FakeRunner(self.slave, packages={"omarchy", "gedit"})

    def export(self):
        self.assertEqual(run_command(["export", str(self.archive)], self.master, self.master_runner,
                                     lambda _: "", "master"), 0)

    def test_export_and_plan_do_not_change_either_laptop(self):
        self.export()
        self.assertEqual(run_command(["plan", str(self.archive)], self.slave, self.slave_runner,
                                     lambda _: "", "slave"), 0)
        self.assertFalse((self.slave / ".config/omarchy/shell.json").exists())
        self.assertEqual(self.slave_runner.packages, {"omarchy", "gedit"})

    def test_rejection_leaves_slave_unchanged(self):
        self.export()
        self.assertEqual(run_command(["apply", str(self.archive)], self.slave, self.slave_runner,
                                     lambda _: "no", "slave"), 1)
        self.assertEqual(self.slave_runner.packages, {"omarchy", "gedit"})
        self.assertFalse((self.slave / ".config/omarchy/shell.json").exists())

    def test_confirmed_apply_installs_then_copies_then_removes_and_reapply_is_noop(self):
        self.export()
        self.assertEqual(run_command(["apply", str(self.archive)], self.slave, self.slave_runner,
                                     lambda _: "APPLY", "slave"), 0)
        self.assertEqual(self.slave_runner.packages, {"omarchy", "chromium"})
        self.assertEqual((self.slave / ".config/omarchy/shell.json").read_text(),
                         '{"idle": {"screensaver": 150}}')
        calls = self.slave_runner.calls
        self.assertLess(calls.index(("omarchy", "pkg", "add", "chromium")),
                        calls.index(("omarchy", "pkg", "drop", "gedit")))
        self.assertEqual(run_command(["apply", str(self.archive)], self.slave, self.slave_runner,
                                     lambda _: "APPLY", "slave"), 0)
        self.assertEqual(self.slave_runner.calls.count(("omarchy", "pkg", "drop", "gedit")), 1)

    def test_failed_install_prevents_removal(self):
        self.export()
        self.slave_runner.fail_install = True
        self.assertNotEqual(run_command(["apply", str(self.archive)], self.slave, self.slave_runner,
                                        lambda _: "APPLY", "slave"), 0)
        self.assertNotIn(("omarchy", "pkg", "drop", "gedit"), self.slave_runner.calls)

    def test_export_reports_local_uv_tool_without_copying_project(self):
        self.export()
        from omarchy_sync.archive import read_archive
        manifest, files = read_archive(self.archive)
        self.assertTrue(any("repos-update" in item for item in manifest["manual_only"]))
        self.assertNotIn("/home/btw/Projects", json.dumps((manifest, list(files))))

    def test_version_mismatch_and_origin_machine_block_apply(self):
        self.export()
        self.slave_runner.version = "4.0"
        self.assertNotEqual(run_command(["apply", str(self.archive)], self.slave, self.slave_runner,
                                        lambda _: "APPLY", "slave"), 0)
        self.assertNotEqual(run_command(["apply", str(self.archive)], self.master, self.master_runner,
                                        lambda _: "APPLY", "master"), 0)
        self.assertEqual(self.slave_runner.packages, {"omarchy", "gedit"})


if __name__ == "__main__":
    unittest.main()
