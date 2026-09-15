"""P7 contract: an explorer can progress without combat or gathering."""

from pathlib import Path
import unittest

from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestP7ExplorationRoute(unittest.TestCase):
    def test_forty_new_rooms_pay_landmark_xp_without_other_activities(self) -> None:
        """Walking the authored town is a meaningful, once-only progression path."""
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

            self.assertGreaterEqual(player.total_experience(), 1_000)
            route_entries = player.advancement_entries - seeded_entries
            self.assertTrue(
                all(
                    entry.startswith("landmark:town:") for entry in route_entries
                ),
                "the route should earn only landmark entries: %s" % sorted(route_entries),
            )
        finally:
            server.shutdown()
