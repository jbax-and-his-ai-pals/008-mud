# tests/singles/test_npc_infighting.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import scan_for_targets

class TestNPCInfighting(GameTestBase):

    def test_guard_attacks_hostile(self):
        """Verify friendly NPCs (Guards) attack Hostile NPCs (Goblins)."""
        guard = NPCFactory.create_npc_from_template("town_guard", self.world)
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        
        self.assertIsNotNone(guard, "Failed to create Guard.")
        self.assertIsNotNone(goblin, "Failed to create Goblin.")
        
        if guard and goblin:
            # Setup Arena
            guard.current_region_id = "town"; guard.current_room_id = "arena"
            goblin.current_region_id = "town"; goblin.current_room_id = "arena"
            
            # FIX: Guards need aggression to attack on sight
            guard.aggression = 1.0
            
            self.world.add_npc(guard)
            self.world.add_npc(goblin)
            
            # Guard AI Tick (Friendly defending against hostile)
            # scan_for_targets checks for hostiles in room
            scan_for_targets(guard, self.world, self.player)
            
            # Assert Guard is fighting Goblin
            self.assertTrue(guard.in_combat)
            self.assertIn(goblin, guard.combat_targets)
            
            # Assert Goblin is fighting Guard (reciprocal aggro)
            self.assertTrue(goblin.in_combat)
            self.assertIn(guard, goblin.combat_targets)