# tests/singles/test_economy_repair.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestEconomyRepair(GameTestBase):
    
    def test_repair_costs_and_logic(self):
        """Verify repair calculations and execution."""
        # 1. Setup: Create a Blacksmith
        smith = NPCFactory.create_npc_from_template("blacksmith", self.world)
        self.assertIsNotNone(smith)
        
        if smith:
            self.world.add_npc(smith)
            smith.current_region_id = self.player.current_region_id
            smith.current_room_id = self.player.current_room_id
            
            # 2. Give Player a damaged item
            sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            self.assertIsNotNone(sword)
            
            if sword:
                self.player.inventory.add_item(sword)
                
                # Damage it: Max durability is usually 50 for iron sword
                max_durability = sword.get_property("max_durability", 50)
                sword.update_property("durability", 10) # Heavily damaged
                
                # Set Item Value (e.g. 50 gold)
                sword.value = 50
                
                # 3. Setup Player Gold
                # Cost is roughly: Value * 0.1 * (percentage lost)? 
                # Config says: REPAIR_COST_PER_VALUE_POINT = 0.1
                # Logic says: cost = item.value * REPAIR_COST_PER_VALUE_POINT (flat rate in current implementation? lets check logic)
                # Logic in mercantile.py: max(MIN_COST, int(item.value * REPAIR_COST_PER_VALUE_POINT))
                # So it's a flat fee based on value, regardless of how damaged it is (in current simple implementation)
                expected_cost = int(50 * 0.1) # = 5
                
                self.player.runtime_state.gold = 100
                
                # 4. Check Cost Command
                result_cost = self.game.process_command(f"repaircost {sword.name}")
                self.assertIsNotNone(result_cost)
                if result_cost:
                    self.assertIn(str(expected_cost), result_cost)
                
                # 5. Execute Repair
                result_repair = self.game.process_command(f"repair {sword.name}")
                self.assertIsNotNone(result_repair)
                if result_repair:
                    self.assertIn("perfect condition", result_repair)
                
                # 6. Verify State
                self.assertEqual(sword.get_property("durability"), max_durability)
                self.assertEqual(self.player.runtime_state.gold, 100 - expected_cost)

    def test_repair_too_poor(self):
        """Verify repair fails if player lacks gold."""
        smith = NPCFactory.create_npc_from_template("blacksmith", self.world)
        if smith:
            self.world.add_npc(smith)
            # Colocate
            smith.current_region_id = self.player.current_region_id
            smith.current_room_id = self.player.current_room_id
            
            sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            if sword:
                self.player.inventory.add_item(sword)
                sword.update_property("durability", 1)
                
                self.player.runtime_state.gold = 0
                
                result = self.game.process_command(f"repair {sword.name}")
                self.assertIsNotNone(result)
                if result:
                    # Corrected assertion to match actual game message format
                    # Message: "You need X gold to repair..., but you only have Y."
                    self.assertIn("you need", result.lower())
                    self.assertIn("but you only have", result.lower())
                
                # Verify NOT repaired
                self.assertEqual(sword.get_property("durability"), 1)
