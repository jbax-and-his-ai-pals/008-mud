# tests/singles/test_spawner_limits.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.world.region import Region
from engine.world.room import Room
from engine.npcs.npc_factory import NPCFactory

class TestSpawnerLimits(GameTestBase):

    def test_spawn_cap_enforcement(self):
        """Verify spawner stops creating NPCs when region limit is reached."""
        # 1. Setup Small Region
        region = Region("Cap Test", "Testing", obj_id="cap_test")
        region.add_room("room_1", Room("Room 1", "x", obj_id="room_1"))
        
        # Config: Max 2 monsters (based on room count ratio or hard caps)
        # SPAWN_MAX_MONSTERS_PER_REGION_CAP = 3 usually.
        # Let's override spawner logic variables via config if needed, 
        # or rely on `_count_monsters_in_region`.
        
        region.spawner_config = {
            "monster_types": {"goblin": 1},
            "level_range": [1, 1]
        }
        self.world.add_region("cap_test", region)
        self.world.current_region_id = "cap_test"

        # 2. Manually Fill Region
        for _ in range(5): # Exceed default cap of 3
            npc = NPCFactory.create_npc_from_template("goblin", self.world)
            if npc:
                npc.current_region_id = "cap_test"
                npc.current_room_id = "room_1"
                self.world.add_npc(npc)

        initial_count = len([n for n in self.world.npcs.values() 
                             if n.current_region_id == "cap_test" and n.faction == "hostile"])
        self.assertGreaterEqual(initial_count, 5)

        # 3. Run Spawner
        # Force RNG to try spawning
        with patch('random.random', return_value=0.0):
            # Bypass timer check
            self.world.spawner.last_spawn_time = 0
            self.world.spawner.update(1000.0)

        # 4. Assert Count Unchanged
        final_count = len([n for n in self.world.npcs.values() 
                           if n.current_region_id == "cap_test" and n.faction == "hostile"])
        
        self.assertEqual(final_count, initial_count, "Spawner should not add mobs above cap.")