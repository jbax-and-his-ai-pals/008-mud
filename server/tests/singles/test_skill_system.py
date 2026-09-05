# tests/singles/test_skill_system.py
import unittest
from unittest.mock import patch, MagicMock
from tests.fixtures import GameTestBase
from engine.core.skill_system import SkillSystem, MAX_SKILL_LEVEL
from engine.items.item_factory import ItemFactory
from engine.items.container import Container
from engine.items.lockpick import Lockpick
from engine.crafting.recipe import Recipe

class TestSkillSystem(GameTestBase):

    def test_xp_curve(self):
        """Verify XP requirements scale correctly."""
        # Level 1 -> 2 needs 100 XP (Base)
        req_lvl_1 = SkillSystem.get_xp_for_next_level(1)
        self.assertEqual(req_lvl_1, 100)

        # Level 2 -> 3 needs 150 XP (100 * 1.5)
        req_lvl_2 = SkillSystem.get_xp_for_next_level(2)
        self.assertEqual(req_lvl_2, 150)

    def test_player_skill_progression(self):
        """Verify player gains levels when acquiring enough XP."""
        skill = "lockpicking"
        self.player.add_skill(skill, 1)
        
        # 1. Gain partial XP
        msg = SkillSystem.grant_xp(self.player, skill, 50)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["level"], 1)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["xp"], 50)
        self.assertEqual(msg, "") # No level up message

        # 2. Gain enough to level up (50 + 50 = 100)
        msg = SkillSystem.grant_xp(self.player, skill, 50)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["level"], 2)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["xp"], 0) # Exact amount used
        self.assertIn("increased to 2", msg)

        # 3. Gain massive XP (Multi-level jump)
        # Level 2->3 needs 150. Level 3->4 needs 225. Total 375.
        SkillSystem.grant_xp(self.player, skill, 375)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["level"], 4)

    @patch('random.randint')
    def test_skill_check_math(self, mock_randint):
        """Verify skill check formula: Roll + Skill + Stat vs Difficulty."""
        skill = "crafting"
        # Setup: Level 5 Skill, 12 Int (+4 bonus: (12-10)*2)
        self.player.add_skill(skill, 5)
        self.player.stats["intelligence"] = 12
        
        # Scenario: Roll 50. Total = 50 + 5 + 4 = 59.
        mock_randint.return_value = 50
        
        # 1. Easy Check (DC 40) -> Pass
        success, _ = SkillSystem.attempt_check(self.player, skill, 40)
        self.assertTrue(success)
        
        # 2. Hard Check (DC 60) -> Fail
        success, _ = SkillSystem.attempt_check(self.player, skill, 60)
        self.assertFalse(success)

    @patch('random.randint')
    def test_mercantile_skill_check_uses_wisdom_bonus(self, mock_randint):
        """Verify the mercantile stat-bonus branch uses wisdom."""
        self.player.stats["wisdom"] = 14  # +8 bonus: (14-10)*2
        mock_randint.return_value = 50
        success, _ = SkillSystem.attempt_check(self.player, "mercantile", 57)
        self.assertTrue(success)  # 50 + 0 skill + 8 = 58 >= 57
        success, _ = SkillSystem.attempt_check(self.player, "mercantile", 59)
        self.assertFalse(success)

    @patch('random.randint')
    def test_lockpicking_mechanics(self, mock_randint):
        """Verify lockpicks use the skill system."""
        # Inject a guaranteed Container template into the world for this test
        self.world.item_templates["test_strongbox"] = {
            "type": "Container",
            "name": "Test Strongbox",
            "description": "A locked box.",
            "weight": 10.0,
            "value": 50,
            "properties": {
                "locked": True,
                "lock_difficulty": 50,
                "is_open": False,
                "capacity": 100
            }
        }

        # Setup
        chest = ItemFactory.create_item_from_template("test_strongbox", self.world)
        self.assertIsNotNone(chest, "Failed to create test container")
        
        # Guard clause for strict typing
        if not isinstance(chest, Container):
            self.fail(f"Created item is {type(chest)}, expected Container")
            return

        pick = Lockpick("test_pick", "Test Pick")
        self.player.inventory.add_item(pick)
        
        # Zero stats/skills for predictable math
        self.player.stats["dexterity"] = 10 # +0 bonus
        self.player.runtime_state.progression.skills["lockpicking"] = {"level": 0, "xp": 0}
        
        # 1. Fail (Roll 10 + 0 + 0 < 50)
        mock_randint.return_value = 10
        # Mock random.random for break chance (return 1.0 to ensure NO break)
        with patch('random.random', return_value=1.0):
            msg = pick.use(self.player, chest)
            self.assertIn("fail", msg)
            self.assertTrue(chest.properties["locked"])
            # Should gain "fail XP" (2)
            self.assertEqual(self.player.runtime_state.progression.skills["lockpicking"]["xp"], 2)

        # 2. Success (Roll 60 + 0 + 0 > 50)
        mock_randint.return_value = 60
        with patch('random.random', return_value=1.0):
            msg = pick.use(self.player, chest)
            self.assertIn("skillfully pick", msg)
            self.assertFalse(chest.properties["locked"])
            # Should gain "success XP" (DC/2 = 25) + previous 2 = 27
            self.assertEqual(self.player.runtime_state.progression.skills["lockpicking"]["xp"], 27)

    @patch('random.randint')
    def test_crafting_skill_check(self, mock_randint):
        """Verify crafting recipes check skills."""
        manager = self.game.crafting_manager
        
        # Setup Recipe (Result value 50 -> Difficulty 10 + (50/5) = 20)
        # We need a template with value
        self.world.item_templates["test_result"] = {"type": "Item", "name": "Result", "value": 50}
        
        recipe = Recipe("test_r", {
            "result_item_id": "test_result",
            "ingredients": [] # Free crafting
        })
        manager.recipes["test_r"] = recipe
        
        # 1. Fail (Roll 5 + 0 < 20)
        mock_randint.return_value = 5
        result = manager.craft(self.player, "test_r")
        self.assertIn("failed", result)
        
        # 2. Success (Roll 25 + 0 > 20)
        mock_randint.return_value = 25
        result = manager.craft(self.player, "test_r")
        self.assertIn("Successfully", result)
        # Check XP Gain (Max(10, 50/2) = 25) + previous fail xp(2) = 27
        self.assertEqual(self.player.runtime_state.progression.skills["crafting"]["xp"], 27)
