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


def _two_dark_rooms(server, player):
    """The player's room and a room beside it by an exit within the region, both dark; returns the direction between them."""
    region = server.world.get_region(player.current_region_id)
    here = region.get_room(player.current_room_id)
    for direction, destination in here.exits.items():
        if ":" not in destination and destination in region.rooms:
            here.properties["dark"] = True
            region.get_room(destination).properties["dark"] = True
            return direction, destination
    raise AssertionError("no exit inside the region to walk")


def _text(server, sid, command):
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, command) if e.get("type") in ("text", "error")))


class TestMovingInTheDark(unittest.TestCase):
    def test_a_wall_in_the_dark_says_so_and_a_step_says_it_was_taken(self):
        server, sid, player = _game(self, True)
        direction, destination = _two_dark_rooms(server, player)
        missing = next(d for d in ("up", "down", "in", "out", "northwest", "southeast") if d not in server.world.get_current_room(player).exits)
        self.assertIn("find no way %s" % missing, _text(server, sid, "go " + missing))
        stepped = _text(server, sid, "go " + direction)
        self.assertEqual(destination, player.current_room_id)
        self.assertIn("feel your way forward", stepped)
        self.assertNotIn("have entered", stepped)
        self.assertNotIn("[", stepped, "and not the name of where it landed")

    def test_the_side_panel_knows_no_more_than_the_text(self):
        server, sid, player = _game(self, True)
        _two_dark_rooms(server, player)
        payload = server._build_nearby_payload(sid)
        self.assertEqual("Darkness", payload["location"]["room_name"])
        self.assertEqual([], payload["exits"])
        self.assertEqual([], payload["npcs"])
        self.assertEqual([], payload["items"])

    def test_with_a_light_the_panel_and_the_step_are_ordinary(self):
        server, sid, player = _game(self, True)
        direction, _destination = _two_dark_rooms(server, player)
        player.apply_effect({"type": "status", "name": "Torchlight", "tags": ["light"], "base_duration": 60}, 0.0)
        self.assertNotEqual("Darkness", server._build_nearby_payload(sid)["location"]["room_name"])
        self.assertNotIn("feel your way", _text(server, sid, "go " + direction))

    def test_nothing_can_be_looked_at_in_the_dark(self):
        server, sid, player = _game(self, True)
        _two_dark_rooms(server, player)
        self.assertIn("pitch dark", _look(server, sid))
        self.assertIn("pitch dark", _text(server, sid, "look sword"))


if __name__ == "__main__":
    unittest.main()
