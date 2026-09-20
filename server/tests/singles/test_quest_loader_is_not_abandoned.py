# tests/singles/test_quest_loader_is_not_abandoned.py
"""One `_comment` used to remove every quest in the file.

`load_quest_templates` iterated the file's keys without checking them:

* a `_comment` header was read as a quest, and `"stages" not in q_data` on a
  *string* raised `TypeError`;
* the `except` sat **outside** the loop, so that one exception abandoned the
  whole file;
* `quests/quests.json` holds all 22 quests, and six
  `ruleset.quest_generation.authored_board_templates` name ids from it.

So the failure was: add an authoring note, lose every quest, and pass validation
— because the content-set validator builds its own id list by reading the same
file, rather than asking what the loader produced.

These tests are about the loader's behaviour, not the validator's.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.core.quests.loader import load_quest_templates


class QuestLoaderTestBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (Path(self.root) / "quests").mkdir(parents=True, exist_ok=True)

    def _write(self, filename: str, payload) -> None:
        path = Path(self.root) / "quests" / filename
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")

    def _load(self):
        return load_quest_templates(self.root)


class TestTheNoteDoesNotEatTheFile(QuestLoaderTestBase):
    def test_a_comment_header_does_not_remove_the_quests(self):
        self._write("quests.json", {
            "_comment": "Every quest in the game lives here.",
            "quest_one": {"name": "One"},
            "quest_two": {"name": "Two"},
        })
        templates = self._load()
        self.assertEqual({"quest_one", "quest_two"}, set(templates))

    def test_a_comment_is_not_itself_a_quest(self):
        self._write("quests.json", {"_comment": "a note", "quest_one": {"name": "One"}})
        self.assertNotIn("_comment", self._load())

    def test_every_underscore_key_is_skipped(self):
        self._write("quests.json", {
            "_comment": "a note",
            "_default": "quest_one",
            "__also_a_note__": ["whatever"],
            "quest_one": {"name": "One"},
        })
        self.assertEqual({"quest_one"}, set(self._load()))

    def test_a_note_in_any_of_the_three_files_is_skipped(self):
        for filename in ("instances.json", "sagas.json", "quests.json"):
            self._write(filename, {"_comment": "note", "q_%s" % filename: {"name": "Q"}})
        self.assertEqual(3, len(self._load()))


class TestOneBadEntryDoesNotCostTheFile(QuestLoaderTestBase):
    def test_a_non_object_value_is_skipped_not_fatal(self):
        self._write("quests.json", {
            "broken": "this should be an object",
            "quest_one": {"name": "One"},
        })
        templates = self._load()
        self.assertNotIn("broken", templates)
        self.assertIn("quest_one", templates)

    def test_a_list_valued_entry_is_skipped_not_fatal(self):
        self._write("quests.json", {"broken": [1, 2, 3], "quest_one": {"name": "One"}})
        self.assertEqual({"quest_one"}, set(self._load()))

    def test_a_malformed_file_does_not_stop_the_other_two(self):
        """The three files are independent sources; one unreadable loses one."""
        self._write("quests.json", "{ this is not json")
        self._write("instances.json", {"instance_one": {"name": "I"}})
        self._write("sagas.json", {"saga_one": {"name": "S"}})
        self.assertEqual({"instance_one", "saga_one"}, set(self._load()))

    def test_a_top_level_list_is_refused_rather_than_iterated(self):
        self._write("quests.json", [{"name": "not a map"}])
        self.assertEqual({}, self._load())


class TestTheNormalizationStillHappens(QuestLoaderTestBase):
    def test_a_quest_with_no_stages_gains_one(self):
        self._write("quests.json", {
            "quest_one": {"name": "One", "description": "Do the thing."},
        })
        quest = self._load()["quest_one"]
        self.assertEqual(1, len(quest["stages"]))
        self.assertEqual(0, quest["stages"][0]["stage_index"])

    def test_the_synthesized_stage_carries_the_giver(self):
        self._write("quests.json", {
            "quest_one": {"name": "One", "giver_npc_template_id": "village_elder"},
        })
        self.assertEqual("village_elder", self._load()["quest_one"]["stages"][0]["turn_in_id"])

    def test_an_authored_stage_list_is_left_alone(self):
        self._write("quests.json", {
            "quest_one": {"name": "One", "stages": [
                {"stage_index": 0, "description": "First"},
                {"stage_index": 1, "description": "Second"},
            ]},
        })
        self.assertEqual(2, len(self._load()["quest_one"]["stages"]))


class TestItStillReadsTheShippedSet(unittest.TestCase):
    """The regression that matters: all 22 quests, not zero."""

    def test_the_fantasy_set_loads_every_quest(self):
        from pathlib import Path as P

        repo = P(__file__).resolve().parents[3]
        data_root = repo / "content_sets" / "fantasy_frontier" / "data"
        declared = json.loads((data_root / "quests" / "quests.json").read_text(encoding="utf-8"))
        expected = {k for k in declared if not str(k).startswith("_")}
        self.assertGreater(len(expected), 20, "the shipped set should have a real quest list")

        loaded = load_quest_templates(str(data_root))
        missing = sorted(expected - set(loaded))
        self.assertEqual([], missing, "declared quests the loader did not produce")


if __name__ == "__main__":
    unittest.main()
