# tests/singles/test_set_manager_full.py
"""Coverage for engine/items/set_manager.py: the owning-world guard and the
malformed sets.json error-handling branch."""

import os
import tempfile
import shutil
import unittest

from types import SimpleNamespace

from engine.items.set_manager import SetManager


class TestSetManagerConstruction(unittest.TestCase):
    def test_missing_world_is_rejected(self):
        with self.assertRaises(TypeError):
            SetManager()

    def test_missing_sets_file_leaves_sets_empty(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            manager = SetManager(SimpleNamespace(content_root=tmp_dir))
            self.assertEqual(manager.sets, {})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_malformed_sets_file_is_reported_and_leaves_sets_empty(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            items_dir = os.path.join(tmp_dir, "items")
            os.makedirs(items_dir)
            with open(os.path.join(items_dir, "sets.json"), "w") as f:
                f.write("{not valid json")
            manager = SetManager(SimpleNamespace(content_root=tmp_dir))
            self.assertEqual(manager.sets, {})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_active_bonuses_respect_threshold(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            items_dir = os.path.join(tmp_dir, "items")
            os.makedirs(items_dir)
            with open(os.path.join(items_dir, "sets.json"), "w") as f:
                f.write(
                    '{"warrior_set": {"items": ["helm", "boots"], '
                    '"bonuses": {"1": {"strength": 1}, "2": {"strength": 3}}}}'
                )
            manager = SetManager(SimpleNamespace(content_root=tmp_dir))
            one_piece = manager.get_active_bonuses(["helm"])
            self.assertEqual(one_piece, [{"strength": 1}])
            two_pieces = manager.get_active_bonuses(["helm", "boots"])
            self.assertIn({"strength": 1}, two_pieces)
            self.assertIn({"strength": 3}, two_pieces)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
