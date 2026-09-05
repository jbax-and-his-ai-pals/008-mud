# tests/singles/test_npc_core_full.py
"""Coverage for engine/npcs/npc.py: get_description's severely-injured and
minor-injuries thresholds, talk()'s in-combat short-circuit, heal()'s dead
guard, die()'s summoned-despawn and respawnable-NPC-queuing paths (plus a
multi-drop loot loop), despawn()'s not-summoned guard, no-owner/no-world
skip, and multi-summon search loop, _handle_safe_zone_regen's cooldown
gate, gain_experience's dead/non-positive guard, level_up(), the
cast_spell/is_hostile_to delegates, and update()'s effect-message-with-
viewer branch, expired economy_impact cleanup, and dying-mid-update skip
of the AI step."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc import NPC
from engine.npcs.npc_factory import NPCFactory


class TestGetDescription(unittest.TestCase):
    def test_severely_injured_threshold(self):
        npc = NPC(name="Test NPC", health=100)
        npc.max_health = 100
        npc.health = 1
        self.assertIn("severely injured", npc.get_description())

    def test_minor_injuries_threshold(self):
        npc = NPC(name="Test NPC", health=100)
        npc.max_health = 100
        npc.health = 65
        self.assertIn("minor injuries", npc.get_description())


class TestTalkAndHeal(unittest.TestCase):
    def test_talk_while_in_combat_short_circuits(self):
        npc = NPC(name="Test NPC")
        npc.in_combat = True
        self.assertIn("too busy fighting", npc.talk())

    def test_heal_while_dead_returns_zero(self):
        npc = NPC(name="Test NPC")
        npc.is_alive = False
        self.assertEqual(npc.heal(10), 0)


class TestDie(GameTestBase):
    def test_summoned_npc_despawns_instead_of_dropping_loot(self):
        npc = NPC(name="Summon", obj_id="npc_core_summon")
        npc.properties["is_summoned"] = True
        result = npc.die(self.world)
        self.assertEqual(result, [])
        self.assertFalse(npc.is_alive)

    def test_respawnable_npc_is_queued(self):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="npc_core_respawnable")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.home_region_id = self.player.current_region_id
        npc.home_room_id = self.player.current_room_id
        npc.faction = "friendly"
        npc.template_id = "village_elder"
        original_len = len(self.world.respawn_manager.respawn_queue)
        npc.die(self.world)
        self.assertGreater(len(self.world.respawn_manager.respawn_queue), original_len)

    def test_multiple_loot_drops_loop_more_than_once(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="npc_core_multi_loot")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.loot_table = {"item_iron_sword": {"chance": 1.0, "quantity": [3, 3]}}
        dropped = npc.die(self.world)
        self.assertEqual(len(dropped), 3)

    def test_failed_loot_item_creation_within_the_drop_loop_is_skipped(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="npc_core_failed_loot")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.loot_table = {"item_iron_sword": {"chance": 1.0, "quantity": [2, 2]}}
        with patch("engine.npcs.npc.ItemFactory.create_item_from_template", return_value=None):
            dropped = npc.die(self.world)
        self.assertEqual(dropped, [])


class TestDespawn(GameTestBase):
    def test_not_summoned_returns_none(self):
        npc = NPC(name="Not Summoned")
        self.assertIsNone(npc.despawn(self.world))

    def test_no_owner_id_skips_summon_cleanup(self):
        npc = NPC(name="Ownerless Summon")
        npc.properties["is_summoned"] = True
        npc.owner_id = None
        result = npc.despawn(self.world)
        self.assertIn("crumbles to dust", result)

    def test_silent_despawn_returns_none_message(self):
        npc = NPC(name="Silent Summon")
        npc.properties["is_summoned"] = True
        result = npc.despawn(self.world, silent=True)
        self.assertIsNone(result)

    def test_multi_entry_summon_search_loops_to_find_match(self):
        npc = NPC(name="Multi Summon", obj_id="npc_core_multi_summon")
        npc.properties["is_summoned"] = True
        npc.owner_id = self.player.obj_id
        self.player.runtime_state.magic.summons = {
            "spell_a": ["some_other_summon_id"],
            "spell_b": ["npc_core_multi_summon"],
        }
        npc.despawn(self.world)
        self.assertNotIn("spell_b", self.player.runtime_state.magic.summons)
        self.assertIn("spell_a", self.player.runtime_state.magic.summons)


class TestSafeZoneRegenAndExperience(unittest.TestCase):
    def test_regen_skipped_before_tick_interval_elapses(self):
        npc = NPC(name="Test NPC")
        npc.last_regen_time = time.time()
        npc.health = 1
        npc._handle_safe_zone_regen(npc.last_regen_time + 0.001)
        self.assertEqual(npc.health, 1)

    def test_gain_experience_while_dead_is_a_noop(self):
        npc = NPC(name="Test NPC")
        npc.is_alive = False
        leveled_up, msg = npc.gain_experience(100)
        self.assertFalse(leveled_up)
        self.assertEqual(msg, "")

    def test_gain_experience_with_non_positive_amount_is_a_noop(self):
        npc = NPC(name="Test NPC")
        leveled_up, msg = npc.gain_experience(0)
        self.assertFalse(leveled_up)

    def test_level_up_increases_level_and_stats(self):
        npc = NPC(name="Test NPC")
        original_level = npc.level
        original_max_health = npc.max_health
        npc.experience_to_level = 1
        npc.experience = 1
        npc.level_up()
        self.assertEqual(npc.level, original_level + 1)
        self.assertGreater(npc.max_health, original_max_health)


class TestCombatDelegates(unittest.TestCase):
    def test_cast_spell_delegates_to_npc_combat(self):
        npc = NPC(name="Test NPC")
        with patch("engine.npcs.npc.npc_combat.cast_spell", return_value={"ok": True}) as mock_cast:
            result = npc.cast_spell("spell", "target", 123.0)
        mock_cast.assert_called_once_with(npc, "spell", "target", 123.0)
        self.assertEqual(result, {"ok": True})

    def test_is_hostile_to_delegates_to_npc_combat(self):
        npc = NPC(name="Test NPC")
        with patch("engine.npcs.npc.npc_combat.is_hostile_to", return_value=True) as mock_hostile:
            result = npc.is_hostile_to("other")
        mock_hostile.assert_called_once_with(npc, "other")
        self.assertTrue(result)


class TestUpdate(GameTestBase):
    def test_effect_message_reaches_colocated_viewer(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="npc_core_update_effect")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.health = 100
        npc.max_health = 100
        npc.active_effects.append({
            "name": "Poison", "type": "dot", "damage_per_tick": 5, "damage_type": "poison",
            "tick_interval": 0, "last_tick_time": 0, "duration_remaining": 100,
        })
        result = npc.update(self.world, time.time())
        self.assertIsNotNone(result)

    def test_expired_economy_impact_is_cleared(self):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="npc_core_econ")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.properties["economy_impact"] = {"expiry": 0}
        npc.update(self.world, time.time())
        self.assertNotIn("economy_impact", npc.properties)

    def test_unexpired_economy_impact_is_kept(self):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="npc_core_econ_unexpired")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.properties["economy_impact"] = {"expiry": time.time() + 1000}
        npc.update(self.world, time.time())
        self.assertIn("economy_impact", npc.properties)

    def test_dying_mid_update_skips_ai_step(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="npc_core_dies_mid_update")
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.health = 1
        npc.max_health = 100
        npc.active_effects.append({
            "name": "Lethal Poison", "type": "dot", "damage_per_tick": 999, "damage_type": "poison",
            "tick_interval": 0, "last_tick_time": 0, "duration_remaining": 100,
        })
        with patch("engine.npcs.npc.npc_ai.handle_ai") as mock_ai:
            npc.update(self.world, time.time())
        mock_ai.assert_not_called()
        self.assertFalse(npc.is_alive)


if __name__ == "__main__":
    unittest.main()
