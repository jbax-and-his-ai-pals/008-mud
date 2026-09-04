# tests/singles/test_npc_spell_combat.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs import combat as npc_combat
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
import time

class TestNPCSpellCombat(GameTestBase):

    def setUp(self):
        super().setUp()
        # Create a test spell
        self.spell = Spell(
            spell_id="npc_blast", name="NPC Blast", description="Boom",
            mana_cost=10, cooldown=5.0, effects=[{"type": "damage", "value": 20}],
            target_type="enemy", level_required=1,
            cast_message="{caster_name} casts {spell_name}!"
        )
        register_spell(self.spell)
        
        # Setup Mage NPC
        self.mage = NPCFactory.create_npc_from_template("wandering_mage", self.world)
        if self.mage:
            self.mage.usable_spells = ["npc_blast"]
            self.mage.mana = 50
            self.mage.spell_cast_chance = 1.0 # Force spell usage
            self.mage.combat_cooldown = 0
            
            self.world.add_npc(self.mage)
            # Sync location
            self.mage.current_region_id = self.player.current_region_id
            self.mage.current_room_id = self.player.current_room_id

    def test_npc_casts_offensive_spell(self):
        """Verify NPC casts damage spell in combat."""
        if not self.mage: return
        
        # 1. Enter Combat
        self.mage.enter_combat(self.player)
        
        start_hp = self.player.health
        
        # 2. Trigger AI Attack
        # Patch random to ensure spell cast check passes (though we set chance to 1.0)
        with patch('random.random', return_value=0.0):
            result_msg = npc_combat.try_attack(self.mage, self.world, time.time())
            
        # 3. Assertions
        self.assertIsNotNone(result_msg)
        if result_msg:
            self.assertIn("casts NPC Blast", result_msg)
            
        # Check Player Damage (20 base + variance)
        self.assertLess(self.player.health, start_hp)
        
        # Check NPC Mana consumption
        self.assertEqual(self.mage.mana, 40) # 50 - 10
