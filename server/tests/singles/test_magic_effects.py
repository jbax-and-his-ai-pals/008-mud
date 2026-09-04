# tests/singles/test_magic_effects.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestMagicEffects(GameTestBase):
    
    def test_summon_cap(self):
        """Verify summoning limits are enforced."""
        summon_spell = Spell(
            spell_id="test_summon", name="Summon Tester", description="x",
            mana_cost=0, cooldown=0.0, target_type="self", level_required=1,
            effects=[{"type": "summon", "summon_template_id": "skeleton_minion", "max_summons": 1, "summon_duration": 100}],
        )
        register_spell(summon_spell)
        self.player.learn_spell("test_summon")
        
        self.player.cast_spell(summon_spell, self.player, time.time(), self.world)
        assert self.player.runtime_state.magic is not None
        self.assertIn("test_summon", self.player.runtime_state.magic.summons)
        self.assertEqual(len(self.player.runtime_state.magic.summons["test_summon"]), 1)
        
        self.player.cast_spell(summon_spell, self.player, time.time(), self.world)
        self.assertEqual(len(self.player.runtime_state.magic.summons["test_summon"]), 2)

    def test_buff_duration(self):
        """Verify buffs expire after duration."""
        # Create Buff Spell
        buff_spell = Spell(
            spell_id="test_buff", name="Speed Buff", description="+10 Agility",
            target_type="self", level_required=1, mana_cost=0, cooldown=0.0,
            effects=[{"type": "apply_effect", "base_duration": 5.0, "effect_data": {"type": "stat_mod", "name": "Speedy", "modifiers": {"agility": 10}}}],
        )
        register_spell(buff_spell)
        self.player.learn_spell("test_buff")
        
        base_agi = self.player.get_effective_stat("agility")
        
        # Cast
        self.player.cast_spell(buff_spell, self.player, time.time())
        self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 10)
        
        # Tick (Not expired yet)
        self.player.process_active_effects(time.time(), 1.0)
        self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 10)
        
        # Tick (Expired)
        # Advance 6.0 seconds. Total 7.0 > 5.0.
        self.player.process_active_effects(time.time(), 6.0)
        
        # Assert stat returned to base
        self.assertEqual(self.player.get_effective_stat("agility"), base_agi)

    def test_debuff_application(self):
        """Verify offensive debuffs apply to enemies."""
        from engine.npcs.npc_factory import NPCFactory
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            debuff_spell = Spell(
                spell_id="test_curse", name="Weakness", description="-5 Str",
                target_type="enemy", level_required=1, mana_cost=0, cooldown=0.0,
                effects=[{"type": "apply_effect", "base_duration": 10.0, "effect_data": {"type": "stat_mod", "name": "Weakened", "modifiers": {"strength": -5}}}],
            )
            register_spell(debuff_spell)
            self.player.learn_spell("test_curse")
            
            base_str = target.get_effective_stat("strength")
            
            self.player.cast_spell(debuff_spell, target, time.time())
            
            self.assertTrue(target.has_effect("Weakened"))
            self.assertEqual(target.get_effective_stat("strength"), base_str - 5)
