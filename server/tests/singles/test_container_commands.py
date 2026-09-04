# tests/singles/test_container_commands.py
"""Coverage for engine/commands/interaction/containers.py's open/close/put
handlers: dead-player and no-args guards, room-vs-inventory target lookup,
non-container-target errors, put's preposition parsing (missing/malformed),
item-not-found/container-not-found (room and inventory) lookups, the
self-nesting and recursive-nesting guards, can_add rejection, and the
successful-put/failed-add-back-to-inventory paths."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.commands.interaction.containers import open_handler, close_handler, put_handler
from engine.items.container import Container
from engine.items.item import Item


class TestOpenHandler(GameTestBase):
    def test_dead_player_cannot_open(self):
        self.player.is_alive = False
        result = open_handler(["chest"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_prompts(self):
        result = open_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Open what?", result)

    def test_target_not_found_reports_error(self):
        result = open_handler(["nonexistent_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("don't see", result)

    def test_non_container_target_reports_error(self):
        item = Item(obj_id="oc_item", name="Plain Rock", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = open_handler(["plain", "rock"], {"world": self.world, "player": self.player})
        self.assertIn("not a container", result)

    def test_finds_container_in_room(self):
        container = Container(obj_id="oc_room_chest", name="Room Chest")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = open_handler(["room", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("open the Room Chest", result)

    def test_finds_container_in_inventory(self):
        container = Container(obj_id="oc_inv_chest", name="Pocket Box")
        self.player.inventory.add_item(container)
        result = open_handler(["pocket", "box"], {"world": self.world, "player": self.player})
        self.assertIn("open the Pocket Box", result)


class TestCloseHandler(GameTestBase):
    def test_dead_player_cannot_close(self):
        self.player.is_alive = False
        result = close_handler(["chest"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_prompts(self):
        result = close_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Close what?", result)

    def test_target_not_found_reports_error(self):
        result = close_handler(["nonexistent_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("don't see", result)

    def test_non_container_target_reports_error(self):
        item = Item(obj_id="cc_item", name="Plain Stick", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = close_handler(["plain", "stick"], {"world": self.world, "player": self.player})
        self.assertIn("Not a container", result)

    def test_closes_container_in_inventory(self):
        container = Container(obj_id="cc_inv_chest", name="Pocket Box", is_open=True)
        self.player.inventory.add_item(container)
        result = close_handler(["pocket", "box"], {"world": self.world, "player": self.player})
        self.assertIn("close the Pocket Box", result)


class TestPutHandler(GameTestBase):
    def test_dead_player_cannot_put(self):
        self.player.is_alive = False
        result = put_handler(["dagger", "in", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_missing_preposition_reports_usage(self):
        result = put_handler(["dagger", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("Usage: put", result)

    def test_item_not_in_inventory_reports_error(self):
        container = Container(obj_id="put_chest1", name="Chest", is_open=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = put_handler(["dagger", "in", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("don't have", result)

    def test_container_not_found_anywhere_reports_error(self):
        item = Item(obj_id="put_item1", name="Dagger", description="x")
        self.player.inventory.add_item(item)
        result = put_handler(["dagger", "in", "nonexistent_container_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("don't see a container", result)

    def test_finds_container_in_inventory_when_not_in_room(self):
        item = Item(obj_id="put_item2", name="Dagger", description="x", weight=1.0)
        container = Container(obj_id="put_chest2", name="Pocket Box", is_open=True, capacity=10.0)
        self.player.inventory.add_item(item)
        self.player.inventory.add_item(container)
        result = put_handler(["dagger", "in", "pocket", "box"], {"world": self.world, "player": self.player})
        self.assertIn("You put the Dagger in the Pocket Box", result)

    def test_cannot_put_item_inside_itself(self):
        container = Container(obj_id="put_self_chest", name="Self Chest", is_open=True)
        self.player.inventory.add_item(container)
        result = put_handler(["self", "chest", "in", "self", "chest"], {"world": self.world, "player": self.player})
        self.assertIn("inside itself", result)

    def test_cannot_put_container_inside_its_own_nested_content(self):
        outer = Container(obj_id="put_outer", name="Outer Box", is_open=True, capacity=50.0)
        inner = Container(obj_id="put_inner", name="Inner Box", is_open=True, capacity=50.0)
        outer.properties["contains"] = [inner]
        self.player.inventory.add_item(outer)
        self.player.inventory.add_item(inner)
        result = put_handler(["outer", "box", "in", "inner", "box"], {"world": self.world, "player": self.player})
        self.assertIn("already inside", result)

    def test_cannot_put_container_inside_deeply_nested_content(self):
        outer = Container(obj_id="put_outer2", name="Grandparent Box", is_open=True, capacity=50.0)
        decoy = Container(obj_id="put_decoy2", name="Decoy Box", is_open=True, capacity=50.0)
        middle = Container(obj_id="put_middle2", name="Parent Box", is_open=True, capacity=50.0)
        target = Container(obj_id="put_target2", name="Child Box", is_open=True, capacity=50.0)
        middle.properties["contains"] = [target]
        # decoy comes first and contains nothing matching -- forces the
        # recursive check() to return False for it (continuing the loop)
        # before the second entry (middle) actually finds the target.
        outer.properties["contains"] = [decoy, middle]
        self.player.inventory.add_item(outer)
        self.player.inventory.add_item(target)
        result = put_handler(["grandparent", "box", "in", "child", "box"], {"world": self.world, "player": self.player})
        self.assertIn("already inside", result)

    def test_remove_item_failure_reports_error(self):
        item = Item(obj_id="put_item5", name="Slippery Gem", description="x", weight=1.0)
        container = Container(obj_id="put_chest5", name="Odd Box2", is_open=True, capacity=10.0)
        self.player.inventory.add_item(item)
        self.player.inventory.add_item(container)
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "")):
            result = put_handler(["slippery", "gem", "in", "odd", "box2"], {"world": self.world, "player": self.player})
        self.assertIn("Failed to remove item from inventory", result)

    def test_can_add_rejection_is_reported(self):
        item = Item(obj_id="put_item3", name="Boulder", description="x", weight=5.0)
        container = Container(obj_id="put_chest3", name="Tiny Box", is_open=True, capacity=1.0)
        self.player.inventory.add_item(item)
        self.player.inventory.add_item(container)
        result = put_handler(["boulder", "in", "tiny", "box"], {"world": self.world, "player": self.player})
        self.assertIn("too full", result)

    def test_add_item_failure_returns_item_to_inventory(self):
        item = Item(obj_id="put_item4", name="Gem", description="x", weight=1.0)
        container = Container(obj_id="put_chest4", name="Odd Box", is_open=True, capacity=10.0)
        self.player.inventory.add_item(item)
        self.player.inventory.add_item(container)
        with patch.object(container, "add_item", return_value=False):
            result = put_handler(["gem", "in", "odd", "box"], {"world": self.world, "player": self.player})
        self.assertIn("Failed to add item", result)
        self.assertIsNotNone(self.player.inventory.find_item_by_name("gem"))


if __name__ == "__main__":
    import unittest
    unittest.main()
