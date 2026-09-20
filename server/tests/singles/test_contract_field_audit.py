# tests/singles/test_contract_field_audit.py
"""The read-or-delete ledger, and the two ways it can go stale.

`toolkit/contract_field_audit.py` is a gate, so the thing worth testing is that it
**can fail**. A ledger that only ever prints "all classified" is indistinguishable
from a ledger nobody maintains, which is the failure mode this whole convention
exists to prevent.

Three claims are checked here:

1. Today's state is complete -- every declared contract field has a verdict, and
   no verdict outlives its field.
2. A newly declared field is reported rather than silently accepted.
3. A removed field leaves a detectable orphan rather than a quietly dead entry.

(2) and (3) are driven by temporarily editing the schema the audit reads, which is
in-memory only: the shipped `registry.py` is not touched.
"""
import importlib.util
import unittest
from pathlib import Path

from engine.contracts import registry as contract_registry


REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "toolkit" / "contract_field_audit.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("contract_field_audit", AUDIT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_module = _load_audit()

# The debt that exists today. Pinned so it can shrink deliberately and cannot grow
# by accident: adding a field with no reader fails `test_no_new_unread_fields`
# until either a reader exists or this list is deliberately extended.
KNOWN_UNREAD = {
    ("attack_profiles", "cooldown"),
    ("attack_profiles", "resource_cost"),
    ("attack_profiles", "resource_cost.resource"),
    ("attack_profiles", "resource_cost.amount"),
    ("abilities", "effect_packet"),
    ("effect_packets", "kind"),
    ("effect_packets", "value"),
    ("effect_packets", "duration"),
    ("effect_packets", "tags"),
    ("effect_packets", "payload"),
}


class TestTheLedgerIsComplete(unittest.TestCase):
    def test_there_are_fields_to_check(self):
        """Guard against a renamed schema making every assertion below vacuous."""
        self.assertGreater(len(audit_module.declared_fields()), 40)

    def test_every_declared_field_is_classified(self):
        unclassified, _unread, _orphaned = audit_module.audit()
        self.assertEqual(
            [], unclassified,
            "a declared contract field with no read-or-delete verdict",
        )

    def test_no_ledger_entry_outlives_its_field(self):
        _unclassified, _unread, orphaned = audit_module.audit()
        self.assertEqual([], orphaned, "the ledger names a field the schemas do not declare")

    def test_the_audit_passes_as_shipped(self):
        """The gate's own exit code, run the way the content gate runs it."""
        import subprocess
        import sys

        completed = subprocess.run(
            [sys.executable, str(AUDIT_PATH)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
        )
        self.assertEqual(
            0, completed.returncode,
            "the shipped ledger should be complete:\n%s" % (completed.stdout + completed.stderr),
        )
        self.assertIn("all classified", completed.stdout)


class TestTheUnreadDebtIsBounded(unittest.TestCase):
    def test_no_new_unread_fields(self):
        """A field with no reader must be a recorded decision, not an oversight."""
        _unclassified, unread, _orphaned = audit_module.audit()
        unexpected = sorted(set(unread) - KNOWN_UNREAD)
        self.assertEqual(
            [], unexpected,
            "these fields are declared and read by nothing: give them a reader, "
            "remove them, or add them to KNOWN_UNREAD with a reason",
        )

    def test_every_known_unread_field_is_still_unread(self):
        """The list shrinks when a reader lands; it must not go stale in the other way."""
        _unclassified, unread, _orphaned = audit_module.audit()
        fixed = sorted(KNOWN_UNREAD - set(unread))
        self.assertEqual(
            [], fixed,
            "these fields now have a reader -- remove them from KNOWN_UNREAD",
        )

    def test_each_unread_field_records_why(self):
        """`UNREAD` entries carry an explanation; a bare marker explains nothing."""
        for section, field in sorted(KNOWN_UNREAD):
            with self.subTest(field="%s.%s" % (section, field)):
                verdict, why = audit_module.LEDGER[section][field]
                self.assertEqual(audit_module.UNREAD, verdict)
                self.assertGreater(len(why.strip()), 40,
                                   "say what makes it unread and what would wire it")

    def test_the_verdict_vocabulary_is_closed(self):
        for section, fields in audit_module.LEDGER.items():
            for field, (verdict, why) in fields.items():
                with self.subTest(field="%s.%s" % (section, field)):
                    self.assertIn(verdict, audit_module.VERDICTS)
                    self.assertTrue(why.strip(), "every verdict needs its evidence")


class TestTheAuditDetectsANewField(unittest.TestCase):
    """The fault injection, in-process: a declaration nobody reads."""

    def _with_extra_field(self, section: str, field: str):
        original = contract_registry.CONTRACT_SCHEMAS[section]
        patched = dict(original)
        patched[field] = {"type": "string"}
        contract_registry.CONTRACT_SCHEMAS[section] = patched
        self.addCleanup(
            lambda: contract_registry.CONTRACT_SCHEMAS.__setitem__(section, original)
        )

    def test_a_new_field_is_reported_as_unclassified(self):
        self._with_extra_field("item_families", "silent_no_op")
        unclassified, _unread, _orphaned = audit_module.audit()
        self.assertIn(("item_families", "silent_no_op"), unclassified)

    def test_the_shipped_state_does_not_contain_that_field(self):
        """The injection above must not be the shipped state."""
        unclassified, _unread, _orphaned = audit_module.audit()
        self.assertNotIn(("item_families", "silent_no_op"), unclassified)

    def test_a_nested_field_is_found_too(self):
        """`resource_cost.amount` style fields are declared one level down."""
        original = contract_registry.CONTRACT_SCHEMAS["attack_profiles"]
        patched = dict(original)
        patched["swing_time"] = {
            "type": "object", "fields": {"seconds": {"type": "float"}},
        }
        contract_registry.CONTRACT_SCHEMAS["attack_profiles"] = patched
        self.addCleanup(
            lambda: contract_registry.CONTRACT_SCHEMAS.__setitem__("attack_profiles", original)
        )
        unclassified, _unread, _orphaned = audit_module.audit()
        self.assertIn(("attack_profiles", "swing_time.seconds"), unclassified)


class TestTheAuditDetectsAStaleEntry(unittest.TestCase):
    def test_removing_a_field_leaves_an_orphan(self):
        original = contract_registry.CONTRACT_SCHEMAS["item_families"]
        patched = {k: v for k, v in original.items() if k != "debug_only"}
        contract_registry.CONTRACT_SCHEMAS["item_families"] = patched
        self.addCleanup(
            lambda: contract_registry.CONTRACT_SCHEMAS.__setitem__("item_families", original)
        )
        _unclassified, _unread, orphaned = audit_module.audit()
        self.assertIn(("item_families", "debug_only"), orphaned)


class TestTheWireIntoTheContentGate(unittest.TestCase):
    """A check nobody runs is a comment."""

    def test_run_content_checks_invokes_the_audit(self):
        runner = (REPO_ROOT / "run_content_checks.py").read_text(encoding="utf-8")
        self.assertIn("contract_field_audit.py", runner)
        self.assertIn("Audit contract fields for a reader", runner,
                      "the step should be named in the gate's output")


if __name__ == "__main__":
    unittest.main()
