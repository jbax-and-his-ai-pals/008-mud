"""The repair café: a vignette that is playable without being a game.

`modern_capsule` declares `progression_model: none` and enables only `inventory`
and `dialogue` -- no quests, no crafting, no combat, no economy. Its flyer has
advertised a neighbourhood repair café since the set was written, with nothing
behind it. What is behind it now is a conversation with an outcome: Devon takes
the broken lamp and hands back a mended one, and remembers you did it.

These tests are deliberately live journeys, because the claim being made is about
what a player can do in a set with those systems switched off -- a claim no unit
test of the dialogue parser can make.
"""

import os
import unittest

from engine.server.headless_server import HeadlessServer

# tests/fixtures.py exposes FANTASY_FRONTIER for the same reason; this file is
# about the other end of the range, so it resolves its own set.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MIDTOWN = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "content_sets", "modern_capsule"))


class RepairCafeBase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=MIDTOWN,
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.session = self.server.create_session(player_id="repair_cafe")
        self.server.execute_command(self.session.session_id, "char create Alex")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def command(self, text: str) -> str:
        return "\n".join(
            str(event.get("payload", ""))
            for event in self.server.execute_command(self.session.session_id, text)
            if event.get("type") == "text"
        )

    def go(self, direction: str) -> None:
        self.command(direction)


class TestTheRepairCafeIsPlayable(RepairCafeBase):
    def test_the_whole_vignette_from_the_flyer_to_the_mended_lamp(self) -> None:
        # The props are really in the world, not only in the dialogue.
        self.go("north")
        self.assertIn("community flyer", self.command("look"))
        self.assertIn("You pick up", self.command("get flyer"))

        self.go("north")
        self.assertIn("broken desk lamp", self.command("look"))
        self.assertIn("You pick up", self.command("get lamp"))

        # A neighbour explains what the flyer is actually for.
        self.go("south")
        self.go("south")
        explained = self.command("talk Maya")
        self.assertIn("repair cafe", explained)
        invitation = self.command("reply repair cafe")
        self.assertIn("community room", invitation)
        self.assertIn("hold a torch", self.command("reply don't have anything broken"))

        # And the barista runs the electronics table.
        self.go("east")
        self.assertIn("I brought something", self.command("talk Devon"))
        handover = self.command("reply brought something")
        self.assertIn("Come round this side of the counter", handover)
        self.assertIn("You receive mended desk lamp", handover)

        # The broken one is gone; the mended one is yours, and it works.
        self.assertEqual(0, self.player.inventory.count_item("broken_lamp"))
        self.assertEqual(1, self.player.inventory.count_item("mended_lamp"))
        self.assertTrue(self.player.flags.get("lamp_mended"))
        self.assertIn("comes on and stays on", self.command("use mended desk lamp"))

    def test_the_second_conversation_remembers_the_first(self) -> None:
        self.go("north")
        self.command("get flyer")
        self.go("north")
        self.command("get lamp")
        self.go("south")
        self.go("south")
        self.go("east")
        self.command("talk Devon")
        self.command("reply brought something")
        self.command("reply thanks")

        again = self.command("talk Devon")

        self.assertIn("The lamp's still working.", again)
        self.assertNotIn("I brought something", again, "he should not offer to fix it twice")
        self.assertIn("socket working loose", self.command("reply still working"))

    def test_devon_cannot_offer_to_fix_a_lamp_you_are_not_carrying(self) -> None:
        self.go("east")

        opening = self.command("talk Devon")

        self.assertNotIn("I brought something", opening)
        self.assertIn("Tell me about the repair cafe", opening)
        self.assertIn("two faults", self.command("reply tell me about the repair cafe"))

    def test_maya_raises_the_flyer_only_when_you_are_holding_one(self) -> None:
        without = self.command("talk Maya")
        self.assertNotIn("repair cafe", without)
        self.command("reply just waiting for a train")

        self.go("north")
        self.command("get flyer")
        self.go("south")
        with_flyer = self.command("talk Maya")

        self.assertIn("repair cafe", with_flyer)

    def test_none_of_it_needs_progression_quests_or_crafting(self) -> None:
        """The point of the set: something to do, with those systems switched off."""
        world = self.server.world
        for capability in ("quests", "crafting", "combat", "magic", "abilities", "economy"):
            self.assertFalse(world.has_capability(capability), capability)
        self.assertIsNone(self.player.runtime_state.progression)

        self.go("north")
        self.command("get flyer")
        self.go("north")
        self.command("get lamp")
        self.go("south")
        self.go("south")
        self.go("east")
        self.command("talk Devon")
        self.command("reply brought something")

        self.assertEqual(1, self.player.inventory.count_item("mended_lamp"))
        self.assertIsNone(self.player.runtime_state.progression, "still no progression to speak of")


if __name__ == "__main__":
    unittest.main()
