# tests/singles/test_world_constructor_guards.py
"""Coverage for engine/world/world.py's World.__init__() validation guards:
missing content set, and a data_root that disagrees with the content
set's own data_root."""

from tests.fixtures import GameTestBase
from engine.world.world import World


class TestWorldConstructorGuards(GameTestBase):
    def test_missing_content_set_raises(self):
        with self.assertRaisesRegex(ValueError, "requires a validated content set"):
            World(content_set=None)

    def test_mismatched_data_root_raises(self):
        with self.assertRaisesRegex(ValueError, "data_root must be the selected content set's data_root"):
            World(data_root="/totally/different/path", content_set=self.world.content_set)


if __name__ == "__main__":
    import unittest
    unittest.main()
