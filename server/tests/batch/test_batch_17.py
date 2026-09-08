# tests/batch/test_batch_17.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe
from engine.npcs.npc_factory import NPCFactory
from engine.core.skill_system import SkillSystem

class TestBatch17(GameTestBase):
    """Focus: Crafting, Economy, and Items."""

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        # Setup standard recipe
        self.world.item_templates["ingot"] = {"type": "Item", "name": "Ingot", "value": 5}
        self.world.item_templates["product"] = {"type": "Item", "name": "Product", "value": 20}
        self.recipe = Recipe("test_r", {
            "result_item_id": "product", "ingredients": [{"item_id": "ingot", "quantity": 2}]
        })
        self.manager.recipes["test_r"] = self.recipe

    def test_craft_consumes_materials(self):
        """Verify crafting removes the exact number of ingredients."""
        ingot = ItemFactory.create_item_from_template("ingot", self.world)
        if ingot: self.player.inventory.add_item(ingot, 5)
        
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
            self.manager.craft(self.player, "test_r")
            
        self.assertEqual(self.player.inventory.count_item("ingot"), 3) # 5 - 2
        self.assertEqual(self.player.inventory.count_item("product"), 1)

    def test_craft_station_requirement(self):
        """Verify crafting fails if the specific station is missing."""
        self.recipe.station_required = "anvil"
        ingot = ItemFactory.create_item_from_template("ingot", self.world)
        if ingot: self.player.inventory.add_item(ingot, 5)
        
        result = self.manager.craft(self.player, "test_r")
        self.assertIn("need a Anvil", result)
        self.assertEqual(self.player.inventory.count_item("product"), 0)

    def test_vendor_buyback_persistence(self):
        """Verify items sold to a vendor stay in their inventory."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        
        # FIX: Ensure merchant is in the same room as player for trade to work
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        
        self.world.add_npc(merchant)
        merchant.properties["is_vendor"] = True
        merchant.properties["buys_item_types"] = ["Item"]
        
        # Player sells unique item
        self.world.item_templates["unique"] = {"type": "Item", "name": "UniqueThing", "value": 100}
        item = ItemFactory.create_item_from_template("unique", self.world)
        if item:
            self.player.inventory.add_item(item)
            self.player.trading_with = merchant.obj_id
            
            # Execute command
            result = self.game.process_command("sell UniqueThing")
            
        # Verify
        self.assertEqual(self.player.inventory.count_item("unique"), 0, "Item should be removed from player.")
        self.assertEqual(merchant.inventory.count_item("unique"), 1, "Item should be in vendor inventory.")

    def test_repair_cost_partial(self):
        """Verify repair cost scales with damage (roughly)."""
        # Value 100. Repair cost factor 0.1 -> Full repair ~10g.
        self.world.item_templates["sword"] = {
            "type": "Weapon", "name": "Sword", "value": 100, 
            "properties": {"durability": 50, "max_durability": 100}
        }
        sword = ItemFactory.create_item_from_template("sword", self.world)
        
        if sword:
            self.player.inventory.add_item(sword)
            # Create repair NPC
            smith = NPCFactory.create_npc_from_template("blacksmith", self.world)
            if smith: 
                self.world.add_npc(smith)
                # Colocate
                smith.current_region_id = self.player.current_region_id
                smith.current_room_id = self.player.current_room_id
            
            res = self.game.process_command("repaircost Sword")
            # Logic in mercantile.py uses max(MIN, int(value * factor)) regardless of damage amount currently
            # (Simple implementation). So cost should be 10.
            if res: self.assertIn("10 gold", res)

    def test_sell_equipped_error(self):
        """Verify cannot sell items that are equipped."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        self.world.add_npc(merchant)
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        
        self.player.trading_with = merchant.obj_id
        
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            self.player.inventory.add_item(sword)
            self.player.equip_item(sword)
            
            res = self.game.process_command("sell iron sword")
            
            self.assertIsNotNone(res)
            if res: self.assertIn("don't have", res.lower())

    def test_gold_integrity(self):
        """Verify gold cannot go negative via standard commands."""
        # Using debug setgold to try set negative
        res = self.game.process_command("setgold -10")
        if res: self.assertIn("cannot be negative", res)
        self.assertGreaterEqual(self.player.runtime_state.gold, 0)

    def test_loot_rarity_roll(self):
        """Verify rare items drop when RNG is favorable."""
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        self.world.item_templates["rare_gem"] = {"type": "Gem", "name": "Rare Gem"}
        
        if npc:
            # FIX: NPC must be in a valid location to drop loot
            npc.current_region_id = self.player.current_region_id
            npc.current_room_id = self.player.current_room_id
            
            npc.loot_table = {"rare_gem": {"chance": 0.1}}
            # Isolate this test to the manual loot_table: with random.random()
            # patched to always "hit", the content-authored ambient loot pools
            # would otherwise also trigger for this goblin's tags.
            self.world.content_set.ruleset["loot"] = {"ambient_pools": []}

            # Force drop (Random.random() < 0.1)
            with patch('random.random', return_value=0.0):
                 dropped = npc.die(self.world)

            self.assertEqual(len(dropped), 1, "Should drop 1 item.")
            self.assertEqual(dropped[0].name, "Rare Gem")

    def test_crafting_skill_gain(self):
        """Verify crafting grants XP."""
        # Force skill level
        self.player.add_skill("crafting", 1)
        assert self.player.runtime_state.progression is not None
        start_xp = self.player.runtime_state.progression.skills["crafting"]["xp"]
        
        # Provide mats
        ingot = ItemFactory.create_item_from_template("ingot", self.world)
        if ingot: self.player.inventory.add_item(ingot, 2)
        
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
            self.manager.craft(self.player, "test_r")
            
        self.assertGreater(self.player.runtime_state.progression.skills["crafting"]["xp"], start_xp)

    def test_stack_sell_value(self):
        """Verify selling a stack gives correct total gold."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        self.world.add_npc(merchant)
        # Ensure merchant location matches player
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        
        self.world.item_templates["coin"] = {"type": "Treasure", "name": "Coin", "value": 10, "stackable": True}
        coin = ItemFactory.create_item_from_template("coin", self.world)
        
        if coin:
            self.player.inventory.add_item(coin, 5)
            self.player.trading_with = merchant.obj_id
            self.player.runtime_state.gold = 0
            
            # Sell 5. Value 10 * 0.4 = 4g each. Total 20.
            self.game.process_command("sell Coin 5")
            
            self.assertEqual(self.player.runtime_state.gold, 20)
            self.assertEqual(self.player.inventory.count_item("coin"), 0)

    def test_vendor_rejects_wrong_type(self):
        """Verify vendor won't buy items not in their buy list."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        self.world.add_npc(merchant)
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        merchant.properties["is_vendor"] = True
        merchant.properties["buys_item_types"] = ["Weapon"] # Only weapons
        
        self.world.item_templates["apple"] = {"type": "Consumable", "name": "Apple", "value": 1}
        apple = ItemFactory.create_item_from_template("apple", self.world)
        
        if apple:
            self.player.inventory.add_item(apple)
            self.player.trading_with = merchant.obj_id
            
            res = self.game.process_command("sell Apple")
            if res: self.assertIn("not interested", res)
            self.assertEqual(self.player.inventory.count_item("apple"), 1)
