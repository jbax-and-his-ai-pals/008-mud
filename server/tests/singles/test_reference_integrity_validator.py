import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import reference_integrity_validator as riv


class TestReferenceIntegrityValidator(unittest.TestCase):
    def test_live_data_has_no_reference_errors(self) -> None:
        catalogs = riv.load_catalogs(REPO_ROOT / "server" / "data")
        issues = riv.validate_catalogs(catalogs)
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
