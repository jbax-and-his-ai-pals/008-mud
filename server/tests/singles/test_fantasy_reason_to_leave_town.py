"""WORLD_DESIGN section 9 item 2: a new player "is given a reason to walk out
of town that is not 'kill things'".

The opening's only path out of town was "Explore and face danger: equip your
rusty dagger" -- a dagger four of the six backgrounds do not carry. It now
also offers Elder Thorne's errand to Old Bryn, the hermit by the ancient oak.
This plays that errand, as every background, the way a new player would: read
the board and accept by the number shown, gather herbs in the garden, walk to
the oak, win Bryn over with a gift, walk back, and hand it in with the command
the journal names. No attack or spell is ever used.

Three things this found and fixed: `accept quest <n>` before looking at the
board counted the notices a player-mode board hides, and took a different
one; the journal said "Ready to turn in!" but not how (talking to the giver
offers no hand-in); and half the backgrounds could make Bryn nothing, while an
ordinary gift is worth 1 point a day against the 5 he needs -- he now values
the garden's herbs.
"""

import re
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
QUEST_TITLE = "The Hermit of the Deep Wood"


def _server() -> HeadlessServer:
    return HeadlessServer(
        db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
        deterministic_test_mode=True, default_presentation_mode="player",
    )


class _Player:
    def __init__(self, server: HeadlessServer, background: str) -> None:
        self.server = server
        self.session = server.create_session(player_id=f"errand_{background}")
        self.opening = self.run(f"char create Seeker as {background}")
        self.player = server.get_player_for_session(self.session.session_id)

    def run(self, command: str) -> str:
        lines = []
        for event in self.server.execute_command(self.session.session_id, command) or []:
            if isinstance(event, dict) and event.get("type") == "text":
                payload = event.get("payload")
                lines.append(str(payload.get("text", "") if isinstance(payload, dict) else payload))
        return "\n".join(lines)

    def walk(self, region: str, room: str) -> None:
        path = self.server.world.find_path(self.player.current_region_id, self.player.current_room_id, region, room)
        assert path is not None, f"no path to {region}:{room}"
        for direction in path:
            self.run(direction)


class TestAReasonToLeaveTown(unittest.TestCase):
    def test_every_background_can_run_the_hermit_errand_without_fighting(self):
        backgrounds = [b.background_id for b in _server().background_manager.available()]
        for background in backgrounds:
            with self.subTest(background=background):
                server = _server()
                self.addCleanup(server.shutdown)
                seeker = _Player(server, background)
                self.assertIn("Old Bryn", seeker.opening, "the opening offers the errand")

                board = seeker.run("look board")
                number = re.search(r"\[(\d+)\]\S*\s+" + re.escape(QUEST_TITLE), board).group(1)
                self.assertIn("Quest Accepted", seeker.run(f"accept quest {number}"))

                seeker.walk("town", "community_garden")
                seeker.run("gather herb bed")
                seeker.walk("forest", "ancient_oak")
                gift = self._handmade_gift(seeker) or "wild herbs"
                self.assertIn("You give", seeker.run(f"give {gift} to bryn"))
                self.assertGreaterEqual(int(seeker.player.npc_relationships.get("forest_hermit", 0)), 5)

                seeker.walk("town", "town_square")
                journal = seeker.run("journal")
                hand_in = re.search(r"Ready to turn in! \((?:\[\[/\]\])?(talk [^\[\)]+)", journal)
                self.assertIsNotNone(hand_in, f"the journal says how to hand it in: {journal[-300:]}")
                done = seeker.run(hand_in.group(1).strip())
                self.assertIn("Quest Complete", done)
                self.assertTrue(seeker.player.is_alive)

    def test_accepting_before_looking_takes_the_notice_the_board_shows(self):
        server = _server()
        self.addCleanup(server.shutdown)
        first = _Player(server, "wanderer")
        shown = re.findall(r"\[(\d+)\]\S*\s+([^\[\n]+)", first.run("look board"))
        number, title = next((n, t.strip()) for n, t in shown if t.strip() == QUEST_TITLE)
        # A second player, same board, who never looks at it.
        second = _Player(server, "wanderer")
        self.assertIn(f"[Quest Accepted] {title}", second.run(f"accept quest {number}"))

    @staticmethod
    def _handmade_gift(seeker: _Player):
        for recipe_id in sorted(seeker.player.known_recipe_ids):
            if "Successfully crafted" in seeker.run(f"craft {recipe_id}"):
                result = seeker.server.crafting_manager.recipes[recipe_id].result_item_id
                return ItemFactory.create_item_from_template(result, seeker.server.world).name
        return None


if __name__ == "__main__":
    unittest.main()
