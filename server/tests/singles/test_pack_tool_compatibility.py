import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
