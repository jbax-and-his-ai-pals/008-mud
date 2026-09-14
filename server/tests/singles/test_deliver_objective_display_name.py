# tests/singles/test_deliver_objective_display_name.py
"""Regression coverage for the "Deliver the delivery" bug: a deliver
objective missing an authored item_to_deliver_name used to fall back to a
bare generic noun ("the delivery" in the Journal payload, a raw internal
item_template_id in the board-listing text). quest_wildflower_commission --
one of the earliest quests a new player sees -- has exactly this shape
(recipient_name authored, item_to_deliver_name not), so it's used directly
rather than a synthetic fixture."""

import unittest

from tests.fixtures import make_test_server


class TestDeliverObjectiveDisplayName(unittest.TestCase):
    def _accept_wildflower_commission(self, server, session_id):
        events = server.execute_command(session_id, "look board")
        text = "\n".join(str(e.get("payload", "")) for e in events)
        self.assertIn("A Posy for Riverside", text)

        board = server.world.quest_board
        index = next(
            i for i, quest in enumerate(board)
            if str(quest.get("template_id", "")) == "quest_wildflower_commission"
        )
        server.execute_command(session_id, f"accept quest {index + 1}")

    def test_journal_payload_names_the_item_not_a_generic_noun(self) -> None:
        server = make_test_server()
        try:
            session = server.create_session(player_id="deliver_display_name_test")
            server.execute_command(session.session_id, "char create DeliverNameTester")
            self._accept_wildflower_commission(server, session.session_id)

            payload = server._build_quests_payload(session.session_id)
            active = [q for q in payload["active"] if q["title"] == "A Posy for Riverside"]
            self.assertEqual(1, len(active))
            objective = active[0]["objective"]

            self.assertNotIn("the delivery", objective["summary"].lower())
            self.assertNotIn("item_wildflower_posy", objective["summary"])
            self.assertIn("wildflower posy", objective["summary"].lower())
            self.assertIn("Elder Thorne", objective["summary"])
        finally:
            server.shutdown()

    def test_board_listing_names_the_item_not_a_placeholder(self) -> None:
        server = make_test_server()
        try:
            session = server.create_session(player_id="deliver_display_name_board_test")
            server.execute_command(session.session_id, "char create DeliverNameBoardTester")
            self._accept_wildflower_commission(server, session.session_id)

            events = server.execute_command(session.session_id, "journal")
            text = "\n".join(str(e.get("payload", "")) for e in events)
            self.assertNotIn("the ?", text)
            self.assertNotIn("item_wildflower_posy", text)
            self.assertIn("wildflower posy", text.lower())
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
