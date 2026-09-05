"""Coverage for toolkit/pack_tool.py.

Note: two branches are left untested as unreachable:
- main()'s `elif args.command == "export":` falling through without
  taking either the "validate" or "export" body -- the subparsers are
  configured with `required=True` and only "validate"/"export" choices,
  so argparse itself guarantees args.command is always one of the two by
  the time main() reaches this dispatch.
- the module's `if __name__ == "__main__": main()` guard, which only runs
  when the file is invoked directly as a script (consistent with this
  codebase's established precedent for such guards)."""

import io
import json
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import pack_tool


class TestPackToolCompatibility(unittest.TestCase):
    def test_version_range_logic(self) -> None:
        self.assertTrue(pack_tool.version_in_range("1.0", "1.0", "1.0"))
        self.assertTrue(pack_tool.version_in_range("1.2", "1.0", "2.0"))
        self.assertFalse(pack_tool.version_in_range("2.1", "1.0", "2.0"))

    def test_version_range_rejects_unparseable_version(self) -> None:
        self.assertFalse(pack_tool.version_in_range("abc", "1.0", "2.0"))

    def test_validate_pack_rejects_non_string_compat_field(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": 1, "runtime_api_min": "1.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_blank_compat_field(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "   ", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_missing_compat_by_default(self) -> None:
        payload = {
            "theme_id": "x",
            "display_name": "X",
            "ui_strings": {},
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            valid = pack_tool.validate_pack(Path("dummy.json"), {"ui_strings": {}}, strict=False)
        self.assertFalse(valid)

    def test_validate_pack_accepts_valid_compat(self) -> None:
        payload = {
            "theme_id": "x",
            "display_name": "X",
            "pack_spec_version": "1",
            "runtime_api_min": "1.0",
            "runtime_api_max": "1.0",
            "ui_strings": {},
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            valid = pack_tool.validate_pack(Path("dummy.json"), {"ui_strings": {}}, strict=False)
        self.assertTrue(valid)

    def test_parse_version_rejects_malformed_input(self) -> None:
        self.assertIsNone(pack_tool.parse_version(""))
        self.assertIsNone(pack_tool.parse_version("  "))
        self.assertIsNone(pack_tool.parse_version("1.a"))
        self.assertIsNone(pack_tool.parse_version("1.."))
        self.assertEqual((1, 2, 3), pack_tool.parse_version("1.2.3"))

    def test_validate_pack_rejects_missing_required_fields(self) -> None:
        payload = {"pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0"}
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}, require_compat=True))

    def test_validate_pack_rejects_non_string_required_field(self) -> None:
        payload = {
            "theme_id": 123,
            "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_unsupported_pack_spec_version(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "2", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_non_numeric_runtime_api_bounds(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "abc", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_min_greater_than_max(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "2.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_rejects_out_of_range_runtime_api(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}, runtime_api="2.0"))

    def test_validate_pack_missing_compat_is_only_a_warning_when_allowed(self) -> None:
        payload = {"theme_id": "x", "display_name": "X"}
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertTrue(pack_tool.validate_pack(Path("dummy.json"), {}, require_compat=False))

    def test_validate_pack_dict_section_must_be_an_object(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
            "ui_strings": ["not", "a", "dict"],
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))

    def test_validate_pack_unknown_section_key_is_a_warning_not_error(self) -> None:
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
            "ui_strings": {"extra_key": "value"},
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertTrue(pack_tool.validate_pack(Path("dummy.json"), {"ui_strings": {}}, strict=False))

    def test_validate_pack_strict_mode_requires_full_key_coverage(self) -> None:
        reference = {"ui_strings": {"greeting": "hi", "farewell": "bye"}}
        payload = {
            "theme_id": "x", "display_name": "X",
            "pack_spec_version": "1", "runtime_api_min": "1.0", "runtime_api_max": "1.0",
            "ui_strings": {"greeting": "hi"},
        }
        with patch("toolkit.pack_tool.load_json", return_value=payload):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), reference, strict=True))
            self.assertTrue(pack_tool.validate_pack(Path("dummy.json"), reference, strict=False))

    def test_validate_pack_returns_false_when_load_json_fails(self) -> None:
        with patch("toolkit.pack_tool.load_json", return_value=None):
            self.assertFalse(pack_tool.validate_pack(Path("dummy.json"), {}))


