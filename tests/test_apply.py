import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.apply import apply_files


class FakeRunner:
    def __init__(self, home, fail_on=None):
        self.home = home
        self.calls = []
        self.fail_on = fail_on

    def run(self, argv):
        self.calls.append(tuple(argv))
        if argv == ["omarchy", "theme", "set", "Retro 82"]:
            if (self.home / ".config/omarchy/hooks/theme-set.d/new-hook").exists():
                raise AssertionError("new theme hook executed during import")
        if argv == self.fail_on:
            raise RuntimeError("simulated failure")
        return ""


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.plan = {"files_write": [], "files_delete": [], "appearance": {}, "appearance_change": {}, "modes": {}}

    def put(self, name, data):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_backs_up_overwritten_and_removed_files_without_touching_machine_config(self):
        shell = ".config/omarchy/shell.json"
        webapp = ".local/share/applications/WhatsApp.desktop"
        monitor = self.put(".config/hypr/monitors.lua", b"machine monitor")
        browser = self.put(".config/chromium/Default/Preferences", b"user browser")
        self.put(shell, b'{"old": true}')
        self.put(webapp, b"[Desktop Entry]\nExec=omarchy-launch-webapp https://web.whatsapp.com/\n")
        self.plan.update(files_write=[shell], files_delete=[webapp])
        backup = apply_files(self.plan, {shell: b'{"new": true}'}, self.home, FakeRunner(self.home))
        self.assertEqual((backup / shell).read_bytes(), b'{"old": true}')
        self.assertTrue((backup / webapp).is_file())
        self.assertEqual((self.home / shell).read_bytes(), b'{"new": true}')
        self.assertFalse((self.home / webapp).exists())
        self.assertEqual(monitor.read_bytes(), b"machine monitor")
        self.assertEqual(browser.read_bytes(), b"user browser")

    def test_refuses_symlinked_destination_parent(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.home / ".config").symlink_to(outside, target_is_directory=True)
        shell = ".config/omarchy/shell.json"
        self.plan["files_write"] = [shell]
        with self.assertRaises(ValueError):
            apply_files(self.plan, {shell: b"{}"}, self.home, FakeRunner(self.home))
        self.assertFalse((outside / "omarchy/shell.json").exists())

    def test_applies_theme_before_importing_theme_hook(self):
        hook = ".config/omarchy/hooks/theme-set.d/new-hook"
        self.plan.update(files_write=[hook], appearance_change={"theme": "Retro 82"})
        runner = FakeRunner(self.home)
        apply_files(self.plan, {hook: b"#!/bin/sh\n"}, self.home, runner)
        self.assertIn(("omarchy", "theme", "set", "Retro 82"), runner.calls)
        self.assertTrue((self.home / hook).exists())

    def test_theme_failure_keeps_backup_and_does_not_remove_webapp(self):
        shell = ".config/omarchy/shell.json"
        webapp = ".local/share/applications/WhatsApp.desktop"
        self.put(shell, b'{"old": true}')
        self.put(webapp, b"[Desktop Entry]\nExec=omarchy-launch-webapp https://web.whatsapp.com/\n")
        self.plan.update(files_write=[shell], files_delete=[webapp], appearance_change={"theme": "Retro 82"})
        with self.assertRaises(RuntimeError):
            apply_files(self.plan, {shell: b'{"new": true}'}, self.home,
                        FakeRunner(self.home, ["omarchy", "theme", "set", "Retro 82"]))
        backups = list((self.home / ".local/state/omarchy-personalization-sync/backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / shell).read_bytes(), b'{"old": true}')
        self.assertTrue((self.home / webapp).exists())

    def test_empty_plan_creates_no_backup(self):
        self.assertIsNone(apply_files(self.plan, {}, self.home, FakeRunner(self.home)))


if __name__ == "__main__":
    unittest.main()
