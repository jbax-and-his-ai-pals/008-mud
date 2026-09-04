# tests/singles/test_combat_advanced.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestCombatAdvanced(GameTestBase):
    def test_level_up_mechanics(self):
        """Verify stats and health increase upon leveling up."""
        initial_str = self.player.stats["strength"]
        initial_hp_max = self.player.max_health
        
        # Force level up by giving exact XP needed
        self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
        
        self.assertEqual(self.player.runtime_state.progression.level, 2)
        self.assertGreater(self.player.stats["strength"], initial_str, "Strength should increase on level up")
        self.assertGreater(self.player.max_health, initial_hp_max, "Max HP should increase on level up")
        # Ensure health is healed partially/fully on level up
        self.assertGreater(self.player.health, 1) 

    def test_equipment_bonuses(self):
        """Verify equipping items actually changes derived combat stats."""
        base_attack = self.player.get_attack_power()
        
        # Create a sword with known damage
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        
        if sword:
            self.player.inventory.add_item(sword)
            self.player.equip_item(sword)
            
            new_attack = self.player.get_attack_power()
            weapon_damage = sword.get_property("damage", 0)
            
            # Allow for strength scaling, but ensure it increased by at least weapon damage
            self.assertGreaterEqual(new_attack, base_attack + weapon_damage)

    def test_death_and_respawn_cycle(self):
        """Verify the player death state and respawn relocation."""
        self.player.health = 100
        self.player.is_alive = True
        
        # Force death
        self.player.die(self.world)
        
        self.assertFalse(self.player.is_alive)
        self.assertEqual(self.player.health, 0)
        
        # Respawn
        self.player.respawn()
        
        self.assertTrue(self.player.is_alive)
        self.assertEqual(self.player.health, self.player.max_health)
        self.assertEqual(self.player.current_region_id, self.player.respawn_region_id)
        self.assertEqual(self.player.current_room_id, self.player.respawn_room_id)
