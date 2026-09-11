# tests/singles/test_guard_patrol_content.py
"""Content sanity checks for guard patrol routes, plus an integration
test that drives the real `perform_patrol` mechanic (already unit-tested
against synthetic rooms in test_npc_patrol.py) against an actual town
NPC and its authored route through the real room graph."""

from tests.fixtures import GameTestBase
from engine.npcs.ai.movement import perform_patrol


def _guards(world):
    return [npc for npc in world.npcs.values() if npc.template_id in ("town_guard", "guard_captain")]


class TestGuardPatrolContent(GameTestBase):
    def test_town_guards_patrol_and_captains_stay_put(self):
        guards = _guards(self.world)
        town_guards = [g for g in guards if g.template_id == "town_guard"]
        captains = [g for g in guards if g.template_id == "guard_captain"]

        self.assertEqual(4, len(town_guards))
        self.assertEqual(2, len(captains))
        for guard in town_guards:
            self.assertEqual("patrol", guard.behavior_type)
            self.assertTrue(guard.patrol_points)
        for captain in captains:
            self.assertEqual("stationary", captain.behavior_type)

    def test_every_patrol_point_resolves_to_a_real_room_in_town(self):
        region = self.world.get_region("town")
        self.assertIsNotNone(region)
        for guard in _guards(self.world):
            for room_id in guard.patrol_points:
                self.assertIsNotNone(
                    region.get_room(room_id),
                    f"{guard.obj_id}'s patrol point '{room_id}' is not a real room in town",
                )

    def test_patrol_routes_are_distinct_per_instance(self):
        town_guards = [g for g in _guards(self.world) if g.template_id == "town_guard"]
        routes = [tuple(g.patrol_points) for g in town_guards]
        self.assertEqual(len(routes), len(set(routes)), "each guard should have its own route")

    def test_guard_north_1_walks_its_real_authored_route(self):
        guard = next(g for g in self.world.npcs.values() if g.obj_id == "guard_north_1")
        self.assertEqual("north_gate", guard.current_room_id)
        self.assertEqual(["north_gate", "watchtower_base", "town_square"], guard.patrol_points)

        # Already "at" patrol_points[0] (its own spawn room) -- first call
        # just advances the index without moving.
        perform_patrol(guard, self.world, self.player)
        self.assertEqual(1, guard.patrol_index)
        self.assertEqual("north_gate", guard.current_room_id)

        # Now heads toward watchtower_base, one real room-graph step at a time.
        moved_toward_watchtower = False
        for _ in range(10):
            perform_patrol(guard, self.world, self.player)
            if guard.current_room_id == "watchtower_base":
                moved_toward_watchtower = True
                break
        self.assertTrue(moved_toward_watchtower, "guard never reached watchtower_base")
