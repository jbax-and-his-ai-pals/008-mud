# tests/singles/test_spell_registry_full.py
"""Coverage for engine/magic/spell_registry.py's load_spells_from_json:
the no-content_root guard, non-json files being skipped, malformed-JSON
decode errors, and other unexpected exceptions during file load."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from engine.magic.spell_registry import load_spells_from_json, SPELL_REGISTRY


class TestLoadSpellsFromJson(unittest.TestCase):
    def setUp(self):
        self.tmp_root = tempfile.mkdtemp()
        self._original_registry = dict(SPELL_REGISTRY)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        SPELL_REGISTRY.clear()
        SPELL_REGISTRY.update(self._original_registry)

    def test_empty_content_root_raises(self):
        with self.assertRaises(ValueError):
            load_spells_from_json("")

    def test_non_json_files_are_skipped(self):
        magic_dir = os.path.join(self.tmp_root, "magic")
        os.makedirs(magic_dir)
        with open(os.path.join(magic_dir, "readme.txt"), "w") as f:
            f.write("not json")
        stats = load_spells_from_json(self.tmp_root)
        self.assertEqual(stats["files_loaded"], 0)

    def test_malformed_json_reports_file_error(self):
        magic_dir = os.path.join(self.tmp_root, "magic")
        os.makedirs(magic_dir)
        with open(os.path.join(magic_dir, "broken.json"), "w") as f:
            f.write("{not valid json")
        stats = load_spells_from_json(self.tmp_root)
        self.assertEqual(stats["file_errors"], 1)
        self.assertEqual(stats["files_loaded"], 0)

    def test_unexpected_exception_reports_file_error(self):
        magic_dir = os.path.join(self.tmp_root, "magic")
        os.makedirs(magic_dir)
        with open(os.path.join(magic_dir, "valid.json"), "w") as f:
            f.write('{"test_spell": {"name": "Test", "effects": [{"type": "damage", "value": 1}]}}')
        with patch("engine.magic.spell_registry.Spell.from_dict", side_effect=RuntimeError("boom")):
            stats = load_spells_from_json(self.tmp_root)
        self.assertEqual(stats["file_errors"], 1)


if __name__ == "__main__":
    unittest.main()
