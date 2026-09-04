# tests/singles/test_key_item.py
"""Coverage for engine/items/key.py's use(): no-target guard, successful
lock/unlock via toggle_lock, wrong-key rejection, and targets that don't
support toggle_lock at all."""

from tests.fixtures import GameTestBase
from engine.items.key import Key
from engine.items.container import Container
from engine.items.item import Item


class TestKeyConstructor(GameTestBase):
    def test_stackable_kwarg_is_silently_dropped(self):
        key = Key(obj_id="k0", name="Odd Key", stackable=True)
        self.assertFalse(key.stackable)


class TestKeyUse(GameTestBase):
    def test_no_target_prompts(self):
        key = Key(obj_id="k1", name="Brass Key")
        result = key.use(self.player, None)
        self.assertIn("What do you want to use", result)

    def test_locks_unlocked_container(self):
        key = Key(obj_id="k2", name="Iron Key")
        container = Container(obj_id="c1", name="Chest", key_id="k2", locked=False)
        result = key.use(self.player, container)
        self.assertIn("lock the Chest", result)
        self.assertTrue(container.properties["locked"])

    def test_unlocks_locked_container(self):
        key = Key(obj_id="k3", name="Iron Key")
        container = Container(obj_id="c2", name="Chest", key_id="k3", locked=True)
        result = key.use(self.player, container)
        self.assertIn("unlock the Chest", result)
        self.assertFalse(container.properties["locked"])

    def test_wrong_key_does_not_fit(self):
        key = Key(obj_id="k4", name="Wrong Key")
        container = Container(obj_id="c3", name="Vault", key_id="the_right_key", locked=True)
        result = key.use(self.player, container)
        self.assertIn("doesn't fit the lock", result)

    def test_target_without_toggle_lock_reports_cannot_use(self):
        target = Item(obj_id="i1", name="Plain Rock", description="x")
        key = Key(obj_id="k5", name="Any Key")
        result = key.use(self.player, target)
        self.assertIn("can't use", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
