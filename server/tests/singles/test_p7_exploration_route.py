"""P7 contract: an explorer can progress without combat or gathering."""

from pathlib import Path
import unittest

from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestP7ExplorationRoute(unittest.TestCase):
    def test_forty_new_rooms_pay_landmark_xp_without_other_activities(self) -> None:
        """Walking the authored town is a rewarded, once-only progression path
        -- scaled to the town's own level band (2026-09-24). Every room's first
        visit used to pay 25 XP wherever it was, so these forty town rooms paid
        1,000+ XP (level 5) in a level 1-3 region; rooms now pay by their
        region's danger, and the whole public walk still reaches level 15
        (the test below)."""
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="p7_explorer")
            server.execute_command(session.session_id, "char create Explorer")
            player = server.get_player_for_session(session.session_id)
            town = server.world.get_region("town")
            self.assertIsNotNone(town)
            assert town is not None

            start_room_id = player.current_room_id
            seeded_entries = set(player.advancement_entries)
            targets = [
                room_id
                for room_id in sorted(town.rooms)
                if room_id != start_room_id
                and server.world.find_path("town", start_room_id, "town", room_id) is not None
            ][:40]
            self.assertEqual(40, len(targets), "the public starter town must support the promised route")

            for room_id in targets:
                path = server.world.find_path(
                    player.current_region_id,
                    player.current_room_id,
                    "town",
                    room_id,
                )
                self.assertIsNotNone(path, f"no walking path to town:{room_id}")
                for direction in path or []:
                    server.world.change_room(direction, player)
                self.assertEqual(("town", room_id), (player.current_region_id, player.current_room_id))
                self.assertTrue(
                    server.advancement_manager.has_entry(player, f"landmark:town:{room_id}"),
                )

            earned = player.total_experience()
            self.assertGreaterEqual(earned, 100, "the town walk should still be worth a level")
            self.assertLess(earned, 381, "walking the town alone must not carry a character past its level 1-3 band")
            route_entries = player.advancement_entries - seeded_entries
            self.assertTrue(
                all(
                    entry.startswith("landmark:town:") for entry in route_entries
                ),
                "the route should earn only landmark entries: %s" % sorted(route_entries),
            )
        finally:
            server.shutdown()

    def test_complete_public_world_walk_reaches_level_fifteen_without_other_rewards(self) -> None:
        """P7's core promise is reachable through first-time exploration alone.

        This deliberately does not talk, fight, take loot, complete quests, or
        gather. It walks a continuous route through every public static room;
        the only entries it earns are landmark and region entries. Rooms marked
        ``entered_by_system`` (such as custody) are excluded because they are
        intentionally not part of a player-directed route.
        """
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="p7_full_explorer")
            server.execute_command(session.session_id, "char create Explorer")
            player = server.get_player_for_session(session.session_id)
            seeded_entries = set(player.advancement_entries)
            public_rooms = [
                (region_id, room_id)
                for region_id, region in sorted(server.world.regions.items())
                for room_id, room in sorted(region.rooms.items())
                if not room.get_property("entered_by_system", False)
            ]

            for region_id, room_id in public_rooms:
                if (player.current_region_id, player.current_room_id) == (region_id, room_id):
                    continue
                path = server.world.find_path(
                    player.current_region_id,
                    player.current_room_id,
                    region_id,
                    room_id,
                )
                if path is None and (region_id, room_id) == ("obsidian_trial", "inner_sanctum"):
                    # The Trial's final room is intentionally puzzle-gated,
                    # not unreachable: operate its authored lever and then
                    # continue the same walking route through the new exit.
                    lever_path = server.world.find_path(
                        player.current_region_id,
                        player.current_room_id,
                        "obsidian_trial",
                        "lever_room_west",
                    )
                    self.assertIsNotNone(lever_path, "cannot reach the Obsidian Trial lever")
                    for direction in lever_path or []:
                        server.world.change_room(direction, player)
                    activated = server.execute_command(session.session_id, "interact obsidian lever")
                    self.assertIn("grinding sound", "\n".join(str(event["payload"]) for event in activated))
                    path = server.world.find_path(
                        player.current_region_id,
                        player.current_room_id,
                        region_id,
                        room_id,
                    )
                self.assertIsNotNone(path, f"no walking path to {region_id}:{room_id}")
                for direction in path or []:
                    server.world.change_room(direction, player)
                self.assertEqual((region_id, room_id), (player.current_region_id, player.current_room_id))

            earned_entries = player.advancement_entries - seeded_entries
            self.assertTrue(
                all(entry.startswith(("landmark:", "region:")) for entry in earned_entries),
                "exploration-only route earned an unexpected entry: %s" % sorted(earned_entries),
            )
            self.assertGreaterEqual(player.runtime_state.progression.level, 15)
            self.assertGreaterEqual(player.total_experience(), 8_691)
        finally:
            server.shutdown()
