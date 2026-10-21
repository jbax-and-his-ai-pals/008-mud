# tests/singles/test_dark_rooms.py
"""`ruleset.world.dark_requires_light`: a dark room shows nothing to a player who carries no light."""

import re
import unittest

from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _game(case, rule):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    if rule:
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"dark_requires_light": True} if name == "world" else original(name)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    player = server.get_player_for_session(sid)
    room = server.world.get_region(player.current_region_id).get_room(player.current_room_id)
    room.properties["dark"] = True
    return server, sid, player


def _look(server, sid):
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, "look") if e.get("type") == "text"))


class TestDarkRooms(unittest.TestCase):
    def test_without_the_rule_darkness_is_only_atmosphere(self):
        server, sid, _player = _game(self, False)
        self.assertIn("very dark", _look(server, sid))
        self.assertIn("Exits", _look(server, sid))

    def test_with_the_rule_an_unlit_dark_room_shows_nothing(self):
        server, sid, _player = _game(self, True)
        text = _look(server, sid)
        self.assertIn("pitch dark", text)
        self.assertNotIn("Exits", text)
        self.assertNotIn("[", text, "not even the room's name")

    def test_a_light_shows_the_room_and_wears_off(self):
        server, sid, player = _game(self, True)
        ok, _message = player.apply_effect({"type": "status", "name": "Torchlight", "tags": ["light"], "base_duration": 30}, 0.0)
        self.assertTrue(ok)
        self.assertIn("Exits", _look(server, sid))
        player.active_effects.clear()
        self.assertIn("pitch dark", _look(server, sid))


if __name__ == "__main__":
    unittest.main()
