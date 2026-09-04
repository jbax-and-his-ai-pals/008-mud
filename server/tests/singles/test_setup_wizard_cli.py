import json
import shutil
import unittest
import uuid
from pathlib import Path

from setup_wizard_cli import run


SOURCE_CONTENT_SET = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestSetupWizardCli(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"setup_wizard_cli_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _content_set(self, root: Path) -> Path:
        package = root / "content_set"
        shutil.copytree(SOURCE_CONTENT_SET, package)
        return package

    def test_generates_config_and_profile_files(self) -> None:
        root = self._case_root()
        config_dir = root / "cfg"
        content_set = self._content_set(root)
        code = run(
            [
                "--preset",
                "creator_sandbox",
                "--server-name",
                "Builder Lab",
                "--content-set",
                str(content_set),
                "--config-dir",
                str(config_dir),
            ]
        )
        self.assertEqual(0, code)
        cfg_path = config_dir / "builder_lab.server_config.json"
        profile_path = content_set / "data" / "profiles" / "builder_lab.profile.json"
        self.assertTrue(cfg_path.exists())
        self.assertTrue(profile_path.exists())
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual("127.0.0.1", cfg["server"]["host"])
        self.assertEqual("all", profile["authoring"]["mode"])

    def test_refuses_overwrite_without_force(self) -> None:
        root = self._case_root()
        config_dir = root / "cfg"
        content_set = self._content_set(root)
        run(
            [
                "--preset",
                "static_world",
                "--server-name",
                "Locked",
                "--content-set",
                str(content_set),
                "--config-dir",
                str(config_dir),
            ]
        )
        with self.assertRaises(FileExistsError):
            run(
                [
                    "--preset",
                    "static_world",
                    "--server-name",
                    "Locked",
                    "--content-set",
                    str(content_set),
                    "--config-dir",
                    str(config_dir),
                ]
            )

    def test_force_allows_overwrite(self) -> None:
        root = self._case_root()
        config_dir = root / "cfg"
        content_set = self._content_set(root)
        run(
            [
                "--preset",
                "social_no_combat",
                "--server-name",
                "Social",
                "--content-set",
                str(content_set),
                "--config-dir",
                str(config_dir),
            ]
        )
        code = run(
            [
                "--preset",
                "social_no_combat",
                "--server-name",
                "Social",
                "--content-set",
                str(content_set),
                "--config-dir",
                str(config_dir),
                "--force",
            ]
        )
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
