# tests/singles/test_search_and_distance.py
"""A thing found by `search` at one place (trigger event `searched`), an effect that tells the distance to a place (`tell_distance`), and a
consumable that is not used up (`reusable`)."""

import re
import unittest

from engine.items.consumable import Consumable
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _game(case):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    return server, sid, server.get_player_for_session(sid)


def _say(server, sid, command):
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, command) if e.get("type") in ("text", "error")))


def _other_room(server, player):
    region = server.world.get_region(player.current_region_id)
    return player.current_region_id, next(room_id for room_id in region.rooms if room_id != player.current_room_id)


class TestSearchingFindsThingsAtOnePlace(unittest.TestCase):
    def _arm(self, server, player, once):
        server.world.trigger_runner.add("found_it", {
            "on": {"event": "searched", "region": player.current_region_id, "room": player.current_room_id},
            "once": once, "effects": {"set_flag": "found_the_token", "message": "You turn over a flat stone and find a small token."}})

    def test_searching_anywhere_else_finds_nothing(self):
        server, sid, player = _game(self)
        self._arm(server, player, "player")
        region_id, other = _other_room(server, player)
        player.current_room_id = other
        self.assertIn("nothing to search", _say(server, sid, "search"))
        self.assertIsNone(player.flags.get("found_the_token"))

    def test_searching_the_place_finds_it_once(self):
        server, sid, player = _game(self)
        self._arm(server, player, "player")
        self.assertIn("small token", _say(server, sid, "search"))
        self.assertIs(True, player.flags.get("found_the_token"))
        self.assertIn("nothing to search", _say(server, sid, "search"), "and only once")

    def test_the_event_is_in_the_engines_vocabulary(self):
        from engine.world.triggers import EVENT_FIELDS, EVENT_REQUIRED, TRIGGER_EVENTS

        self.assertIn("searched", TRIGGER_EVENTS)
        self.assertEqual(("region", "room"), EVENT_FIELDS["searched"])
        self.assertEqual(("region", "room"), EVENT_REQUIRED["searched"])


class TestTellingTheDistance(unittest.TestCase):
    def test_it_says_how_many_rooms_away_a_place_is(self):
        server, _sid, player = _game(self)
        region_id, other = _other_room(server, player)
        path = server.world.find_path(player.current_region_id, player.current_room_id, region_id, other)
        item = Consumable(obj_id="item_locator", name="locket", uses=1, effect_type="effects", reusable=True,
                          effects={"tell_distance": {"region": region_id, "room": other, "message": "It is {steps} steps to the end."}})
        said = item.use(player)
        self.assertIn("It is %d steps to the end." % len(path), said)

    def test_a_reusable_item_is_not_used_up(self):
        server, _sid, player = _game(self)
        region_id, other = _other_room(server, player)
        item = Consumable(obj_id="item_locator", name="locket", uses=1, effect_type="effects", reusable=True,
                          effects={"tell_distance": {"region": region_id, "room": other}})
        item.use(player)
        item.use(player)
        self.assertEqual(1, item.get_property("uses"))

    def test_a_place_with_no_way_is_said_so(self):
        server, _sid, player = _game(self)
        from engine.dialogue.effects import apply_effects

        report = apply_effects({"tell_distance": {"region": "no_such_region", "room": "x"}}, {"player": player, "world": server.world})
        self.assertTrue(report.failed)


if __name__ == "__main__":
    unittest.main()
