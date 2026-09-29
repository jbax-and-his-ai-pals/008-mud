# tests/singles/test_finite_adventure_reset_closes_exits.py
"""`adventure reset` puts the world back, including a door a lever opened.

The baseline recorded a room's `properties` (which hold a *link* to `room.exits`) and
restored them by re-linking `properties["exits"]` to the live exits, so the exits a
lever, a `reveal_exit` or a Zelda-style bomb had added were never taken away again:
the world was "reset" with the way still open. The exits were never part of what the
baseline kept.
"""

import unittest
from pathlib import Path

from engine.campaign.campaign_models import CampaignDefinition, CampaignNode, CampaignTransition
from engine.server.headless_server import HeadlessServer

FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestFiniteAdventureResetClosesExits(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.server.feature_profile.world_mode = "finite_adventure"
        self.server.feature_profile.raw = {"finite_adventure": {"default_campaign_id": "intro_story", "replay_supported": True}}
        self.session = self.server.create_session(player_id="hero_player")
        self.server.execute_command(self.session.session_id, "char create Hero")
        self.server.world.quest_manager.quest_templates["intro_quest"] = {
            "title": "Intro Step", "type": "fetch",
            "stages": [{"stage_index": 0, "description": "Do the thing.",
                        "objective": {"type": "fetch", "item_id": "rock", "required_quantity": 1}, "turn_in_id": "quest_giver"}],
            "rewards": {"xp": 10},
        }
        self.server.world.campaign_manager.definitions["intro_story"] = CampaignDefinition(
            campaign_id="intro_story", name="Intro Story", description="x", start_node_id="node_intro",
            nodes={
                "node_intro": CampaignNode(node_id="node_intro", description="Start", quest_template_id="intro_quest",
                                           transitions=[CampaignTransition(trigger="SUCCESS", target_node_id="node_end")]),
                "node_end": CampaignNode(node_id="node_end", description="Finish", node_type="END", outcome="VICTORY"),
            },
        )
        self.addCleanup(self.server.shutdown)

    def _square(self):
        return self.server.world.regions["town"].get_room("town_square")

    def test_reset_closes_an_exit_that_was_opened_after_the_adventure_began(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        before = dict(self._square().exits)
        self._square().exits["down"] = "town:tavern_cellar"  # what a lever or `reveal_exit` does

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure reset")

        restored = self._square()
        self.assertEqual(before, dict(restored.exits))
        self.assertEqual(before, dict(restored.properties["exits"]), "the properties link points at the restored exits")

    def test_reset_reopens_an_exit_that_was_closed_after_the_adventure_began(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        before = dict(self._square().exits)
        direction = next(iter(before))
        del self._square().exits[direction]

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure reset")

        self.assertEqual(before, dict(self._square().exits))


if __name__ == "__main__":
    unittest.main()
