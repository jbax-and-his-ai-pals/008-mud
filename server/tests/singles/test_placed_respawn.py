# tests/singles/test_placed_respawn.py
"""A monster a room placed comes back when its author says how long it stays dead.

`respawn_cooldown` was written on ten `fantasy_frontier` templates (and a few in every other
set) and read by nothing that mattered: only a *friendly* NPC was ever queued to return, on a
global constant, and a region's ambient spawner was the only thing that refilled a room. Now a
hostile listed in a room's `initial_npcs` returns after its authored cooldown, as the room
placed it (placement overrides and all), and not in front of a player standing in the room.

* `-1` means never (a boss). No cooldown means never (a set that did not ask gets nothing).
* A hostile the ambient spawner made is not placed and is not brought back by this.
* The wait survives a restart: the queue entry is in the world snapshot.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
BAT = "bat_root_hall"          # a cave bat placed in mossroot's root hall, cooldown 180
WYRM = "horned_wyrm_at_boss_hall"           # a boss, cooldown -1
HOME = ("mossroot", "root_hall")


def _boot(db=":memory:"):
    return HeadlessServer(
        db_path=db, content_set_path=str(REPO_ROOT / "content_sets" / "zelda_slice"),
        deterministic_test_mode=True, default_presentation_mode="player",
    )


class _Zelda(unittest.TestCase):
    def setUp(self):
        self.server = _boot()
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="respawn").session_id
        self.server.execute_command(self.sid, "char create Tester")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.away()

    def away(self):
        self.player.current_region_id, self.player.current_room_id = "aldermark", "village_green"

    def go_home(self):
        self.player.current_region_id, self.player.current_room_id = HOME

    def slay(self, instance_id):
        npc = self.world.npcs[instance_id]
        npc.take_damage(10 ** 6, "physical")
        npc.die(self.world)
        return npc

    def queued(self, instance_id):
        return [e for e in self.world.respawn_manager.respawn_queue if e["instance_id"] == instance_id]

    def wait(self, seconds):
        self.world.clock.advance(seconds)
        return self.world.respawn_manager.update(self.world.clock.now())

    def alive(self, instance_id):
        npc = self.world.npcs.get(instance_id)
        return npc is not None and npc.is_alive


class TestPlacedHostiles(_Zelda):
    def test_a_placed_monster_returns_after_its_cooldown(self):
        self.slay(BAT)
        self.assertTrue(self.queued(BAT), "its death queues a return")
        self.wait(170)
        self.assertFalse(self.alive(BAT), "not before the author's 180 seconds")
        self.wait(20)
        self.assertTrue(self.alive(BAT))
        again = self.world.npcs[BAT]
        self.assertEqual(HOME, (again.current_region_id, again.current_room_id))
        self.assertEqual(again.max_health, again.health, "and at full health")
        self.assertEqual([], self.queued(BAT))

    def test_it_waits_while_a_player_stands_in_the_room(self):
        self.slay(BAT)
        self.go_home()
        self.wait(500)
        self.assertFalse(self.alive(BAT), "no pop-in in front of the player")
        self.assertTrue(self.queued(BAT), "it is still waiting, not lost")
        self.away()
        self.wait(1)
        self.assertTrue(self.alive(BAT), "and comes back as soon as the room is empty")

    def test_a_boss_with_minus_one_never_returns(self):
        self.slay(WYRM)
        self.assertEqual([], self.queued(WYRM))
        self.wait(100000)
        self.assertFalse(self.alive(WYRM))

    def test_a_monster_with_no_authored_cooldown_never_returns(self):
        properties = self.world.npc_templates["cave_bat"]["properties"]
        saved = properties.pop("respawn_cooldown")
        self.addCleanup(properties.__setitem__, "respawn_cooldown", saved)
        self.slay(BAT)
        self.assertEqual([], self.queued(BAT), "a set that never asked for respawns gets none")

    def test_a_monster_the_spawner_made_is_not_placed(self):
        npc, status = self.world.spawn_npc("cave_bat", *HOME, None)
        self.assertEqual("spawned", status)
        npc.take_damage(10 ** 6, "physical")
        npc.die(self.world)
        self.assertEqual([], self.queued(npc.obj_id), "only a room's own placement is brought back by its cooldown")

    def test_it_returns_as_the_room_placed_it(self):
        region = self.world.get_region(HOME[0])
        ref = next(r for r in region.get_room(HOME[1]).initial_npc_refs if r.get("instance_id") == BAT)
        ref["overrides"] = {"max_health": 7}
        self.addCleanup(ref.pop, "overrides", None)
        self.slay(BAT)
        self.wait(200)
        self.assertEqual(7, self.world.npcs[BAT].max_health, "the weakened encounter comes back weakened")

    def test_a_friendly_is_unchanged(self):
        hermit = next(n for n in self.world.npcs.values() if n.template_id == "hermit")
        hermit.die(self.world)
        self.assertTrue(self.queued(hermit.obj_id), "friendlies still return on the global timer")


class TestSurvivesARestart(unittest.TestCase):
    def test_a_monster_waiting_to_return_still_returns_after_a_restart(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        db = str(Path(scratch) / "state.sqlite3")
        first = _boot(db)
        sid = first.create_session(player_id="transport-1").session_id
        first.execute_command(sid, "char create Restarter")
        first.get_player_for_session(sid).current_region_id = "aldermark"
        first.get_player_for_session(sid).current_room_id = "village_green"
        bat = first.world.npcs[BAT]
        bat.take_damage(10 ** 6, "physical")
        bat.die(first.world)
        first.shutdown()

        second = _boot(db)
        self.addCleanup(second.shutdown)
        second.create_session(player_id="another-id")
        world = second.world
        waiting = [e for e in world.respawn_manager.respawn_queue if e["instance_id"] == BAT]
        self.assertEqual(1, len(waiting), "the wait is in the snapshot")
        self.assertTrue(waiting[0].get("placed"))
        world.clock.advance(400)
        world.respawn_manager.update(world.clock.now())
        again = world.npcs.get(BAT)
        self.assertTrue(again is not None and again.is_alive, "and ends after the restart")


if __name__ == "__main__":
    unittest.main()
