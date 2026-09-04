# tests/batch/test_batch_25.py
import os
import time
from tests.fixtures import GameTestBase
from engine.core.skill_system import MAX_SKILL_LEVEL, SkillSystem
from engine.items.item_factory import ItemFactory
from engine.world.room import Room

class TestBatch25(GameTestBase):
    """Focus: Player State, Persistence, and System Integrity."""

    def test_input_trimming(self):
        """Verify leading/trailing spaces are ignored."""
        res = self.game.process_command("   look   ")
        if res:
            # Should not be "unknown command"
            self.assertNotIn("Unknown command", res)
            # Should return room description
            self.assertIn("TOWN SQUARE", res)

    def test_case_insensitive_commands(self):
        """Verify LoOk works same as look."""
        res = self.game.process_command("LoOk")
        if res:
            self.assertIn("TOWN SQUARE", res)

    def test_alias_resolution(self):
        """Verify 'n' maps to 'north'."""
        # Setup room to north
        region = self.world.get_region("town")
        if region:
            # Fix: Instantiate Room directly to avoid type errors with Optional return from get_room
            region.add_room("north_room", Room("North", "x", {"south": "town_square"}, obj_id="north_room"))
            
            sq = region.get_room("town_square")
            if sq: sq.exits["north"] = "north_room"
            
            self.game.process_command("n")
            self.assertEqual(self.player.current_room_id, "north_room")

    def test_inventory_weight_recalc_on_drop(self):
        """Verify weight updates on drop."""
        # Item 10lbs
        self.world.item_templates["heavy"] = {"type": "Item", "name": "Heavy", "weight": 10.0}
        item = ItemFactory.create_item_from_template("heavy", self.world)
        if item:
            self.player.inventory.add_item(item)
            self.assertEqual(self.player.inventory.get_total_weight(), 10.0)
            
            self.game.process_command("drop Heavy")
            self.assertEqual(self.player.inventory.get_total_weight(), 0.0)

    def test_stat_modifiers_cleanup(self):
        """Verify expired buffs remove their modifiers from player stats."""
        base_str = self.player.stats["strength"]
        
        # Fix: Do NOT manually set modifiers, let apply_effect handle it to ensure baseline is clean
        
        # 1. Add effect properly
        eff = {"type": "stat_mod", "name": "Buff", "modifiers": {"strength": 5}, "base_duration": 1.0}
        self.player.apply_effect(eff, time.time())
        
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 5)
        
        # 2. Update time to expire
        self.player.update(time.time() + 2.0, 2.0)
        
        self.assertEqual(self.player.get_effective_stat("strength"), base_str)

    def test_save_load_position(self):
        """Verify player position is saved and loaded."""
        TEST_SAVE = "pos_save.json"
        
        # Fix: Ensure the room exists in the world, otherwise load logic resets to spawn
        region = self.world.get_region("town")
        if region:
            region.add_room("test_loc", Room("Test Loc", "x", obj_id="test_loc"))
        
        self.player.current_room_id = "test_loc"
        self.world.current_room_id = "test_loc" # Sync
        
        self.world.save_game(TEST_SAVE)
        self.world.load_save_game(TEST_SAVE)
        
        # Check self.world.player as self.player ref might be stale after load
        self.assertIsNotNone(self.world.player)
        if self.world.player:
             self.assertEqual(self.world.player.current_room_id, "test_loc")
        
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_player_level_cap(self):
        """Verify behavior at potential level boundaries (if any)."""
        # Current system doesn't have a hard level cap configured in config_player.
        # But let's verify leveling works at high levels.
        self.player.runtime_state.progression.level = 99
        self.player.runtime_state.progression.experience_to_level = 100
        self.player.gain_experience(100)
        self.assertEqual(self.player.runtime_state.progression.level, 100)

    def test_skill_xp_accumulation(self):
        """Verify partial XP is stored."""
        self.player.add_skill("mining", 1)
        SkillSystem.grant_xp(self.player, "mining", 50)
        
        self.assertEqual(self.player.runtime_state.progression.skills["mining"]["xp"], 50)
        # Should not level up yet (base 100)
        self.assertEqual(self.player.runtime_state.progression.skills["mining"]["level"], 1)

    def test_unknown_command_feedback(self):
        """Verify feedback for bad commands."""
        res = self.game.process_command("blargle")
        self.assertIsNotNone(res)
        if res:
             self.assertIn("Unknown command", res)

    def test_empty_command_feedback(self):
        """Verify empty input does nothing/doesn't crash."""
        res = self.game.process_command("")
        self.assertEqual(res, "")
