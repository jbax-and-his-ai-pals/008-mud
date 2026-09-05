# tests/singles/test_world_constructor_guards.py
"""Coverage for engine/world/world.py's World.__init__() validation guards:
a missing content set."""

from tests.fixtures import GameTestBase
from engine.world.world import World


class TestWorldConstructorGuards(GameTestBase):
    def test_missing_content_set_raises(self):
        with self.assertRaisesRegex(ValueError, "requires a validated content set"):
            World(content_set=None)

    def test_content_root_is_not_an_override(self):
        with self.assertRaises(TypeError):
            World(content_root="/totally/different/path", content_set=self.world.content_set)


if __name__ == "__main__":
    import unittest
    unittest.main()
