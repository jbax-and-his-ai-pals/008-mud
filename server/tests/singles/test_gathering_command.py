# tests/singles/test_gathering_command.py
"""Coverage for engine/commands/gathering.py's gather/mine/harvest/chop
command: no-args usage error, target not found in room, target found but
not gatherable, and a real ResourceNode delegating to its own gather()."""

from tests.fixtures import GameTestBase
from engine.items.resource_node import ResourceNode
from engine.items.item_factory import ItemFactory


class TestGatherCommand(GameTestBase):
    def setUp(self):
        super().setUp()
        self.node = ResourceNode(
            obj_id="test_ore_vein", name="Ore Vein", description="A vein of ore.",
            resource_item_id="item_iron_sword", tool_required="pickaxe", charges=3,
        )
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, self.node)

    def test_no_args_returns_usage_error(self):
        result = self.game.process_command("gather")
        self.assertIn("Gather from what", result)

    def test_target_not_found_is_reported(self):
        result = self.game.process_command("gather nonexistent thing")
        self.assertIn("don't see", result)

    def test_non_resource_node_target_cannot_be_gathered(self):
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, sword)
        result = self.game.process_command(f"gather {sword.name}")
        self.assertIn("cannot gather", result)

    def test_resource_node_without_tool_reports_missing_tool(self):
        result = self.game.process_command("gather Ore Vein")
        self.assertIn("pickaxe", result)

    def test_alias_mine_delegates_to_resource_node_gather(self):
        pickaxe = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        pickaxe.update_property("tool_type", "pickaxe")
        self.player.inventory.add_item(pickaxe)
        result = self.game.process_command("mine Ore Vein")
        self.assertIn("gather", result.lower())


if __name__ == "__main__":
    import unittest
    unittest.main()
