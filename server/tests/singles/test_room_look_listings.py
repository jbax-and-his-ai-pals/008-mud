# tests/singles/test_room_look_listings.py
"""A room description only lists what is there.

"People here: (None)", "Hostiles: (None)" and "Items: (None)" told a player nothing, three times
over, in every empty room. A listing with nothing in it is now left out. The first listing that
does appear is set apart from the exits by a blank line, and the later ones follow on the next
line. A new character is shown their room after two blank lines, so it does not run into the
intro above it.
"""

import re
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _boot(set_id):
    server = HeadlessServer(
        db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / set_id),
        deterministic_test_mode=True, default_presentation_mode="player",
    )
    sid = server.create_session(player_id="look").session_id
    events = server.execute_command(sid, "char create Tester")
    return server, sid, events


def _text(events):
    return [_MARKUP.sub("", str(e["payload"])) for e in events if e["type"] == "text"]


class TestLookListings(unittest.TestCase):
    def test_empty_listings_are_not_shown(self):
        server, sid, _events = _boot("zelda_slice")
        self.addCleanup(server.shutdown)
        said = "\n".join(_text(server.execute_command(sid, "look")))
        self.assertIn("Exits:", said)
        for empty in ("(None)", "People here", "Hostiles", "Items:"):
            self.assertNotIn(empty, said, "the starting meadow has no one and nothing in it")

    def test_a_listing_with_someone_in_it_is_shown_once_and_alone(self):
        server, sid, _events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        said = "\n".join(_text(server.execute_command(sid, "look")))
        self.assertIn("People here: King Aldous", said)
        self.assertNotIn("Hostiles", said)
        self.assertNotIn("Items:", said)
        self.assertNotIn("(None)", said)
        self.assertRegex(said, r"Exits: [^\n]*\n\nPeople here", "set apart from the exits by a blank line")

    def test_later_listings_follow_on_the_next_line(self):
        server, sid, _events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "road", "castle_road"
        said = "\n".join(_text(server.execute_command(sid, "look")))
        # the goblin scout lives here: a hostile listing with no one friendly above it
        self.assertIn("Hostiles:", said)
        self.assertNotIn("People here", said)
        self.assertRegex(said, r"Exits: [^\n]*\n\nHostiles", "the first listing, whichever it is, gets the blank line")

    def test_a_new_characters_room_is_set_apart_from_their_intro(self):
        server, _sid, events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        raw = [str(e["payload"]) for e in events if e["type"] == "text"]
        look = next(t for t in raw if "[VARENHOLT - THRONE ROOM]" in _MARKUP.sub("", t).upper())
        self.assertTrue(look.startswith("\n\n"), repr(look[:12]))


class TestWordingAndSpacing(unittest.TestCase):
    def test_a_name_that_carries_its_article_does_not_get_another(self):
        server, sid, _events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "varenholt", "stores"
        next(n for n in server.world.npcs.values() if n.template_id == "quartermaster").name = "the quartermaster"
        said = "\n".join(_text(server.execute_command(sid, "look")))
        self.assertIn("People here: the quartermaster", said)
        self.assertNotIn("a the", said)

    def test_looking_at_a_thing_whose_name_has_an_article_does_not_double_it(self):
        server, sid, _events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        next(n for n in server.world.npcs.values() if n.template_id == "chancellor").name = "the chancellor"
        said = "\n".join(_text(server.execute_command(sid, "look the chancellor")))
        self.assertIn("The chancellor looks healthy", said)
        self.assertNotIn("The the", said)

    def test_something_that_happens_on_its_own_starts_a_line_below_the_last(self):
        from engine.server.headless.lifecycle import _passive

        self.assertEqual("\nThe sun rises.", _passive("The sun rises."))

    def test_the_rewards_for_a_kill_are_a_block_under_the_blow(self):
        server, sid, _events = _boot("ff4_slice")
        self.addCleanup(server.shutdown)
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "road", "castle_road"
        goblin = next(n for n in server.world.npcs.values() if n.template_id == "goblin_scout")
        goblin.health = 1
        for _ in range(40):
            server.tick(sid)
        said = "\n".join(_text(server.execute_command(sid, "attack goblin")))
        self.assertRegex(said, r"defeated!\n\nYou find \d+ gil\.\nYou gain \d+ experience!")


if __name__ == "__main__":
    unittest.main()
