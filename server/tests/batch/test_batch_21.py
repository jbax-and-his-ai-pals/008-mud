# tests/batch/test_batch_21.py
import os
import time
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.inventory import InventorySlot

class TestBatch21(GameTestBase):
    """Focus: System Integrity, Persistence, and Limits."""

    def test_save_load_stress_many_items(self):
        """Verify saving a large inventory works."""
        TEST_SAVE = "stress_inv.json"
        
        self.player.inventory.max_slots = 100
        self.player.inventory.max_weight = 1000
        
        # Fix: Create unique slot objects, not references to the same one
        self.player.inventory.slots = [InventorySlot() for _ in range(100)]
        
        # Add 50 items
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if item:
             for i in range(50):
                 # Clone using factory
                 cloned = ItemFactory.create_item_from_template("item_iron_sword", self.world)
                 if cloned: self.player.inventory.add_item(cloned)
                 
        self.world.save_game(TEST_SAVE)
        self.world.load_save_game(TEST_SAVE)
        
        loaded = self.world.player
        if loaded:
             # Count items
             count = sum(1 for s in loaded.inventory.slots if s.item)
             self.assertEqual(count, 50)
             
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
             os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_load_missing_file_handled(self):
        """Verify loading a non-existent file returns appropriate failure/default."""
        success, _, _ = self.world.load_save_game("ghost_file.json")
        self.assertFalse(success)
        self.assertIsNotNone(self.world.player)
        if self.world.player:
            self.assertEqual(self.world.player.name, "Player")

    def test_quest_board_overflow_prevention(self):
        """Verify the board doesn't grow without bound across repeated fills.

        Content-authored board quests (commissions, bounties) are seeded
        before the capacity-gated procedural fill loop and are explicitly
        exempt from its cap (QuestManager._add_authored_board_quests), so
        the board's real size can legitimately exceed MAX_QUESTS_ON_BOARD
        once a content set authors more board templates than that -- the
        actual invariant worth protecting is idempotency: calling
        ensure_initial_quests again shouldn't keep piling on duplicates."""
        self.world.quest_board = []
        qm = self.world.quest_manager

        qm.ensure_initial_quests()
        first_fill_count = len(self.world.quest_board)
        self.assertGreater(first_fill_count, 0)

        # Calling again shouldn't add more -- authored templates already on
        # the board are skipped, and procedural fill only tops up any
        # remaining slots up to the cap (already exhausted or exceeded).
        qm.ensure_initial_quests()
        self.assertEqual(first_fill_count, len(self.world.quest_board))

    def test_item_factory_bad_id(self):
        """Verify factory returns None for bad IDs."""
        item = ItemFactory.create_item_from_template("bad_id_12345", self.world)
        self.assertIsNone(item)

    def test_time_leap_integrity(self):
        """Verify advancing time by huge amount handles date rollover."""
        tm = self.game.time_manager
        tm.initialize_time(0.0)
        
        # Advance 10 years (360 days/year)
        seconds = 10 * 360 * 86400
        
        # Fix: Only update game_time once
        tm.game_time += seconds
        tm._recalculate_date_from_game_time()
        
        # Year starts at 1, +10 years = 11
        self.assertEqual(tm.year, 11)

    def test_weather_update_consistency(self):
        """Verify weather intensity is valid string."""
        wm = self.game.weather_manager
        wm._update_weather("summer")
        self.assertIn(wm.current_intensity, ["mild", "moderate", "strong", "severe"])

    def test_inventory_split_invalid_qty(self):
        """Verify splitting negative/zero amount fails gracefully."""
        item = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        if item:
            self.player.inventory.add_item(item, 5)
            
            # Remove 0
            rem_item, count, _ = self.player.inventory.remove_item(item.obj_id, 0)
            self.assertIsNone(rem_item)
            self.assertEqual(count, 0)

    def test_equip_conflict_slot(self):
        """Verify equipping to a busy slot swaps items."""
        # Inject template to ensure test is robust
        self.world.item_templates["test_tunic"] = {
            "type": "Armor", "name": "Tunic", "properties": {"equip_slot": ["body"]}
        }

        # 1. Equip A
        itemA = ItemFactory.create_item_from_template("test_tunic", self.world)
        self.assertIsNotNone(itemA, "Failed to create itemA")
        if itemA: itemA.name = "A"
        
        itemB = ItemFactory.create_item_from_template("test_tunic", self.world)
        self.assertIsNotNone(itemB, "Failed to create itemB")
        if itemB: itemB.name = "B"
        
        if itemA and itemB:
            self.player.inventory.add_item(itemA)
            self.player.inventory.add_item(itemB)
            
            self.player.equip_item(itemA)
            self.assertEqual(self.player.equipment["body"], itemA)
            
            # 2. Equip B (Should Swap)
            self.player.equip_item(itemB)
            self.assertEqual(self.player.equipment["body"], itemB)
            self.assertIsNotNone(self.player.inventory.find_item_by_name("A"))

    def test_duplicate_item_ids_handled(self):
        """Verify items with same ID stack or exist separately based on stackable prop."""
        # Stackable
        i1 = ItemFactory.create_item_from_template("item_healing_potion_small", self.world) # Stackable
        # Non-stackable
        i2 = ItemFactory.create_item_from_template("item_iron_sword", self.world) # Not stackable
        
        if i1 and i2:
             self.player.inventory.add_item(i1)
             self.player.inventory.add_item(i1) # Add duplicate
             self.assertEqual(self.player.inventory.slots[0].quantity, 2)
             
             self.player.inventory.add_item(i2)
             self.player.inventory.add_item(i2) # Add duplicate
             # Should be in separate slots (or slot 1 and 2)
             slots_with_swords = [s for s in self.player.inventory.slots if s.item and s.item.obj_id == i2.obj_id]
             self.assertEqual(len(slots_with_swords), 2)

    def test_command_unknown(self):
        """Verify unknown commands return error message."""
        res = self.game.process_command("xyzzy")
        self.assertIsNotNone(res)
        if res:
            self.assertIn("Unknown command", res)
