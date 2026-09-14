# tests/singles/test_journey_runner_failure_classifier.py
"""Coverage for journey_runner.py's _is_gameplay_failure text classifier.

Locked, depleted, and missing-ingredient refusals previously passed
through unclassified -- a journey could hit any of them repeatedly with
gameplay_failure_count staying at zero. Each phrase below is copied
verbatim from the engine code path that emits it, and each non-matching
case is a real informational string that happens to share a word with a
refusal (e.g. a survey line's bare "(depleted)" tag) to confirm the
narrower phrase, not the bare word, was matched intentionally."""

import unittest

from tests.journey_runner import _is_gameplay_failure


class TestGameplayFailureClassifierLockedDepletedMissingIngredient(unittest.TestCase):
    def test_locked_exit_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("The way north is locked."))

    def test_locked_door_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("The door to the Cellar is locked."))

    def test_locked_container_open_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("The old chest is locked."))

    def test_locked_look_inside_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("The strongbox is locked."))

    def test_container_examine_lock_status_line_is_not_a_failure(self):
        self.assertFalse(_is_gameplay_failure("It's locked."))

    def test_container_examine_bracket_tag_is_not_a_failure(self):
        self.assertFalse(_is_gameplay_failure("Status: [Locked] (Closed)"))

    def test_quest_trust_summary_locked_annotation_is_not_a_failure(self):
        self.assertFalse(_is_gameplay_failure("Trust: 3/10 (locked)"))

    def test_depleted_resource_node_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("The herb bed has been depleted."))

    def test_survey_depleted_status_tag_is_not_a_failure(self):
        self.assertFalse(_is_gameplay_failure("- Herb Bed: 0/3 (depleted); tool: none"))

    def test_missing_ingredient_refusal_is_a_failure(self):
        self.assertTrue(_is_gameplay_failure("Missing ingredient: Iron Ore (0/2)"))


if __name__ == "__main__":
    unittest.main()
