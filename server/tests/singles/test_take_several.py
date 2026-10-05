# tests/singles/test_take_several.py
"""Taking several of one thing from an open container in one go: `get all <item> from <container>`, `get <n> <item> from <container>`.

(`get all <item>` and `get <n> <item>`, with no container named, were already there; the `from` form took one at a time.)
"""

import re
import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class TestTakingSeveral(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.player.current_region_id, self.player.current_room_id = "fogreach", "crystal_pool"
        self.say("open iron chest")

    def say(self, command):
        return _MARKUP.sub("", chr(10).join(str(e["payload"]) for e in self.server.execute_command(self.sid, command) if e["type"] == "text"))

    def potions(self):
        return sum(slot.quantity for slot in self.player.inventory.slots if slot.item and slot.item.obj_id == "item_potion")

    def test_all_of_them_at_once(self):
        before = self.potions()
        said = self.say("get all potion from iron chest")
        self.assertIn("3 potions", said)
        self.assertEqual(before + 3, self.potions())
        self.assertIn("not found", self.say("get potion from iron chest"), "and the chest has none left")

    def test_a_number_of_them(self):
        before = self.potions()
        self.assertIn("2 potions", self.say("get 2 potion from iron chest"))
        self.assertEqual(before + 2, self.potions())
        self.assertIn("a potion", self.say("get all potion from iron chest"), "the one that is left")

    def test_asking_for_more_than_there_is_takes_what_there_is(self):
        before = self.potions()
        self.say("get 9 potion from iron chest")
        self.assertEqual(before + 3, self.potions())

    def test_a_plain_get_still_takes_one(self):
        before = self.potions()
        self.assertIn("You get the potion", self.say("get potion from iron chest"))
        self.assertEqual(before + 1, self.potions())

    def test_something_the_chest_does_not_hold_is_not_found(self):
        self.assertIn("not found", self.say("get all sword from iron chest"))

    def test_a_closed_chest_gives_nothing(self):
        self.say("close iron chest")
        self.assertIn("closed", self.say("get all potion from iron chest").lower())


if __name__ == "__main__":
    unittest.main()
