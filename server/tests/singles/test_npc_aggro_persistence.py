# tests/singles/test_npc_aggro_persistence.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room

class TestNPCAggroPersistence(GameTestBase):

    def test_aggro_remains_on_return(self):
        """Verify NPC stays angry if player leaves room and comes back."""
        # 1. Setup Rooms (Square <-> Lane)
        region = self.world.get_region("town")
        if not region: return
        
        room_a = Room("Square", "A", {"east": "Lane"}, obj_id="Square")
        room_b = Room("Lane", "B", {"west": "Square"}, obj_id="Lane")
        region.add_room("Square", room_a)
        region.add_room("Lane", room_b)
        
        # 2. Setup Hostile
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if not goblin: return
        
        self.world.add_npc(goblin)
        
        # Sync BOTH Player and World
        self.player.current_region_id = "town"
        self.player.current_room_id = "Square"
        self.world.current_region_id = "town"
        self.world.current_room_id = "Square"
        
        goblin.current_region_id = "town"
        goblin.current_room_id = "Square"
        
        # 3. Start Combat
        goblin.enter_combat(self.player)
        self.assertTrue(goblin.in_combat)
        
        # 4. Player Leaves
        self.world.change_room("east")
        self.assertEqual(self.player.current_room_id, "Lane")
        
        # 5. Player Returns
        self.world.change_room("west")
        self.assertEqual(self.player.current_room_id, "Square")
        
        # 6. Assert Goblin still angry
        self.assertTrue(goblin.in_combat, "Goblin should remember the fight.")
        self.assertIn(self.player, goblin.combat_targets)