# tests/singles/test_story_fixture.py
"""The engine's tests do not depend on a game's story.

`tests/sets/story_fixture` is a frozen copy of the FF4 slice (see `tests/sets/README.md`), used by the tests of engine
features so that `content_sets/ff4_slice` can be rewritten freely. Two things keep that true:

* the engine's own validator still accepts the fixture, so a change to the engine that would strand it is noticed here, at its
  source, instead of as a dozen unrelated failures;
* only the tests that are *about* a shipped set may name it. A new test that boots `ff4_slice` to check an engine feature
  fails here, with the answer: use `STORY_FIXTURE`.
"""

import json
import re
import unittest
from pathlib import Path

from engine.server import content_set as validator
from tests.fixtures import STORY_FIXTURE

SINGLES = Path(__file__).resolve().parent

# Tests that are about the real set, its content or the sets as a family, and are meant to change with them.
ABOUT_THE_SHIPPED_SET = {
    "test_adaptation_slices.py": "journeys through both slices, pinned to their content",
    "test_slice_geography.py": "the slices' maps",
    "test_every_enemy_pays.py": "every enemy in the slice drops gil",
    "test_hazard_bite.py": "sweeps every shipped set for hazards that do not bite",
    "test_content_playability_check.py": "sweeps every shipped set",
    "test_world_snapshot_round_trip.py": "sweeps every shipped set",
    "test_story_beats.py": "its story classes play the real slice (the rest use the fixture)",
    "test_story_fixture.py": "this file",
}
NAMES_THE_SET = re.compile(r"""["']ff4_slice["']""")


class TestTheFixture(unittest.TestCase):
    def test_the_engine_still_accepts_it(self):
        _definition, issues = validator.load_content_set(STORY_FIXTURE)
        errors = [i.message for i in issues if i.severity == "error"]
        self.assertEqual([], errors, "the frozen story fixture no longer validates: update it deliberately (tests/sets/README.md)")

    def test_it_is_not_mistaken_for_a_shipped_set(self):
        manifest = json.loads((STORY_FIXTURE / "content_set.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("story_fixture", manifest["id"])
        self.assertFalse((STORY_FIXTURE.parents[2].parent / "content_sets" / "story_fixture").exists())


class TestEngineTestsDoNotNameTheStory(unittest.TestCase):
    def test_only_tests_about_the_shipped_set_boot_it(self):
        offenders = []
        for path in sorted(SINGLES.glob("test_*.py")):
            if path.name in ABOUT_THE_SHIPPED_SET:
                continue
            if NAMES_THE_SET.search(path.read_text(encoding="utf-8")):
                offenders.append(path.name)
        self.assertEqual(
            [], offenders,
            "these tests name the real ff4_slice, so a rewrite of its story would break them: use tests.fixtures.STORY_FIXTURE, "
            "or add the file to ABOUT_THE_SHIPPED_SET if it really is about the set",
        )

    def test_the_allowed_files_exist(self):
        for name in ABOUT_THE_SHIPPED_SET:
            self.assertTrue((SINGLES / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
