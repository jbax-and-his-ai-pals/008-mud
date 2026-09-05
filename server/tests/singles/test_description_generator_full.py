# tests/singles/test_description_generator_full.py
"""Coverage for engine/world/description_generator.py's generate_room_
description: the no-player/no-game and missing-room/region early returns,
the quest entry-point visual-override append, a friendly NPC's "(Fighting!)"
status suffix, procedural (spell-scroll) item key differentiation, stacked
identical items using the plural/count branch, and item de-duplication by key.

Note: the "if not current_region_id or not current_room_id" check (right
after current_room/current_region are already confirmed non-None) has no
reachable False->body path -- world.get_room_for_player() already returns
None whenever region_id/room_id is falsy, so current_room being truthy
guarantees those ids are truthy too. Left untested as dead code, consistent
with this codebase's established precedent for provably-unreachable branches."""

import unittest

from tests.fixtures import GameTestBase
from engine.world.description_generator import generate_room_description
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory


class TestGenerateRoomDescriptionEarlyReturns(GameTestBase):
    def test_no_player_and_no_reference_player_returns_not_in_world(self):
        self.world.player = None
        result = generate_room_description(self.world, player=None)
        self.assertIn("not yet in the world", result)

    def test_missing_room_returns_nowhere(self):
        self.player.current_region_id = "totally_bogus_region_xyz"
        self.player.current_room_id = "totally_bogus_room_xyz"
        result = generate_room_description(self.world, player=self.player)
        self.assertIn("nowhere", result)


class TestGenerateRoomDescriptionQuestOverride(GameTestBase):
    def test_active_quest_entry_point_description_is_appended(self):
        self.player.runtime_state.quests.active["probe_quest"] = {
            "state": "active",
            "entry_point": {
                "region_id": self.player.current_region_id,
                "room_id": self.player.current_room_id,
                "description_when_visible": "A hidden door creaks open in the wall.",
            },
        }
        # A second matching quest with no description_when_visible exercises
        # the loop's "extra_desc falsy -> keep iterating" branch too.
        self.player.runtime_state.quests.active["probe_quest_no_desc"] = {
            "state": "active",
            "entry_point": {
                "region_id": self.player.current_region_id,
                "room_id": self.player.current_room_id,
            },
        }
        result = generate_room_description(self.world, player=self.player)
        self.assertIn("hidden door creaks open", result)


class TestGenerateRoomDescriptionFriendlyNpcStatus(GameTestBase):
    def test_friendly_npc_in_combat_shows_fighting_suffix(self):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="desc_fighting_elder")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.in_combat = True
        result = generate_room_description(self.world, player=self.player)
        self.assertIn("(Fighting!)", result)


class TestGenerateRoomDescriptionItems(GameTestBase):
    def _add_room_item(self, item_id="item_iron_sword", **overrides):
        item = ItemFactory.create_item_from_template(item_id, self.world, **overrides)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        return item

    def test_procedural_spell_scroll_key_includes_learned_spell(self):
        item = self._add_room_item(
            "item_iron_sword",
            is_procedural=True, procedural_type="random_spell_scroll", spell_to_learn="magic_missile",
        )
        result = generate_room_description(self.world, player=self.player)
        self.assertIn(item.name, result)

    def test_procedural_item_with_other_type_skips_spell_key_suffix(self):
        item = self._add_room_item(
            "item_iron_sword",
            is_procedural=True, procedural_type="something_else",
        )
        result = generate_room_description(self.world, player=self.player)
        self.assertIn(item.name, result)

    def test_two_identical_items_are_counted_and_pluralized(self):
        self._add_room_item("item_iron_sword")
        self._add_room_item("item_iron_sword")
        result = generate_room_description(self.world, player=self.player)
        self.assertIn("2 ", result)


if __name__ == "__main__":
    unittest.main()
