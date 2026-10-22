# tests/singles/test_health_hearts.py
"""`ruleset.world.health_per_heart`: health counted in hearts, with halves and quarters."""

import re
import unittest

from engine.server.headless_server import HeadlessServer
from engine.utils.health_display import format_health, health_per_heart, hearts

from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _game(case, unit):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    if unit:
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"health_per_heart": unit} if name == "world" else original(name)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    return server, sid, server.get_player_for_session(sid)


class TestHearts(unittest.TestCase):
    def test_half_and_quarter_hearts_are_shown_as_fractions(self):
        self.assertEqual("5½", hearts(11, 2))
        self.assertEqual("6", hearts(12, 2))
        self.assertEqual("0½", hearts(1, 2))
        self.assertEqual("2¾", hearts(11, 4))
        self.assertEqual("0", hearts(-3, 2))

    def test_a_heart_is_never_rounded_up(self):
        self.assertEqual("0½", hearts(1, 2))
        self.assertEqual("0", hearts(0, 2))

    def test_a_set_without_the_rule_shows_numbers(self):
        _server, _sid, player = _game(self, 0)
        self.assertEqual(0, health_per_heart(player.world))
        self.assertEqual("11/12", format_health(player.world, 11, 12))

    def test_a_set_with_the_rule_shows_hearts_in_status_and_in_the_payloads(self):
        server, sid, player = _game(self, 2)
        player.max_health = 12
        player.health = 11
        self.assertEqual("5½/6 hearts", format_health(player.world, 11, 12))
        status = _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, "status") if e.get("type") == "text"))
        self.assertIn("5½/6 hearts", status)
        player.health = 11  # the command ticked the world, and a hero heals
        self.assertEqual("5½/6 hearts", server._health_payload(player)["text"])
        self.assertEqual((11, 12), (server._health_payload(player)["current"], server._health_payload(player)["max"]))

    def test_the_payload_has_no_text_when_the_set_counts_numbers(self):
        server, _sid, player = _game(self, 0)
        self.assertNotIn("text", server._health_payload(player))


if __name__ == "__main__":
    unittest.main()
