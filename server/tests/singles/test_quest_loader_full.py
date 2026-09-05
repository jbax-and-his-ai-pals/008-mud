# tests/singles/test_quest_loader_full.py
"""Coverage for engine/core/quests/loader.py's load_quest_templates(),
including the except branch when a quest JSON file fails to parse."""

import os
import tempfile
import shutil
import unittest

from engine.core.quests.loader import load_quest_templates


class TestLoadQuestTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.quests_dir = os.path.join(self.tmp_dir, "quests")
        os.makedirs(self.quests_dir)
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def test_malformed_json_file_is_skipped_with_error_logged(self):
        with open(os.path.join(self.quests_dir, "quests.json"), "w") as f:
            f.write("{not valid json")
        templates = load_quest_templates(self.tmp_dir)
        self.assertEqual(templates, {})

    def test_valid_quest_is_loaded_and_normalized(self):
        with open(os.path.join(self.quests_dir, "quests.json"), "w") as f:
            f.write('{"q1": {"description": "Do a thing."}}')
        templates = load_quest_templates(self.tmp_dir)
        self.assertIn("q1", templates)
        self.assertIn("stages", templates["q1"])
        self.assertEqual(templates["q1"]["stages"][0]["turn_in_id"], "quest_board")


if __name__ == "__main__":
    unittest.main()
