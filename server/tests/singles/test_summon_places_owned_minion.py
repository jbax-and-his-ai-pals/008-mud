# tests/singles/test_summon_places_owned_minion.py
"""A summon that is cast has to arrive.

`apply_spell_effect` built the minion with the caster as an override the factory
never read and no location at all, so a minion summoned by a real cast was listed
in the caster's summons and then existed nowhere: it was in no room, it never
followed or fought, and `perform_minion_logic` (which needs both a location and an
owner) had nothing to work with. The minion tests all placed and owned their NPC
by hand, which is why nothing noticed. These tests summon through the spell.
"""
import time

from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs import combat as npc_combat
from engine.npcs.ai import handle_ai
from tests.fixtures import GameTestBase


class TestSummonPlacesOwnedMinion(GameTestBase):

    def setUp(self):
        super().setUp()
        self.spell = Spell(
            spell_id="summon_skeleton_test", name="Summon Test", description="x",
            mana_cost=0, cooldown=0.0, target_type="self", level_required=1,
            effects=[{"type": "summon", "summon_template_id": "skeleton_minion", "summon_duration": 100}],
        )
        register_spell(self.spell)
        self.player.learn_spell("summon_skeleton_test")

    def _summon(self):
        self.player.cast_spell(self.spell, self.player, time.time(), self.world)
        ids = self.player.runtime_state.magic.summons["summon_skeleton_test"]
        return self.world.get_npc(ids[-1])

    def test_the_minion_appears_where_the_caster_stands(self):
        minion = self._summon()
        self.assertEqual((self.player.current_region_id, self.player.current_room_id),
                         (minion.current_region_id, minion.current_room_id))
        self.assertIn(minion, self.world.get_npcs_in_room(self.player.current_region_id, self.player.current_room_id))

    def test_the_minion_knows_its_owner(self):
        self.assertEqual(self.player.obj_id, self._summon().properties.get("owner_id"))

    def test_the_minion_follows_its_owner_when_they_move(self):
        minion = self._summon()
        region = self.world.get_region(self.player.current_region_id)
        room = region.get_room(self.player.current_room_id)
        direction, destination = next(iter(room.exits.items()))
        if ":" in destination:
            self.skipTest("the first exit leaves the region; following across regions is not what this checks")
        self.player.current_room_id = destination
        minion.last_moved = 0
        for step in range(6):
            handle_ai(minion, self.world, time.time() + 100 + step * 10, self.player)
            if minion.current_room_id == destination:
                break
        self.assertEqual(destination, minion.current_room_id)

    def test_the_minion_is_not_despawned_as_ownerless(self):
        minion = self._summon()
        handle_ai(minion, self.world, time.time() + 1, self.player)
        self.assertTrue(minion.is_alive)
        self.assertIn(minion.obj_id, self.world.npcs)


if __name__ == "__main__":
    import unittest
    unittest.main()
