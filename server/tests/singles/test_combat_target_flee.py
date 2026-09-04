# tests/singles/test_combat_target_flee.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai.combat_logic import try_flee

class TestCombatTargetFlee(GameTestBase):

    def test_combat_ends_if_target_flees(self):
        """Verify player exits combat if their target successfully flees the room."""
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if not goblin: return
        
        # Setup Room with exit
        from engine.world.room import Room
        region = self.world.get_region("town")
        if region:
            region.add_room("safe_zone", Room("Safe", "Safe", {"south": "town_square"}, obj_id="safe_zone"))
            
            # FIX: Safe access to room before accessing properties
            town_square = region.get_room("town_square")
            if town_square:
                town_square.exits["north"] = "safe_zone"
            else:
                self.fail("Town square not found in region.")
            
        self.world.add_npc(goblin)
        goblin.current_region_id = "town"
        goblin.current_room_id = "town_square"
        
        # Start Combat
        self.player.enter_combat(goblin)
        goblin.enter_combat(self.player)
        
        # Force Flee
        msg = try_flee(goblin, self.world, self.player)
        
        # Assertions
        self.assertIsNotNone(msg, "Flee should succeed given valid exits")
        self.assertNotEqual(goblin.current_room_id, "town_square")
        
        # Player should no longer target goblin
        self.assertFalse(self.player.runtime_state.combat.in_combat)
        self.assertNotIn(goblin, self.player.runtime_state.combat.targets)
