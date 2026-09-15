"""Every background must be able to start playing the moment it exists.

The design rule is that a background decides where you *begin* and never what
you can do. P4 shipped six backgrounds and broke that rule by accident: three
of them (apprentice, acolyte, pedlar) had no foraging knife, and the opening
commission -- "A Posy for Riverside" -- cannot be finished without one. A
player who picked Acolyte was told, at minute one, that they needed a tool they
had no obvious way to recognise or obtain. Conversely, the posy recipe is Elder
Thorne's lesson, not a background perk.

Content could drift again the same way, so this test walks each authored
background through the opening move rather than trusting the kit by eye.
"""

from pathlib import Path
import unittest

from engine.server.content_set import load_content_set
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"

# The room the opening commission sends you to.
GATHERING_ROOM = ("town", "community_garden")


class TestEveryBackgroundCanStart(unittest.TestCase):
    def _background_ids(self) -> list[str]:
        definition, issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(definition, issues)
        assert definition is not None
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            return [b.background_id for b in server.background_manager.available()]
        finally:
            server.shutdown()

    def test_every_background_starts_with_a_usable_kit(self) -> None:
        background_ids = self._background_ids()
        self.assertGreaterEqual(len(background_ids), 2, "no backgrounds to check")

        for background_id in background_ids:
            with self.subTest(background=background_id):
                server = HeadlessServer(
                    db_path=":memory:",
                    content_set_path=str(FANTASY_FRONTIER),
                    deterministic_test_mode=True,
                )
                try:
                    session = server.create_session(player_id="opening_%s" % background_id)
                    created = server.execute_command(
                        session.session_id, "char create Tester as %s" % background_id
                    )
                    created_text = "\n".join(
                        str(event["payload"]) for event in created if event.get("type") == "text"
                    )
                    self.assertIn("Character created", created_text)

                    player = server.get_player_for_session(session.session_id)
                    self.assertEqual(background_id, player.background_id)
                    self.assertNotIn(
                        "tie_wildflower_posy",
                        player.known_recipe_ids,
                        "background %r pre-teaches Elder Thorne's opening lesson" % background_id,
                    )

                    # A weapon to fight with, and the tool the opening
                    # commission needs. Weapons ship carried rather than
                    # equipped, so "carried" counts.
                    weapon = player.equipment.get("main_hand") or self._carried_weapon(player)
                    self.assertIsNotNone(
                        weapon, "background %r starts with nothing to fight with" % background_id
                    )

                    player.current_region_id, player.current_room_id = GATHERING_ROOM
                    gathered = server.execute_command(session.session_id, "gather herb bed")
                    gathered_text = "\n".join(
                        str(event["payload"]) for event in gathered if event.get("type") == "text"
                    )
                    self.assertNotIn(
                        "You don't seem to be carrying or wearing one",
                        gathered_text,
                        "background %r cannot gather, so the opening commission "
                        "cannot be started" % background_id,
                    )
                    self.assertGreaterEqual(
                        player.inventory.count_item("item_wild_herbs"),
                        1,
                        "background %r gathered nothing" % background_id,
                    )
                finally:
                    server.shutdown()

    @staticmethod
    def _carried_weapon(player):
        """A usable weapon in the pack, since kits ship weapons carried."""
        for slot in player.inventory.slots:
            item = getattr(slot, "item", None)
            if item is None:
                continue
            if item.get_property("damage") or item.get_property("attack_power"):
                return item
        return None


if __name__ == "__main__":
    unittest.main()
