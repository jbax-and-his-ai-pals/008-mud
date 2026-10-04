"""The test run's content-set load cache (`engine.server.content_set.enable_load_cache`).

Loading a set validates every file in it and a suite does that once per test, so a run answers a set that has not
changed on disk from memory. That is only safe if an edit is never missed and nobody can change what the next
caller is given; both are pinned here, because a stale answer would make every other test's verdict wrong.
"""

import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.server import content_set

REPO_ROOT = Path(__file__).resolve().parents[3]
STORY_FIXTURE = REPO_ROOT / "server" / "tests" / "sets" / "story_fixture"


class TestTheLoadCache(unittest.TestCase):
    def setUp(self) -> None:
        self.root = REPO_ROOT / "tmp" / ("load_cache_%s" % uuid.uuid4().hex)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.package = self.root / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package, ignore=shutil.ignore_patterns("editor", "saves", "*.bak"))

    def test_the_test_package_turns_it_on(self) -> None:
        self.assertIsNotNone(content_set._LOAD_CACHE)

    def test_an_unchanged_set_is_answered_from_memory(self) -> None:
        first, _ = content_set.load_content_set(self.package)
        keys = len(content_set._LOAD_CACHE)
        second, _ = content_set.load_content_set(self.package)
        self.assertEqual(keys, len(content_set._LOAD_CACHE), "the second load added nothing")
        self.assertEqual(first, second)
        self.assertIsNot(first, second, "each caller gets its own copy")

    def test_what_a_caller_does_to_its_copy_is_not_seen_by_the_next(self) -> None:
        first, issues = content_set.load_content_set(self.package)
        issues.append("a caller's own note")
        first.ruleset["vandalised"] = True
        second, again = content_set.load_content_set(self.package)
        self.assertNotIn("a caller's own note", again)
        self.assertNotIn("vandalised", second.ruleset)

    def test_an_edit_to_any_file_is_seen(self) -> None:
        content_set.load_content_set(self.package)
        victim = next((self.package / "data").rglob("*.json"))
        before = victim.read_text(encoding="utf-8")
        victim.write_text(before + " ", encoding="utf-8")
        keys = len(content_set._LOAD_CACHE)
        content_set.load_content_set(self.package)
        self.assertEqual(keys + 1, len(content_set._LOAD_CACHE), "a changed file is a different set")

    def test_a_broken_edit_is_reported_not_remembered_away(self) -> None:
        _, clean = content_set.load_content_set(self.package)
        manifest = self.package / "content_set.manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["id"] = "Not A Valid Id"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        _, broken = content_set.load_content_set(self.package)
        self.assertTrue([i for i in broken if i.severity == "error"], "the bad id is refused")
        self.assertFalse([i for i in clean if i.severity == "error"])


if __name__ == "__main__":
    unittest.main()
