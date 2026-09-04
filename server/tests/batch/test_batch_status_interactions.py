# tests/batch/test_batch_status_interactions.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory

class TestBatchStatusInteractions(GameTestBase):
    
    def test_cleanse_selective_removal(self):
        """Verify 'Cleanse' removes Poison/Curse but KEEPS Buffs."""
        # 1. Apply Mix of Effects
        # Poison (Bad)
        self.player.apply_effect({
            "name": "Deadly Venom", "type": "dot", "tags": ["poison"], 
            "damage_per_tick": 5, "base_duration": 10
        }, time.time())
        
        # Curse (Bad)
        self.player.apply_effect({
            "name": "Rot", "type": "debuff", "tags": ["curse"], "modifiers": {"strength": -5}
        }, time.time())
        
        # Heroism (Good - has tag 'magic' but not 'poison' or 'curse')
        self.player.apply_effect({
            "name": "Heroism", "type": "stat_mod", "tags": ["magic", "buff"], 
            "modifiers": {"strength": 10}
        }, time.time())
        
        self.assertEqual(len(self.player.active_effects), 3)
        
        # 2. Cast Cleanse (Configured to remove poison/curse/disease)
        cleanse = Spell("cleanse_test", "Cleanse", "x", effects=[{"type": "cleanse"}], target_type="friendly")
        register_spell(cleanse)
        self.player.runtime_state.magic.known_spells.add("cleanse_test")
        
        res = self.player.cast_spell(cleanse, self.player, time.time(), self.world)
        
        # 3. Assertions
        self.assertTrue(res["success"])
        self.assertTrue(self.player.has_effect("Heroism"))
        self.assertFalse(self.player.has_effect("Deadly Venom"))
        self.assertFalse(self.player.has_effect("Rot"))

    def test_dot_stacking_different_sources(self):
        """Verify Bleed (Physical) and Poison (Nature) tick independently."""
        # Reset health
        self.player.max_health = 100
        self.player.health = 100
        # Zero out resist/regen for math check
        self.player.stats["magic_resist"] = 0
        self.player.stat_modifiers = {}
        
        # Bleed: 5 dmg/tick
        self.player.apply_effect({
            "name": "Bleed", "type": "dot", "damage_per_tick": 5, "tick_interval": 1.0, "tags": ["bleed"]
        }, time.time())
        
        # Poison: 2 dmg/tick
        self.player.apply_effect({
            "name": "Poison", "type": "dot", "damage_per_tick": 2, "tick_interval": 1.0, "tags": ["poison"]
        }, time.time())
        
        # Update (1 tick)
        self.player.update(time.time() + 1.1, 1.1)
        
        # Expected: 100 - 5 - 2 = 93
        self.assertEqual(self.player.health, 93)

    def test_silence_interrupts_magic(self):
        """Verify Silence prevents casting but allows attacking."""
        # 1. Apply Silence
        # FIX: Ensure 'silence' tag is present to trigger the new Player.can_cast_spell logic
        self.player.apply_effect({
            "name": "Gagged", "type": "debuff", "tags": ["curse", "silence"], "base_duration": 10
        }, time.time())
        
        # 2. Try Cast
        spell = Spell("zap", "Zap", "x", effects=[{"type": "damage", "value": 1}], target_type="enemy")
        register_spell(spell)
        self.player.runtime_state.magic.known_spells.add("zap")
        
        # Needs target
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            target.current_region_id = self.player.current_region_id
            target.current_room_id = self.player.current_room_id
            self.world.add_npc(target)

            res = self.player.cast_spell(spell, target, time.time(), self.world)
            self.assertFalse(res["success"])
            self.assertIn("silenced", res["message"].lower())
            
            # 3. Try Physical Attack (Should work)
            res_att = self.player.attack(target, self.world)
            self.assertNotIn("silenced", res_att["message"].lower())
            self.assertTrue(self.player.runtime_state.combat.in_combat)
