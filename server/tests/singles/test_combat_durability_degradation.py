# tests/singles/test_combat_durability_degradation.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.config import ITEM_DURABILITY_LOSS_ON_HIT

class TestCombatDurabilityDegradation(GameTestBase):

    def test_weapon_breaking(self):
        """Verify weapon loses durability on hit and breaks at 0."""
        # 1. Setup Weapon with low durability
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if not sword: return
        
        start_durability = ITEM_DURABILITY_LOSS_ON_HIT * 2
        sword.update_property("durability", start_durability)
        self.player.inventory.add_item(sword)
        self.player.equip_item(sword, "main_hand")

        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            target.health = 1000 # Ensure it survives hits
            
            # 2. First Hit (Durability reduces)
            with patch('random.random', return_value=0.0): # Force Hit
                self.player.attack(target, self.world)
                
            self.assertEqual(sword.get_property("durability"), start_durability - ITEM_DURABILITY_LOSS_ON_HIT)

            # 3. Second Hit (Durability -> 0, Breaks)
            with patch('random.random', return_value=0.0): # Force Hit
                result = self.player.attack(target, self.world)
            
            self.assertEqual(sword.get_property("durability"), 0)
            self.assertIn("breaks", result["message"])

            # 4. Third Hit (Broken Weapon Logic)
            # Power should drop to unarmed levels
            base_power = self.player.runtime_state.combat.attack_power + (self.player.get_effective_stat("strength") // 3)
            armed_power = self.player.get_attack_power()
            self.assertEqual(armed_power, base_power, "Broken weapon should not add damage.")
