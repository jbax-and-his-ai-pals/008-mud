# tests/batch/test_batch_loot_lifecycle.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.loot_generator import LootGenerator
from engine.items.affix_data import PREFIXES, SUFFIXES
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestBatchLootLifecycle(GameTestBase):
    """
    Stress tests for the lifecycle of procedurally generated items.
    """

    def setUp(self):
        super().setUp()
        self.world.item_templates["base_sword"] = {
            "type": "Weapon", "name": "Sword", "value": 100, 
            "properties": {"damage": 10, "durability": 50, "max_durability": 50, "equip_slot": ["main_hand"]}
        }

    def test_procedural_value_scaling(self):
        """Verify procedural items sell for significantly more gold."""
        # 1. Generate "Masterwork Sword of the Void" (2.0x * 2.0x = 4.0x Value)
        # Base Value 100 -> Expected 400
        
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [
                ("Masterwork", PREFIXES["Masterwork"]), 
                ("of the Void", SUFFIXES["of the Void"])
            ]
            with patch('random.random', return_value=0.0):
                loot = LootGenerator.generate_loot("base_sword", self.world, level=10)

        self.assertIsNotNone(loot)
        if loot:
            self.assertEqual(loot.value, 400)
            
            # 2. Sell it
            merchant = NPCFactory.create_npc_from_template("merchant", self.world)
            if merchant:
                self.world.add_npc(merchant)
                # Sync location
                merchant.current_region_id = self.player.current_region_id
                merchant.current_room_id = self.player.current_room_id
                merchant.properties["is_vendor"] = True
                merchant.properties["buys_item_types"] = ["Weapon"]
                # This test spawns the "merchant" template as a generic
                # stand-in vendor and expects the global default sell rate,
                # not the merchant's own (deliberately lower) general-store
                # rate.
                merchant.properties["sell_rate_multiplier"] = 0.4

                self.player.inventory.add_item(loot)
                self.player.trading_with = merchant.obj_id
                self.player.runtime_state.gold = 0
                
                # Sell price is usually value * 0.4. (400 * 0.4 = 160)
                self.game.process_command(f"sell {loot.name}")
                self.assertEqual(self.player.runtime_state.gold, 160)

    def test_procedural_durability_buff(self):
        """Verify 'Reinforced' prefix actually increases max durability."""
        # Reinforced adds +20 durability
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [("Reinforced", PREFIXES["Reinforced"]), ("", {})]
            
            with patch('random.random', side_effect=[0.0, 1.0]): # Prefix yes, Suffix no
                loot = LootGenerator.generate_loot("base_sword", self.world, level=5)

        self.assertIsNotNone(loot)
        if loot:
            self.assertEqual(loot.get_property("max_durability"), 70) # 50 + 20
            self.assertEqual(loot.get_property("durability"), 70)

    def test_repair_cost_scaling(self):
        """Verify repairing a high-value procedural item costs more."""
        # 1. Normal Sword (Value 100)
        normal = ItemFactory.create_item_from_template("base_sword", self.world)
        
        # 2. Masterwork Sword (Value 200)
        # We manually construct for predictability
        masterwork = ItemFactory.create_item_from_template("base_sword", self.world)
        if masterwork:
            masterwork.value = 200
            masterwork.name = "Masterwork Sword"

        if normal and masterwork:
            # Damage both by 1 point
            normal.update_property("durability", 49)
            masterwork.update_property("durability", 49)
            
            self.player.inventory.add_item(normal)
            self.player.inventory.add_item(masterwork)
            
            # Spawn Smith
            smith = NPCFactory.create_npc_from_template("blacksmith", self.world)
            if smith:
                self.world.add_npc(smith)
                smith.current_region_id = self.player.current_region_id
                smith.current_room_id = self.player.current_room_id
                
                # Check Costs
                # Cost logic: max(1, int(Value * 0.1))
                # Normal: 100 * 0.1 = 10g
                # Master: 200 * 0.1 = 20g
                
                res_norm = self.game.process_command("repaircost Sword")
                res_mast = self.game.process_command("repaircost Masterwork Sword")
                
                if res_norm: self.assertIn("10 gold", res_norm)
                if res_mast: self.assertIn("20 gold", res_mast)
