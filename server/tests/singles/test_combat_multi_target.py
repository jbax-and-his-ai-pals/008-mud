# tests/singles/test_combat_multi_target.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestCombatMultiTarget(GameTestBase):

    def test_combat_state_with_multiple_enemies(self):
        """Verify player stays in combat if one of two enemies dies."""
        # 1. Create two goblins
        g1 = NPCFactory.create_npc_from_template("goblin", self.world)
        g2 = NPCFactory.create_npc_from_template("goblin", self.world)
        
        self.assertIsNotNone(g1)
        self.assertIsNotNone(g2)
        
        if g1 and g2 and self.player:
            # Sync locations
            rid, room_id = self.player.current_region_id, self.player.current_room_id
            g1.current_region_id = g2.current_region_id = rid
            g1.current_room_id = g2.current_room_id = room_id
            
            self.world.add_npc(g1)
            self.world.add_npc(g2)
            
            # 2. Engage both
            self.player.enter_combat(g1)
            self.player.enter_combat(g2)
            self.assertTrue(self.player.runtime_state.combat.in_combat)
            self.assertEqual(len(self.player.runtime_state.combat.targets), 2)
            
            # 3. Kill first goblin (Deterministic)
            g1.health = 1
            self.player.stats["strength"] = 100 # Ensure one-shot
            
            with patch('random.random', return_value=0.0): # Force Hit
                self.player.attack(g1, self.world)
            
            # 4. Assertions
            self.assertFalse(g1.is_alive)
            self.assertTrue(g2.is_alive)
            
            # Player should still be in combat because g2 is active in the targets set
            self.assertTrue(self.player.runtime_state.combat.in_combat, "Player should remain in combat with remaining targets.")
            self.assertIn(g2, self.player.runtime_state.combat.targets)
            self.assertNotIn(g1, self.player.runtime_state.combat.targets)
