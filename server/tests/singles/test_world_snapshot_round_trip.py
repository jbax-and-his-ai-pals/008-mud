# tests/singles/test_world_snapshot_round_trip.py
"""The persistence contract: a world that was played comes back exactly.

For every shipped content set: boot a server, play it (walk, pick things up, let the
world tick), change the world in the ways content can (a lever's exit, a lifted
requirement, a timed effect, a killed and a moved NPC, a latch, a respawn), take a
snapshot, push it through JSON, boot a *second* server from the same content, restore
the snapshot into it, and require the two worlds to be identical. This is the test a
new kind of world state has to be added to when it is added to the game.
"""

import json
import random
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from engine.utils.utils import _serialize_item_reference
from engine.world import world_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage", "zelda_slice", "ff4_slice")


def _boot(set_id):
    return HeadlessServer(
        db_path=":memory:",
        content_set_path=str(REPO_ROOT / "content_sets" / set_id),
        deterministic_test_mode=True,
        default_presentation_mode="player",
    )


def _pristine(set_id):
    server = _boot(set_id)
    _PRISTINE_SERVERS.append(server)
    return server


_PRISTINE_SERVERS = []


def _json(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def dump_world(server):
    """Everything about the world a snapshot is meant to carry, in a comparable shape."""
    world = server.world
    now = world.clock.now()
    static_regions, rooms, dynamic = {}, {}, {}
    for region_id, region in world.regions.items():
        if str(region_id).startswith(("dynamic_", "instance_")):
            dynamic[region_id] = _json(region.to_dict())
            continue
        static_regions[region_id] = _json(region.properties)
        for room_id, room in region.rooms.items():
            rooms["%s:%s" % (region_id, room_id)] = {
                "exits": _json(room.exits),
                "properties": _json(room.properties),
                "env_properties": _json(room.env_properties),
                "time_descriptions": _json(room.time_descriptions),
                "visited": room.visited,
                "active_env_effects": _json(room.active_env_effects),
                "items": sorted(
                    json.dumps(_serialize_item_reference(i, 1, world), sort_keys=True, default=str) for i in room.items
                ),
            }
    npcs = {}
    for instance_id, npc in world.npcs.items():
        if npc.properties.get("is_summoned"):
            continue
        npcs[instance_id] = {
            "template": npc.template_id, "region": npc.current_region_id, "room": npc.current_room_id,
            "home": [npc.home_region_id, npc.home_room_id], "health": npc.health, "max_health": npc.max_health,
            "mana": npc.mana, "alive": npc.is_alive, "faction": npc.faction, "behavior": npc.behavior_type,
            "level": npc.level, "properties": _json(npc.properties), "stats": _json(npc.stats),
            "ai_state": _json(npc.ai_state),
            "cooldowns": {k: round(max(0.0, float(v) - now), 4) for k, v in npc.spell_cooldowns.items()},  # expired is expired
            "inventory": _json(npc.inventory.to_dict(world)),
        }
    queue = []
    for entry in world.respawn_manager.respawn_queue:
        item = dict(entry)
        if "respawn_time" in item:
            item["respawn_time"] = round(float(item["respawn_time"]) - now, 4)
        queue.append(_json(item))
    return {
        "regions": static_regions, "rooms": rooms, "dynamic": dynamic, "npcs": npcs, "respawn_queue": queue,
        "quest_board": _json(world.quest_board), "world_state": _json(getattr(world, "world_state", {})),
        "game_time": server.time_manager.game_time,
        "weather": [server.weather_manager.current_weather, server.weather_manager.current_intensity],
    }


def differences(a, b, path="", limit=12):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            if key not in a:
                out.append("%s/%s only in restored: %s" % (path, key, json.dumps(b[key])[:80]))
            elif key not in b:
                out.append("%s/%s only in original: %s" % (path, key, json.dumps(a[key])[:80]))
            else:
                out.extend(differences(a[key], b[key], "%s/%s" % (path, key), limit))
    elif a != b:
        out.append("%s: %s != %s" % (path, json.dumps(a)[:60], json.dumps(b)[:60]))
    return out[:limit]


def _play(server, session_id, rng):
    """Walk about, pick up what is lying there, and let the world tick."""
    player = server.get_player_for_session(session_id)
    for step in range(70):
        room = server.world.get_current_room(player)
        if room is None:
            break
        if room.items and step % 4 == 0:
            name = str(room.items[0].name).split(" ")[-1]
            server.execute_command(session_id, "get %s" % name)
        exits = sorted(room.exits)
        if exits:
            server.execute_command(session_id, "go %s" % rng.choice(exits))
        if step % 7 == 0:
            for _ in range(30):
                server.tick(session_id)
        if not player.is_alive:
            break


def _change_the_world(server, rng):
    """The changes content can make that a fresh build does not have."""
    world = server.world
    static = [(rid, r) for rid, r in sorted(world.regions.items()) if not str(rid).startswith(("dynamic_", "instance_")) and r.rooms]
    rooms = [(rid, room_id, room) for rid, region in static for room_id, room in sorted(region.rooms.items())]
    picks = rng.sample(rooms, min(4, len(rooms)))
    (_, _, opened), (_, _, lifted), (_, _, timed), (_, _, marked) = (picks * 4)[:4]
    target_region, target_room, _ = picks[-1]
    opened.exits["probe_door"] = "%s:%s" % (target_region, target_room)              # a lever's exit
    lifted.properties["exit_requirements"] = {"north": {"type": "locked", "key_id": None}}
    lifted.properties["exit_requirements"].pop("north")                              # a lifted requirement
    timed.active_env_effects = [{"action": "modify_exit_req", "direction": "north", "original_value": None, "time_remaining": 33.0}]
    marked.visited = True
    marked.properties["a_new_state"] = {"nested": [1, 2, 3]}
    world.world_state["latch:probe"] = True
    npcs = sorted(world.npcs)
    if npcs:
        world.npcs.pop(npcs[0])                                                      # a killed placed NPC
    if len(npcs) > 1:
        moved = world.npcs[npcs[1]]
        moved.current_region_id, moved.current_room_id = target_region, target_room  # one that walked off
        moved.spell_cooldowns = {"probe_spell": world.clock.now() + 12.5}
    world.respawn_manager.respawn_queue.append({
        "template_id": "probe", "instance_id": "probe_1", "name": "Probe",
        "home_region_id": target_region, "home_room_id": target_room, "respawn_time": world.clock.now() + 41.0,
    })


class TestWorldSnapshotRoundTrip(unittest.TestCase):
    def tearDown(self):
        while _PRISTINE_SERVERS:
            _PRISTINE_SERVERS.pop().shutdown()

    def test_a_played_world_comes_back_exactly_in_every_shipped_set(self):
        for set_id in SETS:
            with self.subTest(content_set=set_id):
                first = _boot(set_id)
                self.addCleanup(first.shutdown)
                session = first.create_session(player_id="rt").session_id
                first.execute_command(session, "char create Roundtrip")
                pristine = dump_world(_pristine(set_id))
                rng = random.Random(41)
                _play(first, session, rng)
                _change_the_world(first, rng)
                original = dump_world(first)
                self.assertNotEqual([], differences(pristine, original), "the play changed nothing, so this proves nothing")

                snapshot = _json(world_snapshot.capture(
                    first.world, time_manager=first.time_manager, weather_manager=first.weather_manager))

                second = _boot(set_id)
                self.addCleanup(second.shutdown)
                report = world_snapshot.restore(
                    second.world, snapshot, time_manager=second.time_manager, weather_manager=second.weather_manager)
                self.assertTrue(report.reverted_to_baseline)
                self.assertTrue(snapshot["rooms"], "the changes were captured as room changes")
                self.assertTrue(any("probe_door" in r.get("exits", {}).get("set", {}) for r in snapshot["rooms"].values()))
                restored = dump_world(second)

                self.assertEqual([], differences(original, restored), "restored world differs")
                self.assertEqual([], [r for r in report.skipped_npcs if not r.startswith("probe")],
                                 "npcs the snapshot could not rebuild")

    def test_a_snapshot_taken_before_any_play_changes_nothing_on_restore(self):
        for set_id in SETS:
            with self.subTest(content_set=set_id):
                server = _boot(set_id)
                self.addCleanup(server.shutdown)
                pristine = dump_world(server)
                snapshot = _json(world_snapshot.capture(server.world, time_manager=server.time_manager,
                                                        weather_manager=server.weather_manager))
                self.assertEqual({}, snapshot["rooms"], "a fresh world differs from content in no room")
                world_snapshot.restore(server.world, snapshot, time_manager=server.time_manager,
                                       weather_manager=server.weather_manager)
                self.assertEqual([], differences(pristine, dump_world(server)))

    def test_restoring_puts_back_a_room_the_snapshot_says_was_untouched(self):
        server = _boot("zelda_slice")
        self.addCleanup(server.shutdown)
        snapshot = _json(world_snapshot.capture(server.world))
        room = server.world.regions["mossroot"].get_room("root_hall")
        room.exits["down"] = "mossroot:secret_larder"       # opened after the snapshot was taken
        room.properties["hidden_exits"] = {}
        world_snapshot.restore(server.world, snapshot)
        self.assertNotIn("down", room.exits)
        self.assertEqual({"down": "mossroot:secret_larder"}, room.properties["hidden_exits"])
        self.assertIs(room.exits, room.properties["exits"], "the link between the two is kept")


if __name__ == "__main__":
    unittest.main()
