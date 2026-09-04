# tests/batch/test_batch_loot.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.loot_generator import LootGenerator
from engine.items.affix_data import PREFIXES, SUFFIXES
from engine.items.container import Container

class TestBatchLoot(GameTestBase):
    """
    Focus: Procedural generation of items, affixes, and stat merging.
    """

    def setUp(self):
        super().setUp()
        # Inject a base template for testing
        self.world.item_templates["test_sword"] = {
            "type": "Weapon", "name": "Sword", "value": 100, "weight": 5.0,
            "properties": {"damage": 10, "equip_slot": ["main_hand"]}
        }
        self.world.item_templates["test_armor"] = {
            "type": "Armor", "name": "Tunic", "value": 100, "weight": 5.0,
            "properties": {"defense": 5, "equip_slot": ["body"]}
        }

    def test_prefix_application(self):
        """Verify Sharp prefix increases damage."""
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [("Sharp", PREFIXES["Sharp"]), ("", {})] 
            
            with patch('random.random', side_effect=[0.0, 1.0]):
                item = LootGenerator.generate_loot("test_sword", self.world, level=1)
        
        self.assertIsNotNone(item)
        if item:
            self.assertEqual(item.name, "Sharp Sword")
            self.assertEqual(item.get_property("damage"), 12)
            self.assertEqual(item.value, 120)

    def test_suffix_stat_merging(self):
        """Verify 'of the Bear' adds stats via equip_effect."""
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [("of the Bear", SUFFIXES["of the Bear"])] 
            
            with patch('random.random', side_effect=[0.9, 0.0]):
                item = LootGenerator.generate_loot("test_armor", self.world, level=1)
                
        self.assertIsNotNone(item)
        if item:
            self.assertEqual(item.name, "Tunic of the Bear")
            
            effect = item.get_property("equip_effect")
            self.assertIsNotNone(effect)
            self.assertEqual(effect["modifiers"]["strength"], 2)
            self.assertEqual(effect["modifiers"]["constitution"], 2)
            
            self.player.inventory.add_item(item)
            self.player.equip_item(item)
            
            self.assertGreater(self.player.get_effective_stat("strength"), self.player.stats["strength"])

    def test_dual_affix_generation(self):
        """Verify item can have both prefix and suffix."""
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [
                ("Masterwork", PREFIXES["Masterwork"]), 
                ("of the Tiger", SUFFIXES["of the Tiger"])
            ]
            
            with patch('random.random', return_value=0.0):
                item = LootGenerator.generate_loot("test_sword", self.world, level=10)
                
        if item:
            self.assertEqual(item.name, "Masterwork Sword of the Tiger")
            self.assertEqual(item.get_property("damage"), 13)
            
            effect = item.get_property("equip_effect")
            self.assertEqual(effect["modifiers"]["strength"], 3)
            self.assertEqual(effect["modifiers"]["agility"], 3)
            self.assertEqual(item.value, 300)

    def test_vampirism_effect(self):
        """Verify Vampirism suffix applies the named buff."""
        with patch.object(LootGenerator, '_pick_affix') as mock_pick:
            mock_pick.side_effect = [("of Vampirism", SUFFIXES["of Vampirism"])]
            
            with patch('random.random', side_effect=[0.9, 0.0]):
                item = LootGenerator.generate_loot("test_sword", self.world, level=10)
                
        if item:
            effect = item.get_property("equip_effect")
            self.assertEqual(effect["name"], "Vampirism")
            
            self.player.inventory.add_item(item)
            self.player.equip_item(item)
            
            target = self.world.get_npc("dummy")
            if not target:
                from engine.npcs.npc_factory import NPCFactory
                target = NPCFactory.create_npc_from_template("goblin", self.world)
            
            if target:
                target.health = 100
                self.player.health = 10
                self.player.max_health = 100
                
                with patch('random.random', return_value=0.0):
                    self.player.attack(target, self.world)
                
                self.assertGreater(self.player.health, 10)

    def test_dungeon_chest_loot(self):
        """Verify we can populate a container with procedural loot."""
        self.world.item_templates["chest"] = {"type": "Container", "name": "Chest", "properties": {"is_open": True}}
        chest = ItemFactory.create_item_from_template("chest", self.world)
        
        loot = LootGenerator.generate_loot("test_sword", self.world, level=5)
        
        # Check types for Pylance safety before adding
        if isinstance(chest, Container) and loot:
            chest.add_item(loot)
            
            if self.player.current_region_id and self.player.current_room_id:
                self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, chest)
            
                desc = self.game.process_command("look in chest")
                # Ensure result is not None before asserting
                if desc:
                    self.assertIn("Sword", desc)
            else:
                self.fail("Player location invalid")
        else:
            self.fail("Chest creation failed or loot generation failed")