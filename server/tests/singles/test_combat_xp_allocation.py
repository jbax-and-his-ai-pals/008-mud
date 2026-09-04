# tests/singles/test_combat_xp_allocation.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.utils.utils import calculate_xp_gain

class TestCombatXPAllocation(GameTestBase):

    def test_xp_on_kill(self):
        """Verify XP is awarded when an enemy dies in combat."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if not target: return
        self.world.add_npc(target)
        
        # Sync location
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        
        start_xp = self.player.runtime_state.progression.experience
        
        # Calculate expected XP
        expected_gain = calculate_xp_gain(
            self.player.runtime_state.progression.level, target.level, target.max_health
        )
        
        # Weak Target
        target.health = 1
        
        # Kill
        with patch('random.random', return_value=0.0): # Hit
            self.player.attack(target, self.world)
            
        self.assertFalse(target.is_alive)
        self.assertEqual(self.player.runtime_state.progression.experience, start_xp + expected_gain)
