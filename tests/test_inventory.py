import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.inventory import collect_inventory


class FakeRunner:
    def __init__(self):
        self.outputs = {
            ("pacman", "-Qqe"): "omarchy\nchromium\ncustom-local\n",
            ("pacman", "-Qm"): "custom-local 1.0\n",
            ("mise", "ls", "--json"): json.dumps({
                "bun": [{"version": "1.4.4", "installed": True, "active": True},
                        {"version": "1.4.3", "installed": True, "active": False}],
                "unused": [{"version": "2", "installed": False, "active": False}],
            }),
            ("uv", "tool", "list"): "browser-use v0.13.11\n- browser-use\nrepos-update v2.2.0\n- repos-update\nsecret-tool v1.0\n",
        }

    def run(self, argv):
        return self.outputs[tuple(argv)]


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.tools = self.home / ".local/share/uv/tools"

    def receipt(self, name, contents):
        directory = self.tools / name
        directory.mkdir(parents=True)
        (directory / "uv-receipt.toml").write_text(contents)

    def test_exports_only_explicit_packages_active_mise_and_reinstallable_uv(self):
        self.receipt("browser-use", '[[tool.requirements]]\nname = "browser-use"\n')
        self.receipt("repos-update", '[[tool.requirements]]\nname = "repos-update"\ndirectory = "file:///home/btw/Projects/tools/repos_update"\n')
        self.receipt("secret-tool", '[[tool.requirements]]\nname = "secret-tool"\nurl = "https://token:private@example.com/src.whl"\n')
        inventory, manual = collect_inventory(self.home, FakeRunner())
        self.assertEqual(inventory["packages"], {"omarchy": "repo", "chromium": "repo", "custom-local": "local"})
        self.assertEqual(inventory["mise"], {"bun": "1.4.4"})
        self.assertEqual(inventory["uv"], {"browser-use": "browser-use==0.13.11"})
        self.assertTrue(any("repos-update" in item for item in manual))
        self.assertTrue(any("secret-tool" in item for item in manual))
        self.assertNotIn("private", json.dumps((inventory, manual)))
        self.assertNotIn("/home/btw/Projects/tools", json.dumps((inventory, manual)))

    def test_ignores_uv_tools_without_receipts(self):
        inventory, manual = collect_inventory(self.home, FakeRunner())
        self.assertEqual(inventory["uv"], {})
        self.assertTrue(any("browser-use" in item for item in manual))

    def test_tracks_mise_config_origin_before_allowing_removal(self):
        runner = FakeRunner()
        runner.outputs[("mise", "ls", "--json")] = json.dumps({
            "local": [{"version": "1", "installed": True, "active": True,
                       "source": {"path": str(self.home / ".config/mise/config.toml")}}],
            "system": [{"version": "2", "installed": True, "active": True,
                        "source": {"path": "/etc/mise/conf.d/omarchy-tools.toml"}}],
        })
        inventory, _ = collect_inventory(self.home, runner)
        self.assertEqual(inventory["mise_sources"], {"local": "user", "system": "system"})

    def test_no_foreign_packages_is_normal_on_pacman_exit_one(self):
        class EmptyForeign(FakeRunner):
            def run(self, argv):
                if argv == ["pacman", "-Qm"]:
                    raise subprocess.CalledProcessError(1, argv, output="")
                return super().run(argv)

        inventory, _ = collect_inventory(self.home, EmptyForeign())
        self.assertEqual(inventory["packages"]["chromium"], "repo")


if __name__ == "__main__":
    unittest.main()
