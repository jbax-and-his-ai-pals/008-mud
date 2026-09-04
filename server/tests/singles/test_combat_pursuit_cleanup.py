# tests/singles/test_combat_pursuit_cleanup.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestCombatPursuitCleanup(GameTestBase):

    def test_target_leaves_room_ends_combat(self):
        """Verify combat ends/updates when a target moves to a different room."""
        # 1. Setup Enemy
        enemy = NPCFactory.create_npc_from_template("goblin", self.world)
        
        if enemy and self.player:
            rid, r_id = "town", "town_square"
            self.player.current_region_id, self.player.current_room_id = rid, r_id
            enemy.current_region_id, enemy.current_room_id = rid, r_id
            self.world.add_npc(enemy)
            
            # 2. Start Combat
            self.player.enter_combat(enemy)
            self.assertTrue(self.player.runtime_state.combat.in_combat)
            
            # 3. Move Enemy away (Teleport)
            enemy.current_room_id = "some_other_room"
            
            # 4. Act: Check combat status
            # With the updated player/display.py, this will no longer list the goblin.
            res = self.player.get_combat_status()
            
            # 5. Assertions
            self.assertIn("No current targets in sight", res)
            self.assertNotIn(enemy.name, res)
