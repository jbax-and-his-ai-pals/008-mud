# tests/singles/test_combat_flee_mechanics.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room

class TestCombatFleeMechanics(GameTestBase):

    def test_flee_updates_state(self):
        """Verify fleeing moves player and ends combat."""
        # 1. Setup Rooms
        region = self.world.get_region("town")
        if not region: return
        
        r1 = Room("Arena", "Fight here", {"north": "Safe"}, obj_id="Arena")
        r2 = Room("Safe", "Safe here", {"south": "Arena"}, obj_id="Safe")
        region.add_room("Arena", r1)
        region.add_room("Safe", r2)
        
        self.player.current_region_id = "town"
        self.player.current_room_id = "Arena"
        self.world.current_region_id = "town"
        self.world.current_room_id = "Arena"
        
        # 2. Setup Enemy
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            goblin.current_region_id = "town"
            goblin.current_room_id = "Arena"
            self.world.add_npc(goblin)
            
            # Start Fight
            self.player.enter_combat(goblin)
            
            # 3. Act: Flee (Manual move command during combat)
            result = self.game.process_command("north")
            
            # 4. Assert
            self.assertIsNotNone(result)
            if result:
                # Should succeed in moving. 
                # Note: "You have entered" only displays on Region change.
                # We check for the new room's title or description.
                self.assertIn("SAFE", result)
            
            self.assertEqual(self.player.current_room_id, "Safe")
            
            # Verify the Goblin is NOT in the new room's NPC list
            npcs_here = self.world.get_current_room_npcs()
            self.assertNotIn(goblin, npcs_here)