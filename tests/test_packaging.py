import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("uv"), "uv is required for packaging verification")
class PackagingTests(unittest.TestCase):
    def test_built_wheel_installs_a_working_cli(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            root = Path(directory)
            dist = root / "dist"
            build = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(dist)],
                                   cwd=PROJECT, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            wheels = list(dist.glob("omarchy_sync-*.whl"))
            self.assertEqual(len(wheels), 1)

            environment = {**os.environ, "UV_TOOL_DIR": str(root / "tools"),
                           "UV_TOOL_BIN_DIR": str(root / "bin"),
                           "UV_PYTHON_DOWNLOADS": "never"}
            subprocess.run(["uv", "tool", "install", "--python", sys.executable, str(wheels[0])],
                           env=environment, check=True, capture_output=True, text=True)
            command = root / "bin" / "omarchy-sync"
            result = subprocess.run([str(command), "--help"],
                                    check=True, capture_output=True, text=True)
            self.assertIn("{export,plan,apply}", result.stdout)


if __name__ == "__main__":
    unittest.main()
