# tests/batch/test_batch_5.py
import time
import os
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.config import PLAYER_REGEN_TICK_INTERVAL

class TestBatch5(GameTestBase):

    def test_hot_application(self):
        """Verify Heal-over-Time (HoT) effects restore health incrementally."""
        # 1. Injure Player
        self.player.max_health = 100
        self.player.health = 50
        
        # 2. Apply HoT Effect (Heal 5 per tick)
        hot_effect = {
            "name": "Regeneration",
            "type": "hot",
            "base_duration": 10.0,
            "heal_per_tick": 5,
            "tick_interval": 1.0,
            "last_tick_time": time.time() # Ready immediately next update
        }
        
        self.player.apply_effect(hot_effect, time.time())
        self.assertTrue(self.player.has_effect("Regeneration"))
        
        # 3. Process Tick (Simulate 1.1 seconds passing)
        # update() calls process_active_effects
        self.player.update(time.time() + 1.1, 1.1)
        
        # 4. Assert Health Increase
        # 50 + 5 = 55 (plus potentially natural regen if safe zone, but we ignore that for now or assume tick interval aligns)
        self.assertGreater(self.player.health, 50)
        self.assertAlmostEqual(self.player.health, 55, delta=1) # Delta allows for minor float/natural regen diffs

    def test_vendor_buyback(self):
        """Verify items sold to a vendor can be bought back (inventory persistence)."""
        # 1. Setup Vendor
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: 
             merchant = NPCFactory.create_npc_from_template("wandering_villager", self.world)
             if merchant:
                 merchant.properties["is_vendor"] = True
                 merchant.properties["buys_item_types"] = ["Treasure"]

        self.assertIsNotNone(merchant, "Failed to create merchant.")
        
        if merchant:
            self.world.add_npc(merchant)
            merchant.current_region_id = self.player.current_region_id
            merchant.current_room_id = self.player.current_room_id
            
            # 2. Give Player Unique Item
            self.world.item_templates["family_heirloom"] = {
                "type": "Treasure", "name": "Heirloom", "value": 100, "stackable": False
            }
            heirloom = ItemFactory.create_item_from_template("family_heirloom", self.world)
            if heirloom:
                self.player.inventory.add_item(heirloom)
                
                # 3. Sell Item
                self.player.trading_with = merchant.obj_id
                self.game.process_command("sell Heirloom")
                
                self.assertEqual(self.player.inventory.count_item("family_heirloom"), 0)
                
                # 4. Verify Vendor Has It
                # Vendors use standard Inventory objects in this engine
                self.assertIsNotNone(merchant.inventory.find_item_by_name("Heirloom"))
                
                # 5. Buy It Back
                # Player needs gold (Sale gave ~40g, Buyback ~200g. Give player gold.)
                self.player.runtime_state.gold = 1000
                self.game.process_command("buy Heirloom")
                
                # 6. Assert Player Has It Again
                self.assertEqual(self.player.inventory.count_item("family_heirloom"), 1)

    def test_durability_stat_impact(self):
        """Verify weapons lose their attack bonus when durability hits 0."""
        # 1. Setup Weapon (10 Damage)
        self.world.item_templates["glass_sword"] = {
            "type": "Weapon", "name": "Glass Sword", "value": 10,
            "properties": { "damage": 10, "durability": 5, "max_durability": 5, "equip_slot": ["main_hand"] }
        }
        
        sword = ItemFactory.create_item_from_template("glass_sword", self.world)
        if sword:
            self.player.inventory.add_item(sword)
            self.player.equip_item(sword)
            
            # 2. Check Power (Base + 10)
            base_power = self.player.runtime_state.combat.attack_power + (self.player.get_effective_stat("strength") // 3)
            armed_power = self.player.get_attack_power()
            self.assertEqual(armed_power, base_power + 10)
            
            # 3. Break Weapon
            sword.update_property("durability", 0)
            
            # 4. Check Power (Should be Base)
            broken_power = self.player.get_attack_power()
            self.assertEqual(broken_power, base_power, "Broken weapon should not grant damage bonus.")

    def test_kill_quest_persistence_interim(self):
        """Verify kill count persists across save/load cycles in the middle of a quest."""
        TEST_SAVE = "test_kill_persist.json"
        
        q_id = "rat_killer_persist"
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "kill", "state": "active", "current_stage_index": 0,
            "title": "Rat Hunt",
            "stages": [{
                "stage_index": 0,
                "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 5, "current_quantity": 0}
            }]
        }
        
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world)
        if rat:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            
        self.assertEqual(self.player.runtime_state.quests.active[q_id]["stages"][0]["objective"]["current_quantity"], 2)
        
        self.world.save_game(TEST_SAVE)
        self.player.runtime_state.quests.active = {}
        self.world.load_save_game(TEST_SAVE)
        loaded_player = self.world.player

        self.assertIsNotNone(loaded_player, "Player should exist after load.")
        
        if loaded_player:
            if rat:
                self.world.dispatch_event("npc_killed", {"player": loaded_player, "npc": rat})
            
            loaded_quest = loaded_player.runtime_state.quests.active.get(q_id)
            self.assertIsNotNone(loaded_quest)
            if loaded_quest:
                self.assertEqual(loaded_quest["stages"][0]["objective"]["current_quantity"], 3)
                
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_container_capacity_rejection(self):
        """Verify putting an item into a full container fails and item remains in inventory."""
        # 1. Setup Small Box (Capacity 2.0)
        self.world.item_templates["small_box"] = {
            "type": "Container", "name": "Small Box", "weight": 1.0,
            "properties": {"capacity": 2.0, "is_open": True}
        }
        box = ItemFactory.create_item_from_template("small_box", self.world)
        
        # 2. Setup Items
        # Heavy Item (Weight 5.0) - Won't fit
        self.world.item_templates["anvil"] = {"type": "Item", "name": "Anvil", "weight": 5.0}
        anvil = ItemFactory.create_item_from_template("anvil", self.world)
        
        if box and anvil:
            self.player.inventory.add_item(box)
            self.player.inventory.add_item(anvil)
            
            # 3. Attempt Put
            result = self.game.process_command("put Anvil in Small Box")
            
            # 4. Assert Failure
            self.assertIsNotNone(result)
            if result:
                self.assertIn("too full", result)
                
            # Verify Anvil still in player inventory
            self.assertEqual(self.player.inventory.count_item("anvil"), 1)
            # Verify Box empty
            self.assertEqual(len(box.properties.get("contains", [])), 0)
