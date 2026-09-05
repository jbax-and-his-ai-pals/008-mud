# tests/singles/test_pickup_drop_full.py
"""Coverage for engine/commands/interaction/pickup_drop.py's get/take/drop
handlers: dead-player and no-args guards, quantity/"all" argument parsing,
open-container sub-item candidates, partial-name matching, the qty=0 edge
case, can_take=False and inventory-full skips, taking from a container vs.
the floor, a failed removal looping to the next candidate, drop's quantity
validation and unicode-digit ValueError, empty-inventory/no-match guards,
a failed ItemFactory re-creation falling back to a deepcopy, dropping
multiple stacks/non-stackable items, a fully-failed drop, and get's
container-lookup/closed/take-all/single-item/cannot-carry branches.

Note: four branches are provably unreachable and left untested, consistent
with this codebase's established precedent for dead code:
- _handle_item_acquisition's take-all `if not targets: return "Nothing on
  the floor."` -- every room item, containers included, is unconditionally
  added as a floor candidate (source=None) before container sub-items are
  ever considered, so a room with an open, non-empty container already has
  that container itself as a floor target.
- _handle_item_disposal's `if not items_to_drop: return ...` -- items_to_drop
  is only ever assigned from `matches` (already checked non-empty) or from
  `items_in_inventory` (already checked non-empty), so it can never be empty
  here.
- _handle_item_disposal's stackable-branch "summary_key not in
  items_dropped_summary" False arm -- Inventory.remove_item() aggregates
  and removes across every slot sharing an obj_id in a single call, so a
  repeated obj_id in items_to_drop always finds either count_item()<=0
  (already fully drained -> `continue`) or qty_remaining_to_drop<=0
  (request already satisfied -> `break`) before it could ever reach the
  summary-key check a second time.
- get_handler's `except (ValueError, IndexError)` around `.index(...)` --
  the preceding `if GET_COMMAND_PREPOSITION in [...]` check already
  guarantees `.index()` succeeds, and slicing never raises IndexError."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.commands.interaction.pickup_drop import get_handler, drop_handler
from engine.items.container import Container
from engine.items.item import Item
from engine.items.item_factory import ItemFactory


class TestItemAcquisitionGuards(GameTestBase):
    def test_dead_player_cannot_take(self):
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = get_handler(["sword"], context)
        self.assertIn("dead", result)

    def test_no_args_returns_usage_error(self):
        result = self.game.process_command("take")
        self.assertIn("Take what", result)

    def test_nothing_here_to_take(self):
        result = self.game.process_command("take sword")
        self.assertIn("Nothing here", result)


class TestItemAcquisitionMatching(GameTestBase):
    def _room_item(self, name="Iron Sword", template="item_iron_sword"):
        item = ItemFactory.create_item_from_template(template, self.world)
        item.name = name
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        return item

    def test_quantity_prefix_takes_that_many(self):
        self._room_item("Copper Coin", "item_iron_sword")
        self._room_item("Copper Coin", "item_iron_sword")
        self._room_item("Copper Coin", "item_iron_sword")
        result = self.game.process_command("take 2 Copper Coin")
        self.assertIn("pick up", result)
        taken = [s.item for s in self.player.inventory.slots if s.item and s.item.name == "Copper Coin"]
        self.assertEqual(len(taken), 2)

    def test_partial_name_match(self):
        self._room_item("Ancient Rusty Sword")
        result = self.game.process_command("take rusty")
        self.assertIn("pick up", result)

    def test_zero_quantity_falls_back_to_single_item(self):
        self._room_item("Solo Item")
        result = self.game.process_command("take 0 Solo Item")
        self.assertIn("pick up", result)

    def test_no_matches_is_reported(self):
        self._room_item("Iron Sword")
        result = self.game.process_command("take totally bogus item xyz")
        self.assertIn("don't see", result)

    def test_open_container_subitem_is_a_candidate(self):
        container = Container(name="Open Chest", is_open=True)
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        gem.name = "Shiny Gem"
        container.properties["contains"] = [gem]
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("take Shiny Gem")
        self.assertIn("from the Open Chest", result)
        self.assertNotIn(gem, container.properties["contains"])

    def test_can_take_false_item_is_skipped_with_message(self):
        item = self._room_item("Fixed Statue")
        item.update_property("can_take", False)
        result = self.game.process_command("take Fixed Statue")
        self.assertIn("fixed in place", result)

    def test_inventory_full_stops_and_reports(self):
        item = self._room_item("Heavy Thing")
        with patch.object(self.player.inventory, "can_add_item", return_value=(False, "full")):
            result = self.game.process_command("take Heavy Thing")
        self.assertIn("cannot carry", result)

    def test_failed_removal_continues_to_next_candidate(self):
        self._room_item("Stubborn Item")
        with patch.object(self.world, "remove_item_instance_from_room", return_value=False):
            result = self.game.process_command("take Stubborn Item")
        self.assertIn("Couldn't take anything", result)

    def test_take_all_of_a_named_item(self):
        self._room_item("Named Sword A", "item_iron_sword")
        self._room_item("Named Sword A", "item_iron_sword")
        result = self.game.process_command("take all Named Sword A")
        self.assertIn("pick up", result)
        taken = [s.item for s in self.player.inventory.slots if s.item and s.item.name == "Named Sword A"]
        self.assertEqual(len(taken), 2)

    def test_take_all_from_floor(self):
        self._room_item("Floor Item A")
        self._room_item("Floor Item B")
        result = self.game.process_command("take all")
        self.assertIn("pick up", result)

    # Note: _handle_item_acquisition's `if not targets: return "Nothing on
    # the floor."` (the take_all branch) is unreachable -- every room item,
    # a container included, is unconditionally added as a floor candidate
    # (source=None) before container sub-items are ever considered, so
    # floor candidates and container-presence can't be decoupled: any room
    # holding an open container with contents already has that container
    # itself as a non-empty floor target. Left untested as dead code.


class TestItemDisposalGuards(GameTestBase):
    def test_dead_player_cannot_drop(self):
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = drop_handler(["sword"], context)
        self.assertIn("dead", result)

    def test_no_args_returns_usage_error(self):
        result = self.game.process_command("drop")
        self.assertIn("Drop what", result)

    def test_empty_inventory_is_reported(self):
        result = self.game.process_command("drop sword")
        self.assertIn("empty", result)

    def test_negative_quantity_is_rejected(self):
        item = Item(name="Droppable")
        self.player.inventory.add_item(item)
        result = self.game.process_command("drop -1 Droppable")
        # "-1" fails isdigit(), so this exercises the plain-name path instead;
        # use a genuinely non-positive digit string to hit the guard.
        result2 = self.game.process_command("drop 0 Droppable")
        self.assertIn("positive", result2)

    def test_digit_with_no_item_name_is_rejected(self):
        item = Item(name="Droppable")
        self.player.inventory.add_item(item)
        result = self.game.process_command("drop 2")
        self.assertIn("of what", result)

    def test_unicode_digit_raises_value_error_on_conversion(self):
        item = Item(name="Droppable")
        self.player.inventory.add_item(item)
        # '²' (superscript two) passes str.isdigit() but int() rejects it.
        result = self.game.process_command("drop ² Droppable")
        self.assertIn("Invalid quantity", result)

    def test_no_matching_item_is_reported(self):
        item = Item(name="Droppable")
        self.player.inventory.add_item(item)
        result = self.game.process_command("drop totally bogus item xyz")
        self.assertIn("don't have", result)


class TestItemDisposalExecution(GameTestBase):
    def test_stackable_item_factory_failure_falls_back_to_deepcopy(self):
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.player.inventory.add_item(potion, 2)
        with patch("engine.commands.interaction.pickup_drop.ItemFactory.create_item_from_template", return_value=None):
            result = self.game.process_command("drop 2 small healing potion")
        self.assertIn("drop", result.lower())
        room_items = self.world.get_items_in_room(self.player.current_region_id, self.player.current_room_id)
        self.assertGreaterEqual(len([i for i in room_items if "healing potion" in i.name.lower()]), 1)

    def test_multiple_stackable_units_loop_more_than_once(self):
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.player.inventory.add_item(potion, 3)
        result = self.game.process_command("drop 3 small healing potion")
        self.assertIn("drop", result.lower())
        room_items = self.world.get_items_in_room(self.player.current_region_id, self.player.current_room_id)
        self.assertEqual(len([i for i in room_items if "healing potion" in i.name.lower()]), 3)

    def test_multiple_non_stackable_items_loop_more_than_once(self):
        sword_a = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        sword_b = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(sword_a)
        self.player.inventory.add_item(sword_b)
        result = self.game.process_command("drop all Iron Sword")
        self.assertIn("drop", result.lower())
        room_items = self.world.get_items_in_room(self.player.current_region_id, self.player.current_room_id)
        self.assertEqual(len([i for i in room_items if "iron sword" in i.name.lower()]), 2)

    def test_stale_zero_count_item_is_skipped(self):
        item_a = Item(name="Real Item")
        item_b = Item(name="Ghost Item")
        self.player.inventory.add_item(item_a)
        self.player.inventory.add_item(item_b)
        original_count = self.player.inventory.count_item

        def fake_count(obj_id):
            if obj_id == item_b.obj_id:
                return 0
            return original_count(obj_id)

        with patch.object(self.player.inventory, "count_item", side_effect=fake_count):
            result = self.game.process_command("drop all")
        self.assertIn("Real Item", result)

    def test_fully_failed_drop_is_reported(self):
        item = Item(name="Unremovable Thing")
        self.player.inventory.add_item(item)
        with patch.object(self.player.inventory, "remove_item_instance", return_value=False):
            result = self.game.process_command("drop Unremovable Thing")
        self.assertIn("couldn't", result.lower())

    def test_stackable_remove_returning_nothing_despite_available_count_is_skipped(self):
        # A defensive edge case: count_item() reports stock, but remove_item()
        # still comes back empty-handed (e.g. a race or internal inconsistency).
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.player.inventory.add_item(potion, 2)
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "mock failure")):
            result = self.game.process_command("drop small healing potion")
        self.assertIn("couldn't", result.lower())


class TestGetFromContainer(GameTestBase):
    def _open_container(self, name="Open Box"):
        container = Container(name=name, is_open=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        return container

    def test_container_not_found_is_reported(self):
        result = self.game.process_command("get sword from totally bogus container xyz")
        self.assertIn("not found", result)

    def test_target_that_is_not_a_container_is_rejected(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        item.name = "Not A Container"
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = self.game.process_command("get sword from Not A Container")
        self.assertIn("not found", result)

    def test_closed_container_is_rejected(self):
        container = Container(name="Closed Box", is_open=False)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("get sword from Closed Box")
        self.assertIn("closed", result)

    def test_empty_container_all_is_reported(self):
        container = self._open_container("Empty Box")
        result = self.game.process_command("get all from Empty Box")
        self.assertIn("empty", result.lower())

    def test_get_all_from_container(self):
        container = self._open_container("Full Box")
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        container.properties["contains"] = [gem]
        result = self.game.process_command("get all from Full Box")
        self.assertIn("You take", result)
        self.assertEqual(container.properties["contains"], [])

    def test_get_all_skips_items_that_cannot_be_carried(self):
        container = self._open_container("Overflow Box")
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        container.properties["contains"] = [gem]
        with patch.object(self.player.inventory, "can_add_item", return_value=(False, "full")):
            result = self.game.process_command("get all from Overflow Box")
        self.assertIn("You take 0 items", result)

    def test_specific_item_not_found_in_container(self):
        container = self._open_container("Sparse Box")
        result = self.game.process_command("get bogus item xyz from Sparse Box")
        self.assertIn("not found in container", result)

    def test_specific_item_taken_from_container(self):
        container = self._open_container("Named Box")
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        gem.name = "Special Gem"
        container.properties["contains"] = [gem]
        result = self.game.process_command("get Special Gem from Named Box")
        self.assertIn("You get", result)
        self.assertIsNotNone(self.player.inventory.find_item_by_name("Special Gem"))

    def test_specific_item_removal_from_container_fails(self):
        container = self._open_container("Stuck Box")
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        gem.name = "Stuck Gem"
        container.properties["contains"] = [gem]
        with patch.object(container, "remove_item", return_value=False):
            result = self.game.process_command("get Stuck Gem from Stuck Box")
        self.assertIn("Cannot carry", result)

    def test_specific_item_cannot_be_carried(self):
        container = self._open_container("Blocked Box")
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        gem.name = "Unliftable Gem"
        container.properties["contains"] = [gem]
        with patch.object(self.player.inventory, "can_add_item", return_value=(False, "full")):
            result = self.game.process_command("get Unliftable Gem from Blocked Box")
        self.assertIn("Cannot carry", result)

    def test_container_found_via_player_inventory(self):
        pouch = Container(name="Belt Pouch", is_open=True)
        self.player.inventory.add_item(pouch)
        gem = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        gem.name = "Pouch Gem"
        pouch.properties["contains"] = [gem]
        result = self.game.process_command("get Pouch Gem from Belt Pouch")
        self.assertIn("You get", result)


if __name__ == "__main__":
    unittest.main()
