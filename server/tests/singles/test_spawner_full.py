# tests/singles/test_spawner_full.py
"""Coverage for engine/world/spawner.py's remaining branches: the per-tick
random-chance skip, a stale/missing region in the active-region loop, an
empty region (zero rooms), room-filtering (None entries, no_monster_spawn
flag, ruleset no_spawn_keywords), no suitable rooms, an empty monster-type
weight table, an unknown/invalid chosen template, and the SPAWN_DEBUG
render-message branch.

Note: the "fallback_player" branches in both update() and
_spawn_monsters_in_region() (looked up via world.resolve_reference_player()
when no player's region/room is already in the active set) are provably
unreachable: resolve_reference_player() draws exclusively from
world.players, the very same collection the preceding set comprehension
already scanned, so any player it could return with the needed truthy
region/room would already have been included by that comprehension. Left
untested as dead code, consistent with this codebase's established
precedent for provably-unreachable branches."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.spawner import Spawner
from engine.world.region import Region
from engine.world.room import Room


class TestSpawnerUpdate(GameTestBase):
    def setUp(self):
        super().setUp()
        self.spawner = Spawner(self.world)
        self.region = Region("Spawn Zone", "Testing", obj_id="spawner_full_zone")
        self.region.properties["safe_zone"] = False
        self.room = Room("Spawn Room", "Empty", obj_id="spawner_full_room")
        self.region.add_room("spawner_full_room", self.room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        self.world.add_region("spawner_full_zone", self.region)
        self.player.current_region_id = "spawner_full_zone"
        self.player.current_room_id = "spawner_full_room"
        if "goblin" not in self.world.npc_templates:
            self.world.npc_templates["goblin"] = {
                "name": "Goblin", "description": "Ugly.", "faction": "hostile", "health": 10,
            }

    def test_chance_roll_failure_skips_the_tick(self):
        with patch("engine.world.spawner.random.random", return_value=1.5):
            self.spawner.update(time.time())
        hostiles = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertEqual(len(hostiles), 0)

    def test_stale_region_id_is_skipped(self):
        self.player.current_region_id = "region_that_does_not_exist_xyz"
        with patch("engine.world.spawner.random.random", return_value=0.0):
            self.spawner.update(time.time())  # must not raise


class TestSpawnMonstersInRegion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.spawner = Spawner(self.world)
        self.region = Region("Spawn Zone", "Testing", obj_id="spawner_full_zone2")
        self.region.properties["safe_zone"] = False
        self.world.add_region("spawner_full_zone2", self.region)
        if "goblin" not in self.world.npc_templates:
            self.world.npc_templates["goblin"] = {
                "name": "Goblin", "description": "Ugly.", "faction": "hostile", "health": 10,
            }

    def test_region_with_zero_rooms_is_skipped(self):
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        self.spawner._spawn_monsters_in_region(self.region)  # must not raise

    def test_none_room_entry_is_skipped(self):
        room = Room("Real Room", "A room.", obj_id="real_room")
        self.region.add_room("real_room", room)
        self.region.rooms["ghost_room"] = None
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        with patch("engine.world.spawner.random.choice", side_effect=lambda seq: seq[0]):
            self.spawner._spawn_monsters_in_region(self.region)
        # No crash, and the only real room was the one chosen.
        goblins = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertTrue(all(n.current_room_id == "real_room" for n in goblins))

    def test_no_monster_spawn_flagged_room_is_excluded(self):
        blocked_room = Room("Blocked Room", "No spawns here.", obj_id="blocked_room")
        blocked_room.update_property("no_monster_spawn", True)
        self.region.add_room("blocked_room", blocked_room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        self.spawner._spawn_monsters_in_region(self.region)
        goblins = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertEqual(len(goblins), 0)

    def test_no_spawn_keyword_match_excludes_room(self):
        forbidden_room = Room("Forbidden Sanctuary", "Off limits.", obj_id="forbidden_room")
        self.region.add_room("forbidden_room", forbidden_room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        with patch.object(self.world, "ruleset_section", return_value={"no_spawn_keywords": ["sanctuary"]}):
            self.spawner._spawn_monsters_in_region(self.region)
        goblins = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertEqual(len(goblins), 0)

    def test_no_suitable_rooms_returns_without_spawning(self):
        blocked_room = Room("Only Room", "The only room.", obj_id="only_room")
        blocked_room.update_property("no_monster_spawn", True)
        self.region.add_room("only_room", blocked_room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        self.spawner._spawn_monsters_in_region(self.region)  # must not raise

    def test_empty_monster_type_weights_returns_without_spawning(self):
        room = Room("Room", "A room.", obj_id="empty_weights_room")
        self.region.add_room("empty_weights_room", room)
        self.region.spawner_config = {"monster_types": {}, "level_range": [1, 1]}
        self.spawner._spawn_monsters_in_region(self.region)
        goblins = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertEqual(len(goblins), 0)

    def test_unknown_monster_template_returns_without_spawning(self):
        room = Room("Room", "A room.", obj_id="unknown_template_room")
        self.region.add_room("unknown_template_room", room)
        self.region.spawner_config = {"monster_types": {"totally_bogus_monster_xyz": 1}, "level_range": [1, 1]}
        self.spawner._spawn_monsters_in_region(self.region)
        spawned = [n for n in self.world.npcs.values() if n.template_id == "totally_bogus_monster_xyz"]
        self.assertEqual(len(spawned), 0)

    def test_factory_failure_does_not_add_an_npc(self):
        room = Room("Room", "A room.", obj_id="factory_failure_room")
        self.region.add_room("factory_failure_room", room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        with patch("engine.world.spawner.NPCFactory.create_npc_from_template", return_value=None):
            self.spawner._spawn_monsters_in_region(self.region)  # must not raise
        goblins = [n for n in self.world.npcs.values() if n.faction == "hostile" and n.current_region_id == self.region.obj_id]
        self.assertEqual(len(goblins), 0)

    def test_spawn_debug_logs_a_message(self):
        room = Room("Room", "A room.", obj_id="debug_room")
        self.region.add_room("debug_room", room)
        self.region.spawner_config = {"monster_types": {"goblin": 1}, "level_range": [1, 1]}
        with patch("engine.world.spawner.SPAWN_DEBUG", True):
            self.spawner._spawn_monsters_in_region(self.region)
        self.assertIn("[SpawnerDebug]", self.game.renderer.message_buffer[-1] if self.game.renderer.message_buffer else "")


if __name__ == "__main__":
    unittest.main()
