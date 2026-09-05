# tests/singles/test_use_give_full.py
"""Coverage for engine/commands/interaction/use_give.py's use/give command
handlers: dead-player guards, no-args/missing-preposition usage errors,
"on"-preposition target parsing, all three target-resolution fallbacks
(room item, other inventory item, NPC) plus the self/me alias, item-not-
found and target-not-found errors, a Key used with no target, item.use()
raising an exception, give's quest-delivery matching (wrong-recipient
rejection, non-active and non-deliver quests being skipped, failed item
removal), and the standard (non-quest) gift path including the
no-inventory-attribute recipient edge case.

Note: give_handler's `except (ValueError, AttributeError)` around
`.index(GIVE_COMMAND_PREPOSITION)` is unreachable -- the preceding `if
GIVE_COMMAND_PREPOSITION not in [...]` check already guarantees the value
is present, so `.index()` can never raise. Left untested as dead code,
consistent with this codebase's established precedent."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.items.item import Item
from engine.items.key import Key
from engine.commands.interaction.use_give import use_handler, give_handler


class TestUseHandler(GameTestBase):
    def test_dead_player_cannot_use_items(self):
        # process_command() itself gates dead players before commands not in
        # its allowlist ever dispatch, so use_handler's own check needs a
        # direct call to reach it.
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = use_handler(["potion"], context)
        self.assertIn("dead", result)

    def test_no_args_returns_usage_error(self):
        result = self.game.process_command("use")
        self.assertIn("Use what", result)

    def test_item_not_in_inventory_is_reported(self):
        result = self.game.process_command("use totally bogus item xyz")
        self.assertIn("don't have", result)

    def test_target_resolves_to_room_item(self):
        key = Key(name="Test Key", target_id="test_chest")
        self.player.inventory.add_item(key)
        chest = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, chest)
        result = self.game.process_command(f"use Test Key on {chest.name}")
        self.assertNotIn("not found", result)

    def test_target_resolves_to_other_inventory_item(self):
        key = Key(name="Test Key", target_id="test_lockbox")
        lockbox = Item(name="Lockbox")
        self.player.inventory.add_item(key)
        self.player.inventory.add_item(lockbox)
        result = self.game.process_command("use Test Key on Lockbox")
        self.assertNotIn("not found", result)

    def test_target_resolves_to_npc_in_room(self):
        key = Key(name="Test Key", target_id="nothing")
        self.player.inventory.add_item(key)
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="use_target_npc")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        result = self.game.process_command(f"use Test Key on {npc.name}")
        self.assertNotIn("not found", result)

    def test_target_resolves_to_self_via_alias(self):
        key = Key(name="Test Key", target_id="nothing")
        self.player.inventory.add_item(key)
        result = self.game.process_command("use Test Key on self")
        self.assertNotIn("not found", result)

    def test_unresolvable_target_is_reported(self):
        key = Key(name="Test Key", target_id="nothing")
        self.player.inventory.add_item(key)
        result = self.game.process_command("use Test Key on totally bogus target xyz")
        self.assertIn("not found", result)

    def test_key_without_target_reports_usage_error(self):
        key = Key(name="Test Key", target_id="nothing")
        self.player.inventory.add_item(key)
        result = self.game.process_command("use Test Key")
        self.assertIn("Use key on what", result)

    def test_use_raising_exception_is_caught(self):
        item = Item(name="Broken Item")
        self.player.inventory.add_item(item)
        with patch.object(item, "use", side_effect=RuntimeError("boom")):
            with patch.object(self.player.inventory, "find_item_by_name", return_value=item):
                result = self.game.process_command("use Broken Item")
        self.assertIn("Failed to use item", result)


class TestGiveHandler(GameTestBase):
    def _recipient(self, instance_id="give_recipient"):
        # The base content set's starting room already has a default NPC
        # named "Elder Thorne" -- give this one a distinct name so
        # find_npc_in_room_for_player() can't resolve the wrong instance.
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id=instance_id)
        self.world.add_npc(npc)
        npc.name = f"Unique Recipient {instance_id}"
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        return npc

    def test_dead_player_cannot_give(self):
        # Same story as use_handler: process_command() gates dead players
        # before "give" (not in its allowlist) ever dispatches.
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = give_handler(["sword", "to", "bob"], context)
        self.assertIn("dead", result)

    def test_missing_preposition_returns_usage_error(self):
        result = self.game.process_command("give sword bob")
        self.assertIn("Usage: give", result)

    def test_item_not_in_inventory_is_reported(self):
        recipient = self._recipient()
        result = self.game.process_command(f"give bogus item xyz to {recipient.name}")
        self.assertIn("don't have", result)

    def test_npc_not_found_is_reported(self):
        item = Item(name="Gift Item")
        self.player.inventory.add_item(item)
        result = self.game.process_command("give Gift Item to totally bogus npc xyz")
        self.assertIn("not found", result)

    def test_standard_gift_transfers_item_to_npc_inventory(self):
        recipient = self._recipient()
        item = Item(name="Gift Item")
        self.player.inventory.add_item(item)
        result = self.game.process_command(f"give Gift Item to {recipient.name}")
        self.assertIn("You give", result)
        self.assertIsNotNone(recipient.inventory.find_item_by_name("Gift Item"))

    def test_standard_gift_to_recipient_without_inventory_attribute(self):
        recipient = self._recipient("give_recipient_no_inv")
        item = Item(name="Gift Item")
        self.player.inventory.add_item(item)
        del recipient.inventory
        result = self.game.process_command(f"give Gift Item to {recipient.name}")
        self.assertIn("You give", result)

    def test_standard_gift_removal_failure_is_reported(self):
        recipient = self._recipient("give_recipient_removal_fail")
        item = Item(name="Gift Item")
        self.player.inventory.add_item(item)
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "mock failure")):
            result = self.game.process_command(f"give Gift Item to {recipient.name}")
        self.assertIn("Failed to remove item", result)

    def _quest_setup(self, package_id, recipient_instance_id, extra_active=None):
        # extra_active entries are inserted BEFORE the real quest so the
        # scan loop actually walks past (and skips) them before finding its
        # match -- inserting them after would never be reached, since the
        # loop `break`s on the first match.
        if extra_active:
            self.player.runtime_state.quests.active.update(extra_active)
        objective_data = {
            "type": "deliver",
            "item_instance_id": package_id,
            "recipient_instance_id": recipient_instance_id,
            "item_to_deliver_name": "Package",
        }
        self.player.runtime_state.quests.active["test_deliver"] = {
            "instance_id": "test_deliver", "type": "deliver", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "sender",
            "rewards": {"xp": 10},
            "objective": objective_data,
            "stages": [{"stage_index": 0, "turn_in_id": recipient_instance_id, "objective": objective_data}],
        }
        package = ItemFactory.create_item_from_template("quest_package_generic", self.world)
        package.obj_id = package_id
        package.name = "Package"
        self.player.inventory.add_item(package)
        return package

    def test_quest_delivery_to_wrong_recipient_is_rejected(self):
        correct_recipient = self._recipient("quest_correct_recipient")
        wrong_recipient = self._recipient("quest_wrong_recipient")
        self._quest_setup("pkg_wrong_recipient", "quest_correct_recipient")
        result = self.game.process_command(f"give Package to {wrong_recipient.name}")
        self.assertIn("should give", result)

    def test_inactive_quest_entry_is_skipped_in_the_scan(self):
        recipient = self._recipient("quest_inactive_scan_recipient")
        self._quest_setup(
            "pkg_inactive_scan", "quest_inactive_scan_recipient",
            extra_active={"inactive_quest": {"state": "completed", "objective": {}}},
        )
        result = self.game.process_command(f"give Package to {recipient.name}")
        self.assertIn("Quest Complete", result)

    def test_non_deliver_active_quest_is_skipped_in_the_scan(self):
        recipient = self._recipient("quest_non_deliver_recipient")
        self._quest_setup(
            "pkg_non_deliver", "quest_non_deliver_recipient",
            extra_active={"kill_quest": {"state": "active", "objective": {"type": "kill"}}},
        )
        result = self.game.process_command(f"give Package to {recipient.name}")
        self.assertIn("Quest Complete", result)

    def test_quest_delivery_removal_failure_is_reported(self):
        recipient = self._recipient("quest_removal_fail_recipient")
        self._quest_setup("pkg_removal_fail", "quest_removal_fail_recipient")
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "mock failure")):
            result = self.game.process_command(f"give Package to {recipient.name}")
        self.assertIn("Failed to remove item", result)


if __name__ == "__main__":
    unittest.main()
