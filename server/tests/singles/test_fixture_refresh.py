"""Coverage for toolkit/fixture_refresh.py.

Note: the module's `if __name__ == "__main__": main()` guard is left
untested as unreachable under import-based testing -- it only runs when
the file is invoked directly as a script (consistent with this codebase's
established precedent for such guards)."""

import io
import json
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOLKIT_DIR = _REPO_ROOT / "toolkit"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from fixture_refresh import _copy_tree, _on_rm_error, _safe_rmtree, main, refresh_fixture


class TestFixtureRefresh(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"fixture_refresh_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_clean_source(self, src: Path) -> None:
        """A minimal editor-export tree with nothing to warn/error about:
        empty template catalogs and one self-contained, exit-less room."""
        (src / "items").mkdir(parents=True, exist_ok=True)
        (src / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "regions").mkdir(parents=True, exist_ok=True)
        (src / "magic").mkdir(parents=True, exist_ok=True)
        (src / "quests").mkdir(parents=True, exist_ok=True)
        (src / "items" / "base.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "base.json").write_text("{}", encoding="utf-8")
        (src / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}}}),
            encoding="utf-8",
        )
        (src / "magic" / "base.json").write_text("{}", encoding="utf-8")
        (src / "quests" / "instances.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")

    def test_safe_rmtree_is_a_noop_on_missing_path(self) -> None:
        root = self._case_root()
        missing = root / "does_not_exist"
        _safe_rmtree(missing)  # must not raise
        self.assertFalse(missing.exists())

    def test_on_rm_error_clears_readonly_and_retries(self) -> None:
        import os
        import stat

        root = self._case_root()
        stubborn = root / "readonly.txt"
        stubborn.write_text("locked", encoding="utf-8")
        os.chmod(stubborn, stat.S_IREAD)

        _on_rm_error(os.remove, str(stubborn), None)

        self.assertFalse(stubborn.exists())

    def test_copy_tree_replaces_existing_destination(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        src.mkdir()
        (src / "new.txt").write_text("new", encoding="utf-8")
        dst.mkdir()
        (dst / "stale.txt").write_text("stale", encoding="utf-8")

        _copy_tree(src, dst)

        self.assertTrue((dst / "new.txt").exists())
        self.assertFalse((dst / "stale.txt").exists())

    def test_refresh_fixture_requires_a_fixture_name(self) -> None:
        root = self._case_root()
        with self.assertRaisesRegex(ValueError, "fixture_name is required"):
            refresh_fixture(
                source_root=root / "src",
                latest_root=root / "latest",
                fixture_root=root / "fixtures",
                fixture_name="   ",
                tmp_root=root / "tmp",
            )

    def test_strict_refresh_succeeds_on_clean_source_and_writes_marker(self) -> None:
        root = self._case_root()
        src = root / "src"
        self._write_clean_source(src)

        result = refresh_fixture(
            source_root=src,
            latest_root=root / "latest",
            fixture_root=root / "fixtures",
            fixture_name="my_fixture",
            tmp_root=root / "tmp",
            strict=True,
        )

        self.assertEqual("ok", result["status"])
        self.assertTrue(result["replaced_primary_target"])
        self.assertNotIn("replacement_error", result)

        fixture_target = Path(result["fixture_selected_target"])
        self.assertTrue((fixture_target / "regions" / "town.json").exists())
        self.assertTrue((fixture_target / "items" / "base.json").exists())

        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual([], report.get("warnings", []))
        self.assertEqual([], report.get("missing", []))

        marker = json.loads((root / "fixtures" / "LATEST_REFRESH.json").read_text(encoding="utf-8"))
        self.assertEqual(result, marker)

    def test_strict_refresh_raises_on_missing_source_directories(self) -> None:
        root = self._case_root()
        src = root / "src"
        src.mkdir()  # empty: every copy rule will be reported missing

        with self.assertRaisesRegex(RuntimeError, "Strict refresh failed"):
            refresh_fixture(
                source_root=src,
                latest_root=root / "latest",
                fixture_root=root / "fixtures",
                fixture_name="my_fixture",
                tmp_root=root / "tmp",
                strict=True,
            )

        # The report is still written even though the refresh failed, so a
        # caller can inspect why -- only the fixture copy/marker step is skipped.
        work_dirs = list((root / "tmp").glob("fixture_refresh_*"))
        self.assertEqual(1, len(work_dirs))
        self.assertTrue((work_dirs[0] / "report.json").exists())
        self.assertFalse((root / "fixtures" / "LATEST_REFRESH.json").exists())

    def test_non_strict_refresh_succeeds_despite_missing_source_directories(self) -> None:
        root = self._case_root()
        src = root / "src"
        src.mkdir()

        result = refresh_fixture(
            source_root=src,
            latest_root=root / "latest",
            fixture_root=root / "fixtures",
            fixture_name="my_fixture",
            tmp_root=root / "tmp",
            strict=False,
        )

        self.assertEqual("ok", result["status"])
        self.assertTrue((root / "fixtures" / "LATEST_REFRESH.json").exists())

    def test_primary_copy_failure_falls_back_to_a_secondary_target(self) -> None:
        root = self._case_root()
        src = root / "src"
        self._write_clean_source(src)

        with patch(
            "fixture_refresh._copy_tree", side_effect=[OSError("locked by another process"), None],
        ):
            result = refresh_fixture(
                source_root=src,
                latest_root=root / "latest",
                fixture_root=root / "fixtures",
                fixture_name="my_fixture",
                tmp_root=root / "tmp",
                strict=True,
            )

        self.assertFalse(result["replaced_primary_target"])
        self.assertEqual("locked by another process", result["replacement_error"])
        self.assertNotEqual(result["fixture_primary_target"], result["fixture_selected_target"])
        self.assertTrue(str(result["fixture_selected_target"]).startswith(result["fixture_primary_target"] + "__refresh_"))

    def test_main_parses_args_and_prints_result_json(self) -> None:
        root = self._case_root()
        src = root / "src"
        self._write_clean_source(src)

        argv = [
            "fixture_refresh.py",
            "--source", str(src),
            "--latest-root", str(root / "latest"),
            "--fixture-root", str(root / "fixtures"),
            "--fixture-name", "cli_fixture",
            "--tmp-root", str(root / "tmp"),
        ]
        buf = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            main()

        # validate_tree() also prints its own diagnostics line(s); the CLI's
        # actual result is always the final line.
        last_line = [line for line in buf.getvalue().splitlines() if line.strip()][-1]
        printed = json.loads(last_line)
        self.assertEqual("ok", printed["status"])
        self.assertTrue((root / "fixtures" / "cli_fixture").exists())

    def test_main_no_strict_flag_disables_strict_mode(self) -> None:
        root = self._case_root()
        src = root / "src"
        src.mkdir()  # would fail strict mode

        argv = [
            "fixture_refresh.py",
            "--source", str(src),
            "--latest-root", str(root / "latest"),
            "--fixture-root", str(root / "fixtures"),
            "--fixture-name", "cli_fixture",
            "--tmp-root", str(root / "tmp"),
            "--no-strict",
        ]
        buf = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            main()  # must not raise

        last_line = [line for line in buf.getvalue().splitlines() if line.strip()][-1]
        printed = json.loads(last_line)
        self.assertEqual("ok", printed["status"])


if __name__ == "__main__":
    unittest.main()
