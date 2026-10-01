# tests/singles/test_panel_payloads.py
"""A client's side panels get their data as events, and only when it changes.

`character` (level, gold, stats, equipment, spells, skills, effects) and `world` (time, date,
period, season, weather) join the existing `inventory` and `quests` events. They are sent when a
character is created or resumed, and afterwards only when their content differs from what that
session last received. Creating a character also shows the room, as `look` would.
"""

import re
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _boot(set_id="ff4_slice"):
    return HeadlessServer(
        db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / set_id),
        deterministic_test_mode=True, default_presentation_mode="player",
    )


def _types(events):
    return [e["type"] for e in events]


class TestPanelPayloads(unittest.TestCase):
    def setUp(self):
        self.server = _boot()
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="panel").session_id
        self.created = self.server.execute_command(self.sid, "char create Tester")
        self.player = self.server.get_player_for_session(self.sid)

    def payload(self, events, kind):
        return next(e["payload"] for e in events if e["type"] == kind)

    def test_creating_a_character_sends_every_panel_and_shows_the_room(self):
        types = _types(self.created)
        for kind in ("character", "world", "inventory", "quests"):
            self.assertIn(kind, types)
        texts = [_MARKUP.sub("", str(e["payload"])) for e in self.created if e["type"] == "text"]
        self.assertTrue(any("THRONE ROOM" in t.upper() for t in texts), "the room is shown, as look would")

    def test_the_character_sheet_carries_the_sets_own_vocabulary(self):
        sheet = self.payload(self.created, "character")
        self.assertEqual("Tester", sheet["name"])
        self.assertEqual(1, sheet["level"])
        self.assertEqual("gil", sheet["currency"], "the currency is the set's, not 'gold'")
        self.assertEqual("MP", sheet["ability_resource"]["short"])
        self.assertEqual(sheet["health"]["max"], self.player.max_health)
        self.assertIn("STR", [s["label"] for s in sheet["stats"]])
        self.assertEqual({"main_hand", "off_hand", "head", "body", "hands", "feet", "neck"}, {e["slot"] for e in sheet["equipment"]})

    def test_the_world_panel_has_a_clock_and_the_weather_where_you_stand(self):
        world = self.payload(self.created, "world")
        self.assertRegex(world["time"], r"^\d\d:\d\d$")
        self.assertTrue(world["weather"])
        self.assertTrue(world["period"])

    def test_a_world_with_no_clock_of_its_own_starts_at_noon(self):
        world = self.payload(self.created, "world")
        self.assertTrue(world["time"].startswith("12:"), world["time"])
        self.assertNotEqual("night", world["period"])

    def test_nothing_is_resent_when_nothing_changed(self):
        first = self.server._panel_events(self.sid)
        second = self.server._panel_events(self.sid)
        self.assertEqual([], [e for e in second if e["type"] in ("character", "inventory", "quests")])
        self.assertLessEqual(len(first), 1, "at most the clock moved")

    def test_wearing_something_changes_the_character_sheet(self):
        armor = ItemFactory.create_item_from_template("item_dark_armor", self.server.world)
        self.player.inventory.add_item(armor)
        self.server.execute_command(self.sid, "equip dark armor")
        again = self.server._panel_events(self.sid, force=True)
        body = next(e for e in self.payload(again, "character")["equipment"] if e["slot"] == "body")
        self.assertEqual("dark armor", body["item"])
        self.assertRegex(body["durability"], r"^\d+/\d+$")

    def test_a_command_that_changes_the_pack_sends_the_pack_without_being_asked(self):
        events = self.server.execute_command(self.sid, "equip dark armor")
        self.assertIn("inventory", _types(events))
        self.assertIn("character", _types(events))

    def test_a_session_with_no_character_gets_no_panels(self):
        other = self.server.create_session(player_id="nobody").session_id
        self.assertEqual([], self.server._panel_events(other))


if __name__ == "__main__":
    unittest.main()
