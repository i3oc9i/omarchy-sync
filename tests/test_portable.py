import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from omarchy_sync.portable import collect_portable, is_allowed


class FakeRunner:
    def run(self, argv):
        return {("omarchy", "theme", "current"): "Retro 82\n",
                ("omarchy", "font", "current"): "CaskaydiaMono Nerd Font\n"}[tuple(argv)]


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def put(self, name, data="sample"):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_collects_omarchy_hypr_and_webapps_but_not_private_config(self):
        wanted = [
            ".config/omarchy/shell.json",
            ".config/omarchy/plugins/btw.idle/Service.qml",
            ".config/omarchy/hooks/theme-set.d/omazed",
            ".config/omarchy/themes/custom/colors.toml",
            ".config/hypr/bindings.lua",
            ".local/share/applications/WhatsApp.desktop",
            ".local/share/icons/hicolor/256x256/apps/whatsapp.png",
        ]
        for name in wanted[:-2]:
            self.put(name)
        self.put(wanted[-2], "[Desktop Entry]\nType=Application\nExec=omarchy-launch-webapp https://web.whatsapp.com/\nIcon=whatsapp\n")
        self.put(wanted[-1], "icon")
        for excluded in (
            ".config/hypr/monitors.lua", ".config/hypr/xdph.conf",
            ".config/omarchy/hooks/post-update.d/setup-fingerprint.hook",
            ".config/omarchy/shell.json.bak.123", ".config/chromium/Default/Preferences",
            ".config/omarchy/plugins/btw.idle/.env", ".config/omarchy/plugins/btw.idle/token.key",
            ".local/share/applications/Custom.desktop",
            ".local/share/applications/Other.desktop",
        ):
            self.put(excluded, "[Desktop Entry]\nExec=/usr/bin/custom\n" if excluded.endswith(".desktop") else "excluded")
        files, appearance, warnings = collect_portable(self.home, FakeRunner())
        self.assertEqual(set(files), set(wanted))
        self.assertEqual(appearance["theme"], "Retro 82")
        self.assertEqual(appearance["font"], "CaskaydiaMono Nerd Font")
        self.assertTrue(any("Custom.desktop" in warning for warning in warnings))

    def test_rejects_symlink_to_outside_home(self):
        outside = self.home.parent / "external-omarchy-sync-test"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_text("secret")
        link = self.home / ".config/omarchy/shell.json"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        files, _, _ = collect_portable(self.home, FakeRunner())
        self.assertNotIn(".config/omarchy/shell.json", files)

    def test_includes_omarchy_hey_and_zoom_webapp_handlers(self):
        self.put(".local/share/applications/HEY.desktop",
                 "[Desktop Entry]\nExec=omarchy-webapp-handler-hey %u\nIcon=hey\n")
        self.put(".local/share/applications/Zoom.desktop",
                 "[Desktop Entry]\nExec=omarchy-webapp-handler-zoom %u\nIcon=zoom\n")
        self.put(".local/share/applications/Unsafe.desktop",
                 "[Desktop Entry]\nExec=omarchy-webapp-handler-unknown %u\nIcon=unsafe\n")
        files, _, warnings = collect_portable(self.home, FakeRunner())
        self.assertIn(".local/share/applications/HEY.desktop", files)
        self.assertIn(".local/share/applications/Zoom.desktop", files)
        self.assertNotIn(".local/share/applications/Unsafe.desktop", files)
        self.assertTrue(any("Unsafe.desktop" in warning for warning in warnings))

    def test_is_allowed_never_grants_monitor_or_unrelated_config(self):
        self.assertTrue(is_allowed(".config/omarchy/plugins/btw.idle/Service.qml"))
        self.assertFalse(is_allowed(".config/hypr/monitors.lua"))
        self.assertFalse(is_allowed(".config/chromium/Default/Preferences"))
        self.assertFalse(is_allowed(".config/omarchy/plugins/../shell.json"))


if __name__ == "__main__":
    unittest.main()
