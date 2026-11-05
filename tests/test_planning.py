import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.planning import build_plan


class FakeRunner:
    def __init__(self, removed=None):
        self.calls = []
        self.removed = removed or {}

    def run(self, argv):
        self.calls.append(tuple(argv))
        if argv[:3] == ["pacman", "-Rns", "--print"]:
            return self.removed.get(argv[-1], argv[-1]) + "\n"
        if argv[:2] == ["pacman", "-Si"]:
            return "Repository : extra\n"
        if argv == ["omarchy", "theme", "current"]:
            return "Retro 82\n"
        if argv == ["omarchy", "font", "current"]:
            return "CaskaydiaMono Nerd Font\n"
        raise AssertionError(argv)


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.files = {".config/omarchy/shell.json": b'{"idle": {}}'}
        self.manifest = {
            "format_version": 1, "omarchy_version": "4.5.0-3",
            "origin_machine_fingerprint": "master", "username": "btw",
            "packages": {"omarchy": "repo", "chromium": "repo", "wanted-lib": "repo"},
            "mise": {"bun": "1.4.4"}, "uv": {"browser-use": "browser-use==0.13.11"},
            "appearance": {"theme": "Retro 82", "font": "CaskaydiaMono Nerd Font", "background_filename": ""},
            "manual_only": ["uv tool requires manual installation: repos-update"],
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()},
        }
        self.target = {
            "omarchy_version": "4.5.0-3", "machine_fingerprint": "slave", "username": "btw",
            "packages": {"omarchy": "repo", "gedit": "repo", "linux-omarchy": "repo",
                         "nvidia-580xx-dkms": "repo", "intel-ucode": "repo"},
            "mise": {"deno": "2.9.8"}, "uv": {"other": "other==1.0"},
        }

    def test_previews_apps_tools_and_protects_hardware(self):
        runner = FakeRunner()
        plan = build_plan(self.manifest, self.files, self.target, self.home, runner)
        self.assertEqual(plan["packages_install"], ["chromium", "wanted-lib"])
        self.assertEqual(plan["packages_remove"], ["gedit"])
        self.assertTrue(all(name not in plan["packages_remove"] for name in
                            ("linux-omarchy", "nvidia-580xx-dkms", "intel-ucode")))
        self.assertEqual(plan["mise_install"], {"bun": "1.4.4"})
        self.assertEqual(plan["mise_remove"], ["deno"])
        self.assertEqual(plan["uv_install"], {"browser-use": "browser-use==0.13.11"})
        self.assertEqual(plan["uv_remove"], ["other"])
        self.assertEqual(plan["files_write"], [".config/omarchy/shell.json"])
        self.assertTrue(any("repos-update" in item for item in plan["manual_only"]))
        self.assertFalse(plan["blockers"])
        self.assertTrue(all(call[0] in ("pacman", "omarchy") and "--noconfirm" not in call for call in runner.calls))

    def test_rejects_origin_wrong_version_and_wrong_user(self):
        for key, value in (("machine_fingerprint", "master"), ("omarchy_version", "4.0"), ("username", "other")):
            with self.subTest(key=key):
                target = {**self.target, key: value}
                with self.assertRaises(ValueError):
                    build_plan(self.manifest, self.files, target, self.home, FakeRunner())

    def test_transitive_removal_of_wanted_package_requires_manual_review(self):
        plan = build_plan(self.manifest, self.files, self.target, self.home,
                          FakeRunner({"gedit": "gedit\nwanted-lib"}))
        self.assertEqual(plan["packages_remove"], [])
        self.assertTrue(any("gedit" in item for item in plan["manual_only"]))

    def test_appearance_only_applies_when_different(self):
        plan = build_plan(self.manifest, self.files, self.target, self.home, FakeRunner())
        self.assertEqual(plan["appearance_change"], {})
        desired = {**self.manifest, "appearance": {**self.manifest["appearance"], "theme": "Tokyo Night"}}
        changed = build_plan(desired, self.files, self.target, self.home, FakeRunner())
        self.assertEqual(changed["appearance_change"], {"theme": "Tokyo Night"})

    def test_slave_only_webapp_is_removed_and_second_run_is_noop(self):
        app = self.home / ".local/share/applications/WhatsApp.desktop"
        app.parent.mkdir(parents=True)
        app.write_text("[Desktop Entry]\nExec=omarchy-launch-webapp https://web.whatsapp.com/\nIcon=whatsapp\n")
        runner = FakeRunner()
        plan = build_plan(self.manifest, self.files, self.target, self.home, runner)
        self.assertIn(".local/share/applications/WhatsApp.desktop", plan["files_delete"])
        (self.home / ".config/omarchy").mkdir(parents=True)
        (self.home / ".config/omarchy/shell.json").write_bytes(self.files[".config/omarchy/shell.json"])
        synced = {**self.target, "packages": {**self.manifest["packages"], "linux-omarchy": "repo"},
                  "mise": self.manifest["mise"], "uv": self.manifest["uv"]}
        app.unlink()
        repeat = build_plan(self.manifest, self.files, synced, self.home, runner)
        self.assertFalse(repeat["files_write"] or repeat["files_delete"] or repeat["packages_install"] or
                         repeat["packages_remove"] or repeat["mise_install"] or repeat["mise_remove"] or
                         repeat["uv_install"] or repeat["uv_remove"])


if __name__ == "__main__":
    unittest.main()
