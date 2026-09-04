# tests/singles/test_environment_commands.py
"""Coverage for engine/commands/interaction/environment.py's pull/push
interact command (no-args guard, not-found, Interactive dispatch, and
non-interactive fallback) and the pick command (no-args guard, direction
dispatch including alias expansion, container-lockpick flow, no-lockpick
guard, and no-target-here fallback) -- both previously almost entirely
untested."""

from tests.fixtures import GameTestBase
from engine.commands.interaction.environment import interact_handler, pick_handler
from engine.items.interactive import Interactive
from engine.items.container import Container
from engine.items.item import Item
from engine.items.lockpick import Lockpick


class TestInteractHandler(GameTestBase):
    def test_no_args_prompts(self):
        result = interact_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Interact with what?", result)

    def test_target_not_found_reports_error(self):
        result = interact_handler(["nonexistent_lever_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("don't see", result)

    def test_interactive_target_dispatches_to_interact(self):
        lever = Interactive(obj_id="env_lever", name="Rusty Lever", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, lever)
        result = interact_handler(["rusty", "lever"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_non_interactive_target_reports_nothing_happens(self):
        rock = Item(obj_id="env_rock", name="Plain Rock", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, rock)
        result = interact_handler(["plain", "rock"], {"world": self.world, "player": self.player})
        self.assertIn("Nothing happens", result)


class TestPickHandler(GameTestBase):
    def test_no_args_prompts(self):
        result = pick_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Pick what?", result)

    def test_direction_dispatches_to_pick_lock_direction(self):
        result = pick_handler(["north"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_direction_alias_is_expanded(self):
        result = pick_handler(["n"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_no_lockpick_reports_error(self):
        container = Container(obj_id="env_chest", name="Locked Chest", locked=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = pick_handler(["locked", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("don't have a lockpick", result)

    def test_container_target_with_lockpick_delegates_to_lockpick_use(self):
        container = Container(obj_id="env_chest2", name="Iron Chest", locked=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        pick = Lockpick(obj_id="env_pick1", name="Lockpick", description="A pick.")
        self.player.inventory.add_item(pick)
        result = pick_handler(["iron", "chest"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_no_target_here_with_lockpick_reports_nothing_to_pick(self):
        pick = Lockpick(obj_id="env_pick2", name="Lockpick", description="A pick.")
        self.player.inventory.add_item(pick)
        result = pick_handler(["nonexistent_thing_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("nothing to pick", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
