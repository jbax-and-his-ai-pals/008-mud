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

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _boot(set_id="story_fixture"):
    return HeadlessServer(
        db_path=":memory:", content_set_path=str(STORY_FIXTURE if set_id == "story_fixture" else REPO_ROOT / "content_sets" / set_id),
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

    def test_the_room_pane_gets_what_look_says_and_follows_the_player(self):
        room = self.payload(self.created, "room")["text"]
        self.assertIn("THRONE ROOM", room.upper())
        self.assertIn("Exits:", room)
        self.player.current_region_id, self.player.current_room_id = "varenholt", "courtyard"
        moved = self.server._panel_events(self.sid)
        self.assertIn("COURTYARD", self.payload(moved, "room")["text"].upper())

    def test_the_attack_cooldown_is_sent_when_you_attack_and_not_every_tick(self):
        from engine.npcs.npc_factory import NPCFactory

        ready = self.payload(self.created, "cooldown")["attack"]
        self.assertEqual(0.0, ready["remaining"], "nothing has been swung yet")
        self.assertGreater(ready["duration"], 0)
        self.player.current_region_id, self.player.current_room_id = "road", "castle_road"
        rat = NPCFactory.create_npc_from_template("goblin_scout", self.server.world, instance_id="cd_target")
        rat.current_region_id, rat.current_room_id = "road", "castle_road"
        rat.health = rat.max_health = 500
        self.server.world.add_npc(rat)
        self.server._panel_events(self.sid)
        events = self.server.execute_command(self.sid, "attack goblin")
        swung = self.payload(events, "cooldown")["attack"]
        self.assertGreater(swung["remaining"], 0)
        self.assertLessEqual(swung["remaining"], swung["duration"])
        for _ in range(3):
            self.assertEqual([], [e for e in self.server._panel_events(self.sid) if e["type"] == "cooldown"],
                             "the client counts down; the server does not resend")

    def test_an_ability_on_cooldown_is_sent_once_and_the_character_sheet_is_not_resent_each_tick(self):
        from engine.npcs.npc_factory import NPCFactory

        listed = {a["id"]: a for a in self.payload(self.created, "cooldown")["abilities"]}
        self.assertEqual(0.0, listed["dark_wave"]["remaining"])
        self.assertEqual(6.0, listed["dark_wave"]["duration"])
        self.player.current_region_id, self.player.current_room_id = "road", "castle_road"
        target = NPCFactory.create_npc_from_template("goblin_scout", self.server.world, instance_id="cd_ability_target")
        target.current_region_id, target.current_room_id = "road", "castle_road"
        target.health = target.max_health = 500
        self.server.world.add_npc(target)
        self.server._panel_events(self.sid)
        events = self.server.execute_command(self.sid, "cast dark wave")
        cooling = {a["id"]: a for a in self.payload(events, "cooldown")["abilities"]}["dark_wave"]
        self.assertGreater(cooling["remaining"], 0)
        later = self.server._panel_events(self.sid)
        self.assertEqual([], [e for e in later if e["type"] == "cooldown"], "counted down by the client")
        self.assertNotIn("cooldown", self.payload(self.server._panel_events(self.sid, force=True), "character")["spells"][0],
                         "the sheet no longer carries a countdown that would resend it every tick")

    def test_the_room_is_not_resent_while_it_is_the_same(self):
        self.server._panel_events(self.sid)
        self.assertEqual([], [e for e in self.server._panel_events(self.sid) if e["type"] == "room"])

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
