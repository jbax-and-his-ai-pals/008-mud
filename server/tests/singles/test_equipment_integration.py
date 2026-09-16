# tests/singles/test_equipment_integration.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestEquipmentIntegration(GameTestBase):
    
    def setUp(self):
        super().setUp()
        # Inject templates
        self.world.item_templates["item_leather_cap"] = {
            "type": "Armor", "name": "Leather Cap", "value": 10, "weight": 0.5,
            "properties": { "defense": 1, "equip_slot": ["head"] }
        }
        self.world.item_templates["item_iron_sword"] = {
            "type": "Weapon", "name": "Iron Sword", "value": 50, "weight": 3.0,
            "properties": { "damage": 8, "equip_slot": ["main_hand"] }
        }

    def test_auto_swap_equipment(self):
        """Verify equipping an item to an occupied slot swaps them."""
        # 1. Setup: Two Helmets
        cap1 = ItemFactory.create_item_from_template("item_leather_cap", self.world)
        cap2 = ItemFactory.create_item_from_template("item_leather_cap", self.world)
        
        if not cap1 or not cap2: 
            self.fail("Failed to create test items")
            return
        
        # FIX: Assign unique IDs so inventory removal targets the correct instance
        cap1.obj_id = "cap_1_unique"
        cap2.obj_id = "cap_2_unique"
        
        cap1.name = "Old Cap"
        cap2.name = "New Cap"
        
        self.player.inventory.add_item(cap1)
        self.player.inventory.add_item(cap2)
        
        # 2. Equip First Cap
        self.game.process_command("equip old cap")
        self.assertEqual(self.player.equipment["head"], cap1)
        
        # Verify Old Cap is gone from inventory
        self.assertIsNone(self.player.inventory.find_item_by_name("Old Cap"))
        
        # 3. Equip Second Cap (Should swap)
        result = self.game.process_command("equip new cap")
        
        # 4. Assert Swap
        self.assertIsNotNone(result, "Command processed but returned None")
        if result:
            self.assertIn("unequip the Old Cap", result) # Check feedback message
            
        self.assertEqual(self.player.equipment["head"], cap2)
        
        # Old cap should be back in inventory
        self.assertIsNotNone(self.player.inventory.find_item_by_name("Old Cap"))

    def test_equipped_armor_reduces_damage_taken(self):
        """Equipping armor with a "defense" property must actually reduce
        physical damage taken, not just the get_defense() display number.
        (Regression coverage: this property used to be summed only for
        display -- see Player.get_effective_stat("defense") in
        engine/player/core.py -- and never reached GameObject.take_damage.)"""
        self.player.stats["defense"] = 0
        if self.player.runtime_state.combat is not None:
            self.player.runtime_state.combat.defense = 0
        self.player.stats["dexterity"] = 0
        self.player.max_health = 100
        self.player.health = 100

        unarmored_damage = self.player.take_damage(10, "physical")
        self.assertEqual(unarmored_damage, 10)

        cap = ItemFactory.create_item_from_template("item_leather_cap", self.world)
        self.assertIsNotNone(cap)
        if not cap:
            return
        self.player.inventory.add_item(cap)
        success, _ = self.player.equip_item(cap, "head")
        self.assertTrue(success)

        self.player.health = 100
        armored_damage = self.player.take_damage(10, "physical")
        self.assertEqual(armored_damage, 9)  # 10 - 1 defense from the cap

    def test_slot_validation_command(self):
        """Verify 'equip' command prevents invalid slot usage."""
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword, "Failed to create sword")
        if not sword: return
        
        self.player.inventory.add_item(sword)
        
        # Sword goes in main_hand/off_hand. Try to put on 'head'.
        result = self.game.process_command("equip sword to head")
        
        self.assertIsNotNone(result, "Command processed but returned None")
        if result:
            self.assertIn("cannot be equipped in the 'head'", result)
        self.assertIsNone(self.player.equipment["head"])