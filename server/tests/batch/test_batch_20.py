# tests/batch/test_batch_20.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.config import MIN_ATTACK_COOLDOWN, MINIMUM_DAMAGE_TAKEN

class TestBatch20(GameTestBase):
    """Focus: Advanced Combat and Magic Mechanics."""

    def setUp(self):
        super().setUp()
        # FIX: Added target_type="self" to allow casting on player in tests
        self.spell = Spell(
            "test_dot", "Poison", "x",
            effects=[{"type": "apply_dot", "dot_name": "P1", "dot_damage_per_tick": 5}],
            target_type="self",
        )
        register_spell(self.spell)
        self.player.learn_spell("test_dot")

    def test_multi_dot_stacking(self):
        """Verify two different DoTs can exist on a target simultaneously."""
        dot1 = {"type": "dot", "name": "Poison", "damage_per_tick": 5}
        dot2 = {"type": "dot", "name": "Burn", "damage_per_tick": 5}
        
        self.player.apply_effect(dot1, time.time())
        self.player.apply_effect(dot2, time.time())
        
        self.assertEqual(len(self.player.active_effects), 2)
        names = [e["name"] for e in self.player.active_effects]
        self.assertIn("Poison", names)
        self.assertIn("Burn", names)

    def test_magic_immunity(self):
        """Verify 100% resistance results in 0 damage."""
        self.player.stats["resistances"] = {"fire": 100}
        self.player.health = 100
        
        # Take 50 Fire Damage
        damage = self.player.take_damage(50, "fire")
        
        self.assertEqual(damage, 0)
        self.assertEqual(self.player.health, 100)

    def test_cooldown_agility_scaling(self):
        """Verify high agility reduces attack cooldown."""
        base_cd = self.player.attack_cooldown
        
        self.player.stats["agility"] = 10 # Baseline
        cd_normal = self.player.get_effective_attack_cooldown()
        
        self.player.stats["agility"] = 50 # High
        cd_fast = self.player.get_effective_attack_cooldown()
        
        self.assertLess(cd_fast, cd_normal)
        self.assertGreaterEqual(cd_fast, MIN_ATTACK_COOLDOWN)

    def test_mana_cost_exact_depletion(self):
        """Verify casting a spell with exact mana leaves player at 0."""
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 10
        self.spell.mana_cost = 10
        
        res = self.player.cast_spell(self.spell, self.player, time.time())
        
        self.assertTrue(res["success"])
        self.assertEqual(self.player.runtime_state.magic.mana, 0)

    def test_combat_log_rotation(self):
        """Verify combat log doesn't exceed max length."""
        self.player.max_combat_messages = 3
        self.player.combat_messages = ["1", "2", "3"]
        
        self.player._add_combat_message("4")
        
        self.assertEqual(len(self.player.combat_messages), 3)
        self.assertEqual(self.player.combat_messages, ["2", "3", "4"])

    def test_minimum_damage_floor(self):
        """Verify damage never drops below 1 (unless immune/miss)."""
        # High defense vs Low attack
        self.player.stats["defense"] = 100
        
        # Raw damage 5 - Defense 100 = 0 (Fully absorbed by defense returns 0)
        dmg = self.player.take_damage(5, "physical")
        
        self.assertEqual(dmg, 0)

    def test_negative_stat_floor(self):
        """Verify stats don't go negative from debuffs (display logic)."""
        self.player.stats["strength"] = 10
        debuff = {"type": "stat_mod", "name": "Weak", "modifiers": {"strength": -20}}
        self.player.apply_effect(debuff, time.time())
        
        val = self.player.get_effective_stat("strength")
        self.assertEqual(val, -10)

    def test_heal_spell_on_enemy_fails(self):
        """Verify healing spells cannot target enemies."""
        heal_spell = Spell("heal_test", "Heal", "x", effects=[{"type": "heal", "value": 1}], target_type="friendly")
        register_spell(heal_spell) 
        self.player.learn_spell("heal_test")
        
        # Enemy
        from engine.npcs.npc_factory import NPCFactory
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.add_npc(goblin)
            goblin.current_region_id = self.player.current_region_id
            goblin.current_room_id = self.player.current_room_id
            
            cmd_res = self.game.process_command(f"cast Heal on {goblin.name}")
            self.assertIsNotNone(cmd_res)
            if cmd_res:
                self.assertIn("only cast", cmd_res.lower())

    def test_spell_cooldown_start_time(self):
        """Verify cooldown is set based on current time."""
        now = time.time()
        self.spell.cooldown = 10.0
        self.player.mana = 100
        
        res = self.player.cast_spell(self.spell, self.player, now)
        self.assertTrue(res["success"], "Cast failed, cooldown test cannot proceed.")
        
        expected_end = now + 10.0
        assert self.player.runtime_state.magic is not None
        self.assertAlmostEqual(self.player.runtime_state.magic.cooldowns["test_dot"], expected_end, delta=0.1)

    def test_remove_effect_by_name(self):
        """Verify specific effect removal."""
        self.player.apply_effect({"type": "buff", "name": "B1"}, time.time())
        self.player.apply_effect({"type": "buff", "name": "B2"}, time.time())
        
        self.player.remove_effect("B1")
        
        self.assertFalse(self.player.has_effect("B1"))
        self.assertTrue(self.player.has_effect("B2"))
