# tests/singles/test_lockpick_rng.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.lockpick import Lockpick
from engine.items.container import Container

class TestLockpickRNG(GameTestBase):

    def test_pick_breakage(self):
        """Verify lockpick is consumed when breakage RNG hits."""
        # 1. Setup
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", 
            "properties": {"locked": True, "lock_difficulty": 50}
        }
        box = ItemFactory.create_item_from_template("box", self.world)
        
        pick = Lockpick("pick", "Pick", break_chance=1.0) # 100% break chance
        self.player.inventory.add_item(pick)
        
        # 2. Force Skill Fail (so we don't unlock it, but trigger break logic)
        # Lockpick.use calls SkillSystem.attempt_check
        # Break logic happens regardless of success/fail based on RNG
        
        # Patch skill check to fail
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(False, "")):
            # Patch random.random to return 0.0 ( < 1.0 chance) -> Break
            with patch('random.random', return_value=0.0):
                msg = pick.use(self.player, box)
        
        # 3. Assert
        self.assertIn("snaps", msg)
        self.assertEqual(self.player.inventory.count_item("pick"), 0)

    def test_pick_survival(self):
        """Verify lockpick is kept when RNG rolls high."""
        self.world.item_templates["box"] = {"type": "Container", "name": "Box", "properties": {"locked": True}}
        box = ItemFactory.create_item_from_template("box", self.world)
        
        pick = Lockpick("pick", "Pick", break_chance=0.5)
        self.player.inventory.add_item(pick)
        
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(False, "")):
            # Patch random to 0.9 ( > 0.5 ) -> No break
            with patch('random.random', return_value=0.9):
                msg = pick.use(self.player, box)
        
        self.assertNotIn("snaps", msg)
        self.assertEqual(self.player.inventory.count_item("pick"), 1)