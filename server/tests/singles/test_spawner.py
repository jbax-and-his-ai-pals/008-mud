# tests/singles/test_spawner.py
import time
from unittest.mock import patch, MagicMock
from tests.fixtures import GameTestBase
from engine.world.spawner import Spawner
from engine.world.region import Region
from engine.world.room import Room
from engine.npcs.npc_factory import NPCFactory

class TestSpawner(GameTestBase):
    
    def test_spawn_caps_and_cooldowns(self):
        """Verify spawner respects population limits and time intervals."""
        spawner = Spawner(self.world)
        
        # 1. Setup a region with aggressive spawning
        region = Region("Spawn Test Zone", "Testing", obj_id="test_zone")
        # Add a room
        room = Room("Spawn Room", "Empty", obj_id="spawn_room")
        region.add_room("spawn_room", room)
        
        region.spawner_config = {
            "monster_types": {"goblin": 1},
            "level_range": [1, 1]
        }
        # Ensure not safe
        region.properties["safe_zone"] = False 
        
        self.world.add_region("test_zone", region)
        self.world.current_region_id = "test_zone" # Player must be in region for spawner to activate
        self.world.current_room_id = "other_room" # Player shouldn't be in spawn room ideally, though config allows it usually
        
        # Add a secondary room for the player to be in so they don't block the spawn room logic
        player_room = Room("Player Room", "Safe", obj_id="player_room")
        region.add_room("player_room", player_room)
        self.player.current_region_id = "test_zone"
        self.player.current_room_id = "player_room"

        # 2. Mock NPCFactory to ensure it doesn't fail on "goblin" template
        # We'll rely on the actual factory if the template exists, otherwise mock
        if "goblin" not in self.world.npc_templates:
             self.world.npc_templates["goblin"] = {
                 "name": "Goblin", "description": "Ugly.", "faction": "hostile", "health": 10
             }

        # 3. First Spawn Tick
        # Force RNG to always spawn (random() returns 0.0)
        with patch('random.random', return_value=0.0): 
            spawner.update(time.time())
            
        # Count hostiles
        hostiles = [n for n in self.world.npcs.values() 
                    if n.faction == "hostile" and n.current_region_id == "test_zone"]
        initial_count = len(hostiles)
        self.assertGreater(initial_count, 0, "Spawner should have created a goblin.")
        
        # 4. Test Cooldown (Immediate Update)
        # 0.1s passed, cooldown is typically 5.0s
        spawner.update(time.time() + 0.1) 
        hostiles_after_fast = [n for n in self.world.npcs.values() 
                               if n.faction == "hostile" and n.current_region_id == "test_zone"]
        self.assertEqual(len(hostiles_after_fast), initial_count, "Should not spawn during cooldown.")
        
        # 5. Test Cap
        # Manually fill the region with Goblins to exceed typical cap (3-5)
        for i in range(10):
            g = NPCFactory.create_npc_from_template("goblin", self.world, instance_id=f"extra_goblin_{i}")
            if g:
                g.current_region_id = "test_zone"
                g.current_room_id = "spawn_room"
                self.world.add_npc(g)
            
        # Try to spawn again after significant time
        with patch('random.random', return_value=0.0):
            spawner.update(time.time() + 100.0)
            
        # Ensure we didn't exceed logic (count should stay same, no new ones)
        final_count = len([n for n in self.world.npcs.values() 
                           if n.faction == "hostile" and n.current_region_id == "test_zone"])
        
        # We added 10 manually + 1 initial = 11. Spawner shouldn't add more.
        self.assertEqual(final_count, 10 + initial_count)

    def test_spawner_considers_all_active_player_regions(self):
        """Verify spawning can occur in a non-legacy active player region."""
        spawner = Spawner(self.world)

        primary_region = Region("Primary Region", "Legacy player region.", obj_id="primary_region")
        primary_player_room = Room("Primary Player Room", "Occupied.", obj_id="primary_player_room")
        primary_spawn_room = Room("Primary Spawn Room", "Spawn room.", obj_id="primary_spawn_room")
        primary_region.add_room("primary_player_room", primary_player_room)
        primary_region.add_room("primary_spawn_room", primary_spawn_room)
        primary_region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        primary_region.properties["safe_zone"] = False
        self.world.add_region("primary_region", primary_region)

        secondary_region = Region("Secondary Region", "Active multiplayer region.", obj_id="secondary_region")
        secondary_player_room = Room("Secondary Player Room", "Occupied.", obj_id="secondary_player_room")
        secondary_spawn_room = Room("Secondary Spawn Room", "Spawn room.", obj_id="secondary_spawn_room")
        secondary_region.add_room("secondary_player_room", secondary_player_room)
        secondary_region.add_room("secondary_spawn_room", secondary_spawn_room)
        secondary_region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        secondary_region.properties["safe_zone"] = False
        self.world.add_region("secondary_region", secondary_region)

        self.player.current_region_id = "primary_region"
        self.player.current_room_id = "primary_player_room"
        self.world.current_region_id = "primary_region"
        self.world.current_room_id = "primary_player_room"

        from engine.player.core import Player
        other_player = Player("Secondary Hero", obj_id="secondary_hero", data_root=self.world.data_root)
        other_player.world = self.world
        other_player.current_region_id = "secondary_region"
        other_player.current_room_id = "secondary_player_room"
        self.world.players[other_player.obj_id] = other_player

        if "goblin" not in self.world.npc_templates:
            self.world.npc_templates["goblin"] = {
                "name": "Goblin", "description": "Ugly.", "faction": "hostile", "health": 10
            }

        with patch("random.random", return_value=0.0), patch("random.choice", return_value="secondary_spawn_room"):
            spawner.update(time.time())

        spawned_in_secondary = [
            npc for npc in self.world.npcs.values()
            if npc.faction == "hostile" and npc.current_region_id == "secondary_region"
        ]
        self.assertGreater(len(spawned_in_secondary), 0, "Spawner should consider the non-legacy active player region.")

    def test_spawner_uses_resolved_player_when_legacy_binding_missing(self):
        """Verify spawn activation still works when only loaded players remain."""
        spawner = Spawner(self.world)

        region = Region("Resolved Region", "Player-backed region.", obj_id="resolved_region")
        player_room = Room("Player Room", "Occupied.", obj_id="player_room")
        spawn_room = Room("Spawn Room", "Spawn room.", obj_id="spawn_room")
        region.add_room("player_room", player_room)
        region.add_room("spawn_room", spawn_room)
        region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        region.properties["safe_zone"] = False
        self.world.add_region("resolved_region", region)

        self.player.current_region_id = "resolved_region"
        self.player.current_room_id = "player_room"
        self.world._legacy_player_id = None

        if "goblin" not in self.world.npc_templates:
            self.world.npc_templates["goblin"] = {
                "name": "Goblin", "description": "Ugly.", "faction": "hostile", "health": 10
            }

        with patch("random.random", return_value=0.0), patch("random.choice", return_value="spawn_room"):
            spawner.update(time.time())

        spawned = [
            npc for npc in self.world.npcs.values()
            if npc.faction == "hostile" and npc.current_region_id == "resolved_region"
        ]
        self.assertGreater(len(spawned), 0, "Spawner should still work from resolved player context.")
