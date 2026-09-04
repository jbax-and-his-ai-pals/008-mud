import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestNoCombatPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session = self.server.create_session()
        self.session_id = self.session.session_id
        self.server.execute_command(self.session_id, "char create TestPlayer")
        self.server.feature_profile.combat_mode = "disabled"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_combat_adjacent_messages_filtered(self) -> None:
        self.assertTrue(self.server._is_combat_adjacent_message("Goblin attacks you for 5 damage."))
        self.assertFalse(self.server._is_combat_adjacent_message("A cool breeze passes through the room."))

    def test_nearby_payload_marks_hostility_false_when_combat_disabled(self) -> None:
        # Seed a hostile faction onto an NPC already spawned in the player's room.
        # Use player.current_region_id / current_room_id directly — world.current_region_id
        # is a property backed by world.player (None in headless mode).
        player = self.server.get_player_for_session(self.session_id)
        self.assertIsNotNone(player, "Character creation should have placed a player.")
        region_id = player.current_region_id
        room_id = player.current_room_id

        seeded = False
        for npc in self.server.world.npcs.values():
            if (
                getattr(npc, "current_region_id", None) == region_id
                and getattr(npc, "current_room_id", None) == room_id
            ):
                npc.faction = "hostile"
                seeded = True
                break
        self.assertTrue(
            seeded,
            "Expected at least one NPC in the player's starting room for coverage. "
            "Check that the baseline world spawns NPCs at the starting location.",
        )

        payload = self.server._build_nearby_payload(self.session_id)
        hostiles = [npc for npc in payload.get("npcs", []) if npc.get("faction") == "hostile"]
        self.assertTrue(hostiles, "Expected nearby payload to include the seeded hostile NPC.")
        self.assertTrue(
            all(not bool(npc.get("hostile")) for npc in hostiles),
            "Expected hostile flag to be False when combat_mode is 'disabled'.",
        )

    def test_execute_command_blocks_combat_verb_when_disabled(self) -> None:
        events = self.server.execute_command(self.session_id, "attack goblin")
        payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("do not have permission" in payload.lower() for payload in payloads))


if __name__ == "__main__":
    unittest.main()
