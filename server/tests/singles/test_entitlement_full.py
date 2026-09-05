# tests/singles/test_entitlement_full.py
"""Direct coverage for engine/server/entitlement.py's EntitlementGuard."""

import unittest

from engine.server.entitlement import EntitlementGuard


class TestEntitlementGuard(unittest.TestCase):
    def test_default_config_has_no_grants_or_gates(self):
        guard = EntitlementGuard()
        self.assertEqual([], guard.default_grants)
        self.assertEqual({}, guard.gates)

    def test_apply_defaults_adds_missing_grant(self):
        guard = EntitlementGuard({"default_session_grants": ["pack.sample_world"]})
        result = guard.apply_defaults([])
        self.assertEqual(["pack.sample_world"], result)

    def test_apply_defaults_skips_grant_already_present(self):
        guard = EntitlementGuard({"default_session_grants": ["pack.sample_world", "creator_sdk"]})
        result = guard.apply_defaults(["pack.sample_world"])
        self.assertEqual(["pack.sample_world", "creator_sdk"], result)

    def test_check_undefined_gate_is_open(self):
        guard = EntitlementGuard()
        allowed, reason = guard.check("unknown.gate", [])
        self.assertTrue(allowed)
        self.assertEqual("", reason)

    def test_check_missing_entitlement_is_denied(self):
        guard = EntitlementGuard({"gates": {"creator_sdk": {"requires": ["creator_sdk"]}}})
        allowed, reason = guard.check("creator_sdk", [])
        self.assertFalse(allowed)
        self.assertIn("requires entitlement", reason)

    def test_check_with_entitlement_is_allowed(self):
        guard = EntitlementGuard({"gates": {"creator_sdk": {"requires": ["creator_sdk"]}}})
        allowed, reason = guard.check("creator_sdk", ["creator_sdk"])
        self.assertTrue(allowed)
        self.assertEqual("", reason)

    def test_describe_gates_returns_requirements_mapping(self):
        guard = EntitlementGuard({"gates": {"creator_sdk": {"requires": ["creator_sdk"]}}})
        self.assertEqual({"creator_sdk": ["creator_sdk"]}, guard.describe_gates())


if __name__ == "__main__":
    unittest.main()
