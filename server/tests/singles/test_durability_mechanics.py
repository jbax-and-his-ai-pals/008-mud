# tests/singles/test_durability_mechanics.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestDurabilityMechanics(GameTestBase):
    
    def setUp(self):
        super().setUp()
        # Inject templates
        self.world.item_templates["item_iron_sword"] = {
            "type": "Weapon", "name": "Iron Sword", "value": 50, "weight": 3.0,
            "properties": { "damage": 8, "durability": 50, "max_durability": 50, "equip_slot": ["main_hand"] }
        }
        self.world.item_templates["item_leather_tunic"] = {
            "type": "Armor", "name": "Leather Tunic", "value": 25, "weight": 3.0,
            "properties": { "defense": 2, "durability": 50, "max_durability": 50, "equip_slot": ["body"] }
        }

    def test_broken_weapon_damage(self):
        """Verify broken weapons do not contribute to attack power."""
        # 1. Setup
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        if not sword: return

        self.player.inventory.add_item(sword)
        self.player.equip_item(sword, "main_hand")
        
        # 2. Check Base Power (Unarmed + Stats) vs Armed Power
        base_power = self.player.runtime_state.combat.attack_power + (self.player.get_effective_stat("strength") // 3)
        armed_power = self.player.get_attack_power()
        
        self.assertGreater(armed_power, base_power, "Equipped sword should increase attack power.")
        
        # 3. Break the Sword
        sword.update_property("durability", 0)
        
        # 4. Check Power with Broken Weapon
        broken_power = self.player.get_attack_power()
        
        # Logic in Player.get_attack_power checks if durability > 0
        self.assertEqual(broken_power, base_power, "Broken sword should provide no bonus damage.")

    def test_broken_armor_defense(self):
        """Verify broken armor provides no defense."""
        # 1. Setup
        armor = ItemFactory.create_item_from_template("item_leather_tunic", self.world)
        self.assertIsNotNone(armor)
        if not armor: return

        self.player.inventory.add_item(armor)
        self.player.equip_item(armor, "body")
        
        # 2. Baseline Defense
        initial_def = self.player.get_defense()
        
        # Calculate expected base defense (Base + Dex bonus)
        # Assuming defaults: Base 3 + Dex 10 (+2) = 5
        # Armor gives +2. Total 7.
        
        # 3. Break the Armor
        armor.update_property("durability", 0)
        
        # 4. Check Defense
        broken_def = self.player.get_defense()
        self.assertEqual(broken_def, initial_def - armor.get_property("defense"), "Broken armor should lose its defense bonus.")
