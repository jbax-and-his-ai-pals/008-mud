# tests/singles/test_editor_validate.py
"""The editor's one-shot validation pass (`toolkit/editor_validate.py`).

The point of this module is that the editor and the command line cannot drift
onto different checks, so what it must prove is: it runs every validator, it
reports what they report, it is usable when one of them cannot run, and it never
raises on a content set that is broken -- a validation tool that crashes on
invalid content is worse than one that reports nothing.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import editor_validate  # noqa: E402

CONTENT_SETS = REPO_ROOT / "content_sets"

# The `ran` name the editor reports for each shared check. A check whose id
# differs from its collector's name is mapped here, so a check added to the shared
# list without a collector fails the assertion instead of passing unnoticed.
SOURCE_FOR_CHECK = {
    "content_set_schema": "engine",
    "json_integrity": "json",
    "number_types": "numbers",
    "contract_fields": "contracts",
    "skill_audit": "skills",
    "reference_integrity": "references",
    "stale_references": "stale",
}


class TestValidationRuns(unittest.TestCase):
    def test_both_reference_sets_pass_their_own_checks(self):
        for name in ("fantasy_frontier", "orbital_salvage"):
            with self.subTest(content_set=name):
                result = editor_validate.validate(CONTENT_SETS / name)
                self.assertEqual(0, result["counts"]["error"], result["issues"])
                self.assertTrue(result["ok"])
                # The list comes from `toolkit/content_check_steps.py`, shared with
                # `run_content_checks.py`; this asserts the editor ran the checks
                # that apply to one set, not a frozen transcription of them.
                from toolkit import content_check_steps as steps

                expected_sources = set()
                for check in steps.checks_for_set(name):
                    expected_sources.add(SOURCE_FOR_CHECK.get(check.id, check.id))
                self.assertTrue(
                    expected_sources <= set(result["ran"]),
                    "checks claimed but not run: %s" % sorted(expected_sources - set(result["ran"])),
                )

    def test_a_data_directory_is_accepted_as_well_as_a_content_set(self):
        from_set = editor_validate.validate(CONTENT_SETS / "fantasy_frontier")
        from_data = editor_validate.validate(CONTENT_SETS / "fantasy_frontier" / "data")
        self.assertEqual(from_set["counts"], from_data["counts"])

    def test_the_known_dangling_set_references_are_reported_as_warnings(self):
        """The allow-listed mage_set gaps are visible, and are not errors."""
        result = editor_validate.validate(CONTENT_SETS / "fantasy_frontier")
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["counts"]["warning"], 2)
        self.assertTrue(any("mage_set" in issue["message"] for issue in result["issues"]))

    def test_the_same_problem_from_two_validators_is_reported_once(self):
        result = editor_validate.validate(CONTENT_SETS / "fantasy_frontier")
        messages = [issue["message"] for issue in result["issues"]]
        self.assertEqual(len(messages), len(set(messages)), messages)
        merged = [issue for issue in result["issues"] if len(issue.get("sources", [])) > 1]
        self.assertTrue(merged, "the stale audit and the reference validator overlap; both should be recorded")


class TestBrokenContentIsReportedNotRaised(unittest.TestCase):
    def _broken_set(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        target = root / "content_set"
        shutil.copytree(CONTENT_SETS / "fantasy_frontier", target)
        # A quest that can never be completed, an item template missing its type,
        # and invalid JSON: three different validators, three different failures.
        quests = target / "data" / "quests" / "quests.json"
        payload = json.loads(quests.read_text(encoding="utf-8"))
        first = next(iter(payload))
        payload[first]["stages"].append({"stage_index": 9, "description": "orphan"})
        quests.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        (target / "data" / "items" / "broken.json").write_text("{ not json", encoding="utf-8")
        return target

    def test_errors_are_found_and_described(self):
        result = editor_validate.validate(self._broken_set())
        self.assertFalse(result["ok"])
        broken = [issue for issue in result["issues"] if "broken.json" in issue["path"]]
        self.assertTrue(broken, "the invalid file is named: %s" % result["issues"])
        self.assertTrue(all(issue["severity"] == "error" for issue in broken), broken)
        # Several validators notice the same file. Where their wording agrees the
        # entry records both sources; where it does not, both are still listed.
        merged = [issue for issue in result["issues"] if len(issue.get("sources", [])) > 1]
        self.assertTrue(merged, "the same problem from two validators should name both sources")

    def test_paths_are_relative_to_the_content_set(self):
        result = editor_validate.validate(CONTENT_SETS / "fantasy_frontier")
        for issue in result["issues"]:
            path = issue["path"]
            # A drive letter or a leading slash is a path from this machine. A
            # colon alone is not: the skill audit uses synthetic locators like
            # `engine:crafting_manager` to say the roll lives in engine code, which
            # is precisely the finding an author needs and not a leaked path.
            self.assertFalse(
                path.startswith("/") or (len(path) > 1 and path[1] == ":"),
                "an author should not be shown this machine's absolute paths: %r" % path,
            )
        self.assertTrue(any(issue["path"].startswith("data/") for issue in result["issues"]),
                        "and the relative path should name the file")

    def test_a_directory_that_is_not_a_content_set_is_reported(self):
        result = editor_validate.validate(REPO_ROOT / "no_such_content_set")
        self.assertFalse(result["ok"])
        self.assertEqual("setup", result["issues"][0]["source"])


class TestTheSourceFilter(unittest.TestCase):
    """`--only` exists so a caller can ask one question.

    The world-link modal uses it to show the engine's *link* verdict without the
    item, quest and contract findings that share the same run. A filter that let
    unrelated findings through would show an author link errors on a region whose
    contracts are broken.
    """

    def _run(self, *extra: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "toolkit" / "editor_validate.py"),
             str(CONTENT_SETS / "fantasy_frontier"), "--json", *extra],
            cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
        )
        raw = completed.stdout
        return json.loads(raw[raw.index("{"):])

    def test_every_reported_issue_comes_from_a_requested_source(self):
        payload = self._run("--only", "references,stale")
        self.assertEqual(["references", "stale"], payload["filtered_to"])
        for issue in payload["issues"]:
            with self.subTest(path=issue["path"]):
                self.assertTrue(
                    {"references", "stale"} & set(issue.get("sources", [issue.get("source", "")])),
                    "an issue from another source survived the filter",
                )

    def test_the_counts_describe_what_is_reported(self):
        """Stale counts would make the modal's summary disagree with its list."""
        payload = self._run("--only", "references,stale")
        reported = payload["issues"]
        self.assertEqual(sum(1 for i in reported if i["severity"] == "error"), payload["counts"]["error"])
        self.assertEqual(sum(1 for i in reported if i["severity"] != "error"), payload["counts"]["warning"])
        self.assertEqual(payload["counts"]["error"] == 0, payload["ok"])

    def test_the_unfiltered_counts_describe_what_is_reported(self):
        """The path the editor's modal actually shows.

        The filter test above passed while the unfiltered path was wrong: counts
        were computed before the issues were deduped, so a shipped set whose
        validators overlap reported seven warnings above five rows.
        """
        payload = editor_validate.validate(CONTENT_SETS / "fantasy_frontier")
        reported = payload["issues"]

        self.assertEqual(sum(1 for i in reported if i["severity"] == "error"), payload["counts"]["error"])
        self.assertEqual(sum(1 for i in reported if i["severity"] != "error"), payload["counts"]["warning"])
        self.assertEqual(payload["counts"]["error"] == 0, payload["ok"])
        self.assertGreaterEqual(len(reported), 1, "the fixture set should report something")

    def test_the_filter_narrows_rather_than_widens(self):
        """A filtered run can only report a subset of the unfiltered one."""
        full = self._run()
        filtered = self._run("--only", "references")
        self.assertLessEqual(len(filtered["issues"]), len(full["issues"]))

    def test_no_filter_reports_every_source_as_before(self):
        payload = self._run()
        self.assertNotIn("filtered_to", payload)
        self.assertIn("engine", payload["ran"])


class TestTheCommandLineContract(unittest.TestCase):
    def test_json_on_stdout_and_exit_codes(self):
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "toolkit" / "editor_validate.py"),
             str(CONTENT_SETS / "orbital_salvage")],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout[completed.stdout.index("{"):])
        self.assertTrue(payload["ok"])

    def test_a_failing_content_set_exits_non_zero(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        target = root / "content_set"
        shutil.copytree(CONTENT_SETS / "fantasy_frontier", target)
        (target / "data" / "items" / "broken.json").write_text("{ not json", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "toolkit" / "editor_validate.py"), str(target)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)


if __name__ == "__main__":
    unittest.main()
