# tests/singles/test_crafting_capacity.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingCapacity(GameTestBase):

    def test_crafting_full_inventory(self):
        """Verify crafting fails safely if inventory is full, even if ingredients would free a slot."""
        # 1. Create Recipe: 1 Ingot -> 2 Daggers (Net +1 slot needed)
        self.world.item_templates["ingot"] = {"type": "Item", "name": "Ingot", "weight": 1}
        self.world.item_templates["dagger"] = {"type": "Weapon", "name": "Dagger", "weight": 1, "stackable": False}
        
        recipe = Recipe("mass_daggers", {
            "result_item_id": "dagger", "result_quantity": 2,
            "ingredients": [{"item_id": "ingot", "quantity": 1}]
        })
        self.game.crafting_manager.recipes["mass_daggers"] = recipe
        
        # 2. Fill Inventory
        self.player.inventory.max_slots = 5
        self.player.inventory.slots = self.player.inventory.slots[:5]

        # Fill 4 slots with dummy items
        for i in range(4):
            dummy = ItemFactory.create_item_from_template("ingot", self.world)
            if dummy: 
                dummy.obj_id = f"dummy_{i}" # Make unique so they don't stack
                self.player.inventory.add_item(dummy)
        
        # Add ingredient to 5th slot
        ingot = ItemFactory.create_item_from_template("ingot", self.world)
        if ingot: self.player.inventory.add_item(ingot)
        
        self.assertEqual(self.player.inventory.get_empty_slots(), 0)
        
        # 3. Attempt Craft
        # PATCH: Ensure skill check passes so we reach the inventory check
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "Success")):
            result = self.game.crafting_manager.craft(self.player, "mass_daggers")
        
        # 4. Assert Failure & Safety
        self.assertIn("Not enough inventory space", result)
        
        self.assertEqual(self.player.inventory.count_item("ingot"), 1, "Ingredient should not be consumed.")