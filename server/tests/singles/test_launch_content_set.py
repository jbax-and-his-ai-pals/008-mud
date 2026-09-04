import json
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"


class TestLaunchContentSet(unittest.TestCase):
    def _dry_run(self, transport: str) -> dict:
        command = [
            sys.executable,
            str(REPOSITORY_ROOT / "server" / "launch_content_set.py"),
            "--transport",
            transport,
            "--dry-run",
        ]
        result = subprocess.run(command, capture_output=True, text=True, cwd=str(REPOSITORY_ROOT), check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_default_tcp_launches_fantasy_frontier(self) -> None:
        payload = self._dry_run("tcp")
        self.assertEqual(str(FANTASY_FRONTIER.resolve()), payload["content_set"])
        self.assertEqual(str((FANTASY_FRONTIER / "content_set.manifest.json").resolve()), payload["manifest"])
        self.assertIn(str(REPOSITORY_ROOT / "server" / "poc_server.py"), payload["command"])
        self.assertIn("--content-set", payload["command"])

    def test_websocket_launches_selected_content_set(self) -> None:
        payload = self._dry_run("ws")
        self.assertIn(str(REPOSITORY_ROOT / "server" / "poc_ws_server.py"), payload["command"])
        self.assertIn(str(FANTASY_FRONTIER.resolve()), payload["command"])

    def test_missing_manifest_is_a_clear_error(self) -> None:
        missing = REPOSITORY_ROOT / "server" / "tests" / "_tmp" / "missing_content_set"
        command = [
            sys.executable,
            str(REPOSITORY_ROOT / "server" / "launch_content_set.py"),
            "--content-set",
            str(missing),
            "--dry-run",
        ]
        result = subprocess.run(command, capture_output=True, text=True, cwd=str(REPOSITORY_ROOT), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Content-set manifest not found", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