class TestPackToolFilesystem(unittest.TestCase):
    """Tests that exercise load_json/export_pack/main against real files,
    since those paths depend on actual I/O rather than pure logic."""

    VALID_PACK = {
        "theme_id": "sample",
        "display_name": "Sample",
        "pack_spec_version": "1",
        "runtime_api_min": "1.0",
        "runtime_api_max": "1.0",
        "ui_strings": {"greeting": "hi"},
    }

    def _case_root(self) -> Path:
        root = REPO_ROOT / "server" / "tmp" / f"pack_tool_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_load_json_returns_none_on_malformed_file(self) -> None:
        root = self._case_root()
        bad = root / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = pack_tool.load_json(bad)
        self.assertIsNone(result)
        self.assertIn("Error loading JSON", buf.getvalue())

    def test_export_pack_writes_minified_output_for_a_valid_pack(self) -> None:
        root = self._case_root()
        target = root / "sample.json"
        target.write_text(json.dumps(self.VALID_PACK), encoding="utf-8")
        out_dir = root / "dist"

        with redirect_stdout(io.StringIO()):
            success = pack_tool.export_pack(target, out_dir, {"ui_strings": {}})

        self.assertTrue(success)
        out_file = out_dir / "sample_export.json"
        self.assertTrue(out_file.exists())
        self.assertEqual(self.VALID_PACK, json.loads(out_file.read_text(encoding="utf-8")))

    def test_export_pack_reports_failure_when_write_raises(self) -> None:
        root = self._case_root()
        target = root / "sample.json"
        target.write_text(json.dumps(self.VALID_PACK), encoding="utf-8")
        out_dir = root / "dist"

        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("toolkit.pack_tool.json.dump", side_effect=OSError("disk full")):
                success = pack_tool.export_pack(target, out_dir, {"ui_strings": {}})

        self.assertFalse(success)
        self.assertIn("Export failed", buf.getvalue())

    def test_export_pack_fails_and_writes_nothing_for_an_invalid_pack(self) -> None:
        root = self._case_root()
        target = root / "invalid.json"
        target.write_text(json.dumps({"theme_id": "x"}), encoding="utf-8")  # missing display_name
        out_dir = root / "dist"

        with redirect_stdout(io.StringIO()):
            success = pack_tool.export_pack(target, out_dir, {})

        self.assertFalse(success)
        self.assertFalse((out_dir / "invalid_export.json").exists())

    def _run_main(self, argv: list[str]) -> int:
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                pack_tool.main()
        return cm.exception.code

    def test_main_validate_exits_zero_for_a_valid_pack_directory(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")
        packs_dir = root / "packs"
        packs_dir.mkdir()
        (packs_dir / "sample.json").write_text(json.dumps(self.VALID_PACK), encoding="utf-8")

        code = self._run_main(["pack_tool.py", "validate", str(packs_dir), "--reference", str(ref)])
        self.assertEqual(0, code)

    def test_main_validate_exits_one_for_an_invalid_pack(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")
        packs_dir = root / "packs"
        packs_dir.mkdir()
        (packs_dir / "sample.json").write_text(json.dumps({"theme_id": "x"}), encoding="utf-8")

        code = self._run_main(["pack_tool.py", "validate", str(packs_dir), "--reference", str(ref)])
        self.assertEqual(1, code)

    def test_main_validate_accepts_a_single_file_target(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")
        target = root / "sample.json"
        target.write_text(json.dumps(self.VALID_PACK), encoding="utf-8")

        code = self._run_main(["pack_tool.py", "validate", str(target), "--reference", str(ref)])
        self.assertEqual(0, code)

    def test_main_validate_nonexistent_target_finds_nothing_and_exits_zero(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")

        code = self._run_main([
            "pack_tool.py", "validate", str(root / "does_not_exist"), "--reference", str(ref),
        ])
        self.assertEqual(0, code)

    def test_main_validate_missing_reference_exits_one(self) -> None:
        root = self._case_root()
        code = self._run_main([
            "pack_tool.py", "validate", str(root), "--reference", str(root / "missing.json"),
        ])
        self.assertEqual(1, code)

    def test_main_export_exits_zero_and_writes_output_file(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")
        target = root / "sample.json"
        target.write_text(json.dumps(self.VALID_PACK), encoding="utf-8")
        out_dir = root / "dist"

        code = self._run_main([
            "pack_tool.py", "export", str(target), "--out", str(out_dir), "--reference", str(ref),
        ])
        self.assertEqual(0, code)
        self.assertTrue((out_dir / "sample_export.json").exists())

    def test_main_export_requires_a_file_target(self) -> None:
        root = self._case_root()
        ref = root / "reference.json"
        ref.write_text(json.dumps({"ui_strings": {}}), encoding="utf-8")

        code = self._run_main([
            "pack_tool.py", "export", str(root), "--out", str(root / "dist"), "--reference", str(ref),
        ])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
