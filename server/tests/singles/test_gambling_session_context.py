import unittest
from unittest.mock import patch

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestGamblingSessionContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.leader = self.server.create_session(player_id="leader")
        self.member = self.server.create_session(player_id="member")
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.leader_player = self.server.get_player_for_session(self.leader.session_id)
        self.member_player = self.server.get_player_for_session(self.member.session_id)
        assert self.leader_player is not None
        assert self.member_player is not None

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    @patch("engine.commands.gambling.draw_card", return_value=("3", "H"))
    def test_blackjack_hit_uses_invoking_session_player(self, _mock_draw_card) -> None:
        self.server.world.player = self.member_player
        self.leader_player.active_minigame = {
            "type": "blackjack",
            "bet": 10,
            "hand": [("10", "H"), ("2", "D")],
            "dealer_hand": [("10", "S"), ("5", "C")],
            "region_id": "casino",
            "room_id": "card_room",
        }
        self.leader_player.current_region_id = "casino"
        self.leader_player.current_room_id = "card_room"

        events = self.server.execute_command(self.leader.session_id, "hit")
        payloads = self._text_payloads(events)

        self.assertTrue(any("You draw" in payload for payload in payloads))
        self.assertEqual(3, len(self.leader_player.active_minigame["hand"]))
        self.assertIsNone(self.member_player.active_minigame)

    def test_blackjack_stand_uses_invoking_session_player(self) -> None:
        self.server.world.player = self.member_player
        self.leader_player.runtime_state.gold = 50
        self.leader_player.active_minigame = {
            "type": "blackjack",
            "bet": 10,
            "hand": [("10", "H"), ("Q", "D")],
            "dealer_hand": [("10", "S"), ("7", "C")],
            "region_id": "casino",
            "room_id": "card_room",
        }
        self.leader_player.current_region_id = "casino"
        self.leader_player.current_room_id = "card_room"

        events = self.server.execute_command(self.leader.session_id, "stand")
        payloads = self._text_payloads(events)

        self.assertTrue(any("You win!" in payload for payload in payloads))
        self.assertIsNone(self.leader_player.active_minigame)
        self.assertEqual(70, self.leader_player.runtime_state.gold)
        self.assertIsNone(self.member_player.active_minigame)

    def test_runebreaker_guess_uses_invoking_session_player(self) -> None:
        self.server.world.player = self.member_player
        self.leader_player.active_minigame = {
            "type": "runebreaker",
            "bet": 10,
            "secret_code": ["fire", "water", "earth"],
            "attempts_left": 3,
            "region_id": "casino",
            "room_id": "arcane_vault",
        }
        self.leader_player.current_region_id = "casino"
        self.leader_player.current_room_id = "arcane_vault"

        events = self.server.execute_command(self.leader.session_id, "guess fire water earth")
        payloads = self._text_payloads(events)

        self.assertTrue(any("CODE BROKEN" in payload for payload in payloads))
        self.assertIsNone(self.leader_player.active_minigame)
        self.assertIsNone(self.member_player.active_minigame)
