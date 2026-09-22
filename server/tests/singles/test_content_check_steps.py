# tests/singles/test_content_check_steps.py
"""One definition of what a content check is -- and the proof that both use it.

Before this, `run_content_checks.py` and `toolkit/editor_validate.py` each held
their own list. The editor's docstring claimed it ran "the same checks" the gate
ran; it ran five of fourteen, so it could report "No issues found" for a content
set the build refuses. The two it was missing first were the number gate and the
contract-field audit -- both of which exist specifically to catch defects the
editor produces.

So these tests are about parity, not about any one validator:

1. The gate's step list is derived from the shared definition.
2. The editor runs an in-process check for every shared check that applies to a
   single set, and *reports* the ones it does not run.
3. Neither side can silently grow a check the other does not know about.
"""
import ast
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

steps = None  # bound below, after REPO_ROOT is known


REPO_ROOT = Path(__file__).resolve().parents[3]
GATE = REPO_ROOT / "run_content_checks.py"
EDITOR_VALIDATE = REPO_ROOT / "toolkit" / "editor_validate.py"
STEPS_MODULE = REPO_ROOT / "toolkit" / "content_check_steps.py"


def _load_steps():
    """Load `toolkit/content_check_steps.py` by path.

    Not `from toolkit import ...`: the suite runs with `server/` as its root, and
    the module deliberately imports nothing beyond the standard library, so a
    direct file load is both sufficient and the honest way to reach it.

    Registered in `sys.modules` first, because the module defines dataclasses and
    `@dataclass` resolves the defining module through `sys.modules` at class
    creation time.
    """
    name = "content_check_steps"
    spec = importlib.util.spec_from_file_location(name, STEPS_MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


steps = _load_steps()

# The checks an editor session runs, and which it must therefore have an
# in-process implementation for. A check added here without one fails
# `test_every_editor_check_has_an_in_process_source`.
EDITOR_SOURCE_NAMES = {
    "number_types": "numbers",
    "contract_fields": "contracts",
    "skill_audit": "skills",
    "reference_integrity": "references",
    "stale_references": "stale",
    "neutrality": "neutrality",
}


class TestTheSharedListIsTheOnlyList(unittest.TestCase):
    def test_the_gate_has_no_hand_written_step_names(self):
        """A second list is how the drift happened. The gate must not have one.

        Asserted on the syntax tree rather than on text, so a comment or a
        docstring mentioning a validator is not mistaken for a call.
        """
        tree = ast.parse(GATE.read_text(encoding="utf-8"))
        literals: list[str] = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "run_step"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                literals.append(str(node.args[0].value))
        self.assertEqual(
            [], literals,
            "run_step should be called with a step's own label, not a literal; "
            "these look like a hand-written list: %s" % literals,
        )

    def test_the_gate_iterates_the_shared_steps(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("steps_module.steps()", source)
        self.assertIn("steps_module.fixture_steps(", source)

    def test_every_check_id_is_unique(self):
        ids = [c.id for c in steps.CHECKS]
        self.assertEqual(len(ids), len(set(ids)), "two checks share an id")

    def test_every_check_declares_a_label_and_a_script(self):
        for check in steps.CHECKS:
            with self.subTest(check=check.id):
                self.assertTrue(check.label.strip())
                first = check.argv_tail[0]
                self.assertTrue(first.startswith("toolkit/"), first)
                self.assertTrue((REPO_ROOT / first).is_file(),
                                "%s does not exist" % first)

    def test_a_per_set_label_ends_in_a_separator(self):
        """The expansion appends the set id, so the label ends in ': '.

        Not a `%s` placeholder: a label may contain "%s" as plain text ("match
        their schema types"), so keying the substitution on the format string
        would make an unrelated check a per-set one by accident.
        """
        for check in steps.CHECKS:
            if check.per_set:
                with self.subTest(check=check.id):
                    self.assertTrue(check.label.endswith(": "),
                                    "a per-set label must end in ': '")

    def test_expansion_produces_no_unresolved_placeholders(self):
        for step in steps.steps():
            with self.subTest(step=step.id):
                self.assertNotIn("<", " ".join(step.argv_tail))
                self.assertNotIn("%s", step.label)

    def test_expansion_covers_every_shipped_set(self):
        targets = {step.target for step in steps.steps() if step.target}
        self.assertEqual(set(steps.CONTENT_SETS), targets)


class TestTheEditorRunsWhatApplies(unittest.TestCase):
    def test_each_set_has_checks(self):
        for set_id in steps.CONTENT_SETS:
            with self.subTest(set=set_id):
                self.assertTrue(steps.checks_for_set(set_id))

    def test_the_editor_runs_every_per_set_check_that_is_not_skipped(self):
        """The parity claim, as an assertion rather than a docstring."""
        for set_id in steps.CONTENT_SETS:
            wanted = {
                check.id for check in steps.CHECKS
                if check.per_set and not check.editor_skips and set_id in check.sets()
            }
            got = {check.id for check in steps.checks_for_set(set_id)}
            with self.subTest(set=set_id):
                self.assertTrue(
                    wanted <= got,
                    "the editor does not run: %s" % sorted(wanted - got),
                )

    def test_coverage_accounts_for_every_check(self):
        coverage = steps.editor_coverage("fantasy_frontier")
        self.assertEqual(
            {check.id for check in steps.CHECKS}, set(coverage),
            "every check must be reported as run, skipped or not applicable",
        )

    def test_a_skipped_check_gives_a_reason(self):
        """A gap with no reason is indistinguishable from an oversight."""
        for check in steps.CHECKS:
            if check.editor_skips is None:
                continue
            with self.subTest(check=check.id):
                self.assertGreater(len(check.editor_skips), 30,
                                   "say why the editor does not run it")

    def test_the_editor_reports_its_gaps_in_the_payload(self):
        """`not_run` is what lets the editor show scope rather than imply it."""
        source = EDITOR_VALIDATE.read_text(encoding="utf-8")
        self.assertIn('"not_run"', source)
        self.assertIn("editor_coverage", source)

    def test_the_four_checks_the_editor_was_missing_are_now_covered(self):
        """The specific regression, pinned by name."""
        ran = {check.id for check in steps.checks_for_set("fantasy_frontier")}
        for check_id in ("number_types", "contract_fields", "skill_audit", "neutrality"):
            with self.subTest(check=check_id):
                self.assertIn(check_id, ran)


class TestTheEditorHasAnImplementationForWhatItClaims(unittest.TestCase):
    """A coverage claim with no implementation behind it is worse than a gap."""

    def _editor_payload(self, set_id: str) -> dict:
        """Run the editor's validator and read its document.

        The engine logs on import, so stdout carries startup lines before the JSON
        -- exactly why `EngineValidator.gd` parses the *last* balanced object
        rather than the whole output. The same reading is done here, so this test
        exercises the contract the editor actually relies on.
        """
        completed = subprocess.run(
            [sys.executable, str(EDITOR_VALIDATE), "content_sets/%s" % set_id],
            cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
        )
        self.assertIn(completed.returncode, (0, 1),
                      "editor_validate should report, not crash:\n%s" % completed.stderr)
        start = completed.stdout.rfind("\n{")
        self.assertNotEqual(-1, start, "no JSON document in the output:\n%s" % completed.stdout[:400])
        return json.loads(completed.stdout[start:])

    def test_every_applicable_check_reports_that_it_ran(self):
        for set_id in ("fantasy_frontier", "orbital_salvage"):
            payload = self._editor_payload(set_id)
            expected = {
                EDITOR_SOURCE_NAMES[check.id]
                for check in steps.checks_for_set(set_id)
                if check.id in EDITOR_SOURCE_NAMES
            }
            with self.subTest(set=set_id):
                self.assertTrue(
                    expected <= set(payload["ran"]),
                    "these checks are claimed but did not run: %s" % sorted(expected - set(payload["ran"])),
                )

    def test_the_editor_reports_no_skipped_validator(self):
        """A `skipped` entry means an implementation broke, not that a check is absent."""
        payload = self._editor_payload("fantasy_frontier")
        self.assertEqual([], payload["skipped"])

    def test_the_editor_names_what_it_did_not_run(self):
        payload = self._editor_payload("fantasy_frontier")
        not_run = payload["not_run"]
        # The editor boots the set the author has open, so `playability` itself
        # runs; what it must still declare is that the *other* shipped sets were
        # not played. Both halves are asserted, because "it ran" alone would let
        # the slow four-set form be dropped without a word.
        self.assertIn("playability", payload["ran"], "the open set is booted and exercised")
        self.assertIn("playability_other_sets", not_run,
                      "the sets the editor did not play must be declared, not omitted")
        self.assertIn("theme_packs", not_run)
        for check_id, reason in not_run.items():
            with self.subTest(check=check_id):
                self.assertTrue(reason.strip())


if __name__ == "__main__":
    unittest.main()
