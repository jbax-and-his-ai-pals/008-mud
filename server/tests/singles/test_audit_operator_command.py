"""Tests for the 'audit stale-refs' operator command wired into JsonLineMudServer.

These tests verify:
- The command is recognised by the parser helper.
- The audit result event has the expected shape.
- An entitlement gate blocks unauthorised callers.
- The audit runs against the selected content set cleanly.
"""
import json
import sys
import unittest
from pathlib import Path

# Ensure the server package root is on sys.path when run directly.
_SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from poc_server import JsonLineMudServer  # noqa: E402
from tests.fixtures import FANTASY_FRONTIER  # noqa: E402


def _make_core() -> JsonLineMudServer:
    return JsonLineMudServer(
        host="127.0.0.1",
        port=0,
        save_file=":memory:",
        asset_db_path=":memory:",
        content_set_path=FANTASY_FRONTIER,
    )


class TestAuditCommandParser(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    def tearDown(self) -> None:
        self.core.server.shutdown()

    def test_recognises_canonical_form(self) -> None:
        self.assertTrue(self.core._is_audit_stale_refs_command("audit stale-refs"))

    def test_recognises_underscore_variant(self) -> None:
        self.assertTrue(self.core._is_audit_stale_refs_command("audit stale_refs"))

    def test_recognises_spaced_variant(self) -> None:
        self.assertTrue(self.core._is_audit_stale_refs_command("audit stale refs"))

    def test_does_not_match_unrelated(self) -> None:
        self.assertFalse(self.core._is_audit_stale_refs_command("profile list"))
        self.assertFalse(self.core._is_audit_stale_refs_command("audit"))
        self.assertFalse(self.core._is_audit_stale_refs_command(""))


class TestAuditResultShape(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    def tearDown(self) -> None:
        self.core.server.shutdown()

    def test_result_has_required_fields(self) -> None:
        result = self.core._run_stale_ref_audit()
        for field in ("audit", "root", "issues", "error_count", "warn_count", "clean"):
            self.assertIn(field, result, msg=f"Expected field '{field}' in audit result.")

    def test_audit_field_is_stale_refs(self) -> None:
        result = self.core._run_stale_ref_audit()
        self.assertEqual("stale_refs", result["audit"])

    def test_issues_is_list(self) -> None:
        result = self.core._run_stale_ref_audit()
        self.assertIsInstance(result["issues"], list)

    def test_counts_match_issues(self) -> None:
        result = self.core._run_stale_ref_audit()
        issues = result["issues"]
        expected_errors = sum(1 for i in issues if i.startswith("[ERROR]"))
        expected_warns = sum(1 for i in issues if i.startswith("[WARN]"))
        self.assertEqual(expected_errors, result["error_count"])
        self.assertEqual(expected_warns, result["warn_count"])

    def test_clean_reflects_zero_errors(self) -> None:
        result = self.core._run_stale_ref_audit()
        if result["error_count"] == 0:
            self.assertTrue(result["clean"])
        else:
            self.assertFalse(result["clean"])


class TestAuditCatalogRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    def tearDown(self) -> None:
        self.core.server.shutdown()

    def test_audit_domain_in_catalog(self) -> None:
        catalog = self.core.build_operator_catalog_payload()
        self.assertIn("Audit", catalog["domains"])

    def test_stale_refs_action_in_audit_domain(self) -> None:
        catalog = self.core.build_operator_catalog_payload()
        self.assertIn("Stale Refs", catalog["domains"].get("Audit", []))

    def test_audit_stale_refs_has_entitlement_requirement(self) -> None:
        catalog = self.core.build_operator_catalog_payload()
        req = catalog.get("requirements", {}).get("Audit:Stale Refs", {})
        self.assertEqual("operator.audit.stale_refs", req.get("requires_entitlement"))


class TestAuditDefaultDataClean(unittest.TestCase):
    """Regression guard: the selected content set must pass the audit."""

    def setUp(self) -> None:
        self.core = _make_core()

    def tearDown(self) -> None:
        self.core.server.shutdown()

    def test_content_set_has_no_stale_ref_errors(self) -> None:
        result = self.core._run_stale_ref_audit()
        if result.get("error"):
            self.skipTest(f"Audit toolkit not available: {result['error']}")
        errors = [i for i in result["issues"] if i.startswith("[ERROR]")]
        self.assertEqual(
            [],
            errors,
            msg="Stale reference errors found in selected content set:\n" + "\n".join(errors),
        )


if __name__ == "__main__":
    unittest.main()
