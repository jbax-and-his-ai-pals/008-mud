"""P6's player-facing quest flows: a commission teaches, and a giver starts.

These are deliberately live content tests rather than parser probes. They keep
the two routes from regressing into the old failures: a recipe known before the
person teaches it, and a large authored quest that has no way to begin.
"""

import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestP6QuestFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            deterministic_test_mode=True,
        )
        self.session = self.server.create_session(player_id="p6_quest_flow")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def command(self, text: str) -> str:
        return "\n".join(
            str(event.get("payload", ""))
            for event in self.server.execute_command(self.session.session_id, text)
            if event.get("type") == "text"
        )

    def _active(self, template_id: str) -> tuple[str, dict]:
        for quest_id, quest in self.player.runtime_state.quests.active.items():
            if quest.get("template_id") == template_id or quest_id.startswith(template_id + "_"):
                return quest_id, quest
        self.fail("%s is not active" % template_id)

    def test_background_does_not_preteach_first_commission_recipe(self) -> None:
        self.assertNotIn("tie_wildflower_posy", self.player.known_recipe_ids)

        self.command("accept quest 1")
        opening = self.command("talk Elder Thorne")
        teaching = self.command("reply commission")

        self.assertIn("posy commission", opening.lower())
        self.assertIn("community garden", teaching.lower())
        self.assertIn("tie_wildflower_posy", self.player.known_recipe_ids)

    def test_missing_guard_is_given_by_elara_and_playable_to_the_final_return(self) -> None:
        self.command("talk Guard Captain Elara")
        briefing = self.command("reply missing guard")
        accepted = self.command("reply accept")
        self.assertIn("abandoned mill", briefing.lower())
        self.assertIn("Quest Accepted", accepted)
        quest_id, quest = self._active("quest_missing_guard")
        self.assertEqual(0, quest["current_stage_index"])

        for command in ("south", "south", "east", "east", "take bloody tabard", "west", "west", "north", "north"):
            self.command(command)
        self.assertEqual(1, self.player.inventory.count_item("item_bloody_tabard"))

        first_turn_in = self.command("talk Guard Captain Elara complete")
        self.assertIn("Objective Complete", first_turn_in)
        self.assertEqual(1, quest["current_stage_index"])
        self.assertEqual(1, self.player.inventory.count_item("item_bloody_tabard"))

        second_turn_in = self.command("talk Kaelan complete")
        self.assertIn("Objective Complete", second_turn_in)
        self.assertEqual(2, quest["current_stage_index"])
        self.assertEqual(0, self.player.inventory.count_item("item_bloody_tabard"))

        for command in ("south", "downstream", "south"):
            self.command(command)
        troll = next(
            npc for npc in self.server.world.npcs.values()
            if npc.template_id == "river_troll" and npc.current_region_id == "swamp"
        )
        self.server.world.dispatch_event("npc_killed", {"player": self.player, "npc": troll})
        self.assertEqual("ready_to_complete", quest["state"])

        for command in ("north", "upstream", "north"):
            self.command(command)
        completed = self.command("talk Guard Captain Elara complete")
        self.assertIn("Quest Complete", completed)
        self.assertNotIn(quest_id, self.player.runtime_state.quests.active)
        self.assertIn(quest_id, self.player.runtime_state.quests.completed)


if __name__ == "__main__":
    unittest.main()
