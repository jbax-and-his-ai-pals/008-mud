# tests/singles/test_crafting.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCrafting(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        
        # Register a test recipe that requires a station
        self.test_recipe = Recipe("test_sword", {
            "name": "Test Sword",
            "result_item_id": "item_iron_sword",
            "result_quantity": 1,
            "station_required": "anvil", 
            "ingredients": [
                {"item_id": "item_iron_ingot", "quantity": 2}
            ]
        })
        self.manager.recipes["test_sword"] = self.test_recipe

    def test_crafting_station_logic(self):
        """Verify crafting requires specific stations and consumes items."""
        # 1. Give Ingredients
        ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
        if ingot and self.player:
            self.player.inventory.add_item(ingot, 2)
        
        # 2. Attempt Fail (No Station)
        result_fail = self.manager.craft(self.player, "test_sword")
        self.assertIn("need a Anvil", result_fail)
        
        # 3. Add Station to Room
        rid = self.player.current_region_id if self.player else None
        room_id = self.player.current_room_id if self.player else None
        
        if rid and room_id:
            anvil = ItemFactory.create_item_from_template("item_anvil", self.world)
            if anvil: 
                self.world.add_item_to_room(rid, room_id, anvil)
        
        # 4. Attempt Success
        # FIX: Patch the SkillSystem to ensure a deterministic pass on the skill check
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "(Mock Success)")):
            result_success = self.manager.craft(self.player, "test_sword")
            self.assertIsNotNone(result_success)
            if result_success:
                self.assertIn("Successfully crafted", result_success)
        
        # 5. Verify Consumption/Creation
        if self.player:
            self.assertEqual(self.player.inventory.count_item("item_iron_ingot"), 0)
            self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 1)

    def test_repair_mechanic(self):
        """Verify repair costs and execution."""
        # 1. Setup: Damaged Item
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        
        if sword and self.player:
            self.player.inventory.add_item(sword)
            sword.update_property("durability", 10) # Damaged (Max 50)
            
            # 2. Setup: Repair NPC (Blacksmith)
            from engine.npcs.npc_factory import NPCFactory
            smith = NPCFactory.create_npc_from_template("blacksmith", self.world)
            if smith:
                self.world.add_npc(smith)
                # Ensure Player and Smith are in the same location
                smith.current_region_id = self.player.current_region_id
                smith.current_room_id = self.player.current_room_id
            
            # 3. Act: Repair
            self.player.runtime_state.gold = 100
            result = self.game.process_command(f"repair {sword.name}")
            
            # 4. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("repairs your", result)
            
            self.assertEqual(sword.get_property("durability"), sword.get_property("max_durability"))
            self.assertLess(self.player.runtime_state.gold, 100)

    def test_recipe_familiarity_is_recorded_and_reports_authored_milestones(self):
        recipe = Recipe("practice_cap", {
            "name": "Practice Cap",
            "result_item_id": "item_leather_cap",
            "result_quantity": 1,
            "difficulty": 0,
            "ingredients": [],
            "familiarity_milestones": [{"count": 1, "label": "Beginner", "message": "You know the first stitch."}],
        })
        self.manager.recipes[recipe.recipe_id] = recipe

        result = self.manager.craft(self.player, recipe.recipe_id)

        self.assertIn("You know the first stitch.", result)
        self.assertEqual(1, self.player.recipe_craft_counts[recipe.recipe_id])
        cap = self.player.inventory.find_item_by_name("leather cap")
        self.assertEqual(1, cap.get_property("crafted_recipe_count"))
        self.assertEqual("practice_cap", cap.get_property("crafted_recipe_id"))

    def test_recipe_familiarity_survives_a_player_round_trip(self):
        self.player.recipe_craft_counts = {"practice_cap": 3}

        from engine.player.core import Player
        restored = Player.from_dict(self.player.to_dict(self.world), self.world)

        self.assertEqual({"practice_cap": 3}, restored.recipe_craft_counts)

    def test_quality_tiers_apply_deterministically_from_recipe_familiarity(self):
        recipe = Recipe("quality_cap", {
            "name": "Quality Cap",
            "result_item_id": "item_leather_cap",
            "difficulty": 0,
            "ingredients": [],
            "quality_tiers": [
                {"id": "standard", "label": "Standard", "min_crafts": 1, "value_multiplier": 1.0},
                {"id": "fine", "label": "Fine", "min_crafts": 2, "value_multiplier": 2.0, "gift_bonus": 2},
            ],
        })
        self.manager.recipes[recipe.recipe_id] = recipe
        base_value = ItemFactory.create_item_from_template("item_leather_cap", self.world).value

        self.manager.craft(self.player, recipe.recipe_id)
        result = self.manager.craft(self.player, recipe.recipe_id)
        crafted = [
            slot.item for slot in self.player.inventory.slots
            if slot.item is not None and slot.item.get_property("crafted_recipe_id") == recipe.recipe_id
        ]

        self.assertIn("Craft quality: Fine.", result)
        self.assertEqual(["standard", "fine"], [item.get_property("craft_quality") for item in crafted])
        self.assertEqual([base_value, base_value * 2], [item.value for item in crafted])
        self.assertEqual(2, crafted[-1].get_property("gift_quality_bonus"))

    def test_quality_enabled_stackables_remain_distinct_inventory_instances(self):
        recipe = Recipe("quality_posy", {
            "name": "Quality Posy",
            "result_item_id": "item_wildflower_posy",
            "difficulty": 0,
            "ingredients": [],
            "quality_tiers": [
                {"id": "standard", "label": "Standard", "min_crafts": 1},
                {"id": "fine", "label": "Fine", "min_crafts": 2, "value_multiplier": 2.0},
            ],
        })
        self.manager.recipes[recipe.recipe_id] = recipe

        self.manager.craft(self.player, recipe.recipe_id)
        self.manager.craft(self.player, recipe.recipe_id)
        crafted = [
            slot for slot in self.player.inventory.slots
            if slot.item is not None and slot.item.get_property("crafted_recipe_id") == recipe.recipe_id
        ]

        self.assertEqual(2, len(crafted))
        self.assertEqual(["standard", "fine"], [slot.item.get_property("craft_quality") for slot in crafted])
        self.assertTrue(all(not slot.item.stackable and slot.quantity == 1 for slot in crafted))
