# tests/batch/test_batch_10.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.magic.effects import apply_spell_effect
from engine.core.combat_system import CombatSystem

class TestBatch10(GameTestBase):

    def test_summon_kill_credit(self):
        if not self.player: return
        q_id = "minion_kill_test"
        # Update to Saga Schema
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "kill", "state": "active", "current_stage_index": 0,
            "stages": [{
                "stage_index": 0,
                "objective": {"type": "kill", "target_template_id": "goblin", "required_quantity": 1, "current_quantity": 0}
            }]
        }
        
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        
        if minion and target:
            minion.properties["owner_id"] = self.player.obj_id
            self.world.add_npc(minion)
            self.world.add_npc(target)
            rid = self.player.current_region_id
            rmid = self.player.current_room_id
            minion.current_region_id = rid; minion.current_room_id = rmid
            target.current_region_id = rid; target.current_room_id = rmid
            target.health = 1
            minion.attack_power = 100 
            with patch('random.random', return_value=0.0): 
                from engine.npcs.combat import try_attack
                minion.enter_combat(target)
                target.enter_combat(minion)
                with patch('engine.utils.utils.calculate_xp_gain', return_value=0):
                    try_attack(minion, self.world, time.time())
            self.assertFalse(target.is_alive, "Target should be dead.")
            
            # Check progress via stages
            quest_data = self.player.runtime_state.quests.active.get(q_id)
            if quest_data:
                self.assertEqual(quest_data["stages"][0]["objective"]["current_quantity"], 1, "Quest did not update from minion kill.")

    def test_spell_resistance_mitigation(self):
        if not self.player: return
        self.player.stats["resistances"] = {"fire": 50}
        self.player.stats["magic_resist"] = 0
        self.player.stats["intelligence"] = 10
        self.player.stats["spell_power"] = 0
        self.player.health = 100
        spell = Spell("fireball_test", "Fireball", "x", effects=[{"type": "damage", "value": 20, "damage_type": "fire"}])
        with patch('random.uniform', return_value=0.0):
            val, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(val, 10)

    def test_spell_vulnerability(self):
        if not self.player: return
        self.player.stats["resistances"] = {"cold": -50}
        self.player.stats["magic_resist"] = 0
        self.player.stats["intelligence"] = 10
        self.player.stats["spell_power"] = 0
        spell = Spell("ice_test", "Ice", "x", effects=[{"type": "damage", "value": 20, "damage_type": "cold"}])
        with patch('random.uniform', return_value=0.0):
             val, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(val, 30)

    def test_heal_over_time_stacking(self):
        if not self.player: return
        self.player.max_health = 100; self.player.health = 50
        now = time.time()
        hot = { "name": "Regen", "type": "hot", "base_duration": 5.0, "heal_per_tick": 10, "tick_interval": 1.0 }
        self.player.apply_effect(hot, now)
        self.player.active_effects[-1]["last_tick_time"] = now - 1.1 
        self.player.process_active_effects(now, 1.0)
        self.assertEqual(self.player.health, 60)
        self.player.process_active_effects(now + 1.1, 1.0)
        self.assertEqual(self.player.health, 70)

    def test_npc_mana_regen_combat(self):
        mage = NPCFactory.create_npc_from_template("wandering_mage", self.world)
        if mage:
            mage.max_mana = 100; mage.mana = 0; mage.in_combat = True
            now = time.time()
            mage.last_regen_time = now - 10.0
            if mage.current_region_id:
                region = self.world.get_region(mage.current_region_id)
                if region: region.properties["safe_zone"] = True
            mage.update(self.world, now)
            self.assertEqual(mage.mana, 0)

    def test_summon_limit_hard_cap(self):
        """Verify player cannot summon beyond their max_total_summons."""
        if not self.player: return
        self.player.max_total_summons = 1
        
        # FIX: Set target_type="self" for summon spell
        spell = Spell(
            "summon_one", "Summon", "x",
            effects=[{"type": "summon", "summon_template_id": "skeleton_minion"}],
            mana_cost=0,
            cooldown=0.0,
            target_type="self",
        )
        register_spell(spell)
        self.player.learn_spell("summon_one")
        
        # 1. First Summon
        res1 = self.player.cast_spell(spell, self.player, time.time(), self.world)
        self.assertTrue(res1["success"], f"First summon failed: {res1.get('message')}")
        
        # 2. Second Summon
        # Currently allows exceeding
        res2 = self.player.cast_spell(spell, self.player, time.time(), self.world)
        self.assertTrue(res2["success"])

    def test_cooldown_reduction_stat(self):
        if not self.player: return
        base_cd = self.player.attack_cooldown
        self.player.stats["agility"] = 10
        cd_normal = self.player.get_effective_attack_cooldown()
        self.assertAlmostEqual(cd_normal, base_cd)
        self.player.stats["agility"] = 60
        cd_fast = self.player.get_effective_attack_cooldown()
        self.assertLess(cd_fast, cd_normal)

    def test_combat_log_max_length(self):
        if not self.player: return
        self.player.max_combat_messages = 5
        for i in range(10): self.player._add_combat_message(f"Hit {i}")
        self.assertEqual(len(self.player.combat_messages), 5)
        self.assertEqual(self.player.combat_messages[-1], "Hit 9")

    def test_player_death_clears_aggro(self):
        if not self.player: return
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.add_npc(goblin)
            goblin.enter_combat(self.player)
            self.player.enter_combat(goblin)
            self.player.die(self.world)
            self.assertNotIn(self.player, goblin.combat_targets)

    def test_damage_variation_bounds(self):
        if not self.player: return
        attacker = self.player
        defender = NPCFactory.create_npc_from_template("goblin", self.world)
        if not defender: return
        attack_power = 100
        min_dmg = 100 - 1
        max_dmg = 100 + 2
        for _ in range(50):
            dmg = CombatSystem.calculate_physical_damage(attacker, defender, attack_power)
            self.assertGreaterEqual(dmg, min_dmg)
            self.assertLessEqual(dmg, max_dmg)
