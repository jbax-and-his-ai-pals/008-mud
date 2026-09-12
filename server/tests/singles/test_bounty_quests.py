# tests/singles/test_bounty_quests.py
"""Coverage for the two new bounty quest templates, hand-authored and
board-posted exactly like the existing commissions (see
test_quest_manager_lifecycle.py::TestEnsureInitialQuests for the
generic board-seeding coverage this mirrors). The key property under
test: _add_authored_board_quests only checks "already on the board,"
never "already completed" -- so a bounty against a rare elite reposts
automatically once cleared, with no extra code."""

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


class TestBountyQuestShape(GameTestBase):
    def test_dire_wolf_alpha_bounty_targets_an_elite_dire_wolf(self):
        template = self.world.quest_manager.quest_templates["quest_bounty_dire_wolf_alpha"]
        objective = template["stages"][0]["objective"]
        self.assertEqual("kill", objective["type"])
        self.assertEqual("dire_wolf", objective["target_template_id"])
        self.assertTrue(objective["require_elite"])
        self.assertEqual(1, objective["required_quantity"])
        self.assertEqual("guard_captain", template["stages"][0]["turn_in_id"])

    def test_troll_elder_bounty_targets_an_elite_troll(self):
        template = self.world.quest_manager.quest_templates["quest_bounty_troll_elder"]
        objective = template["stages"][0]["objective"]
        self.assertEqual("kill", objective["type"])
        self.assertEqual("troll", objective["target_template_id"])
        self.assertTrue(objective["require_elite"])
        self.assertEqual(1, objective["required_quantity"])
        self.assertEqual("guard_captain", template["stages"][0]["turn_in_id"])


class TestBountyBoardPosting(GameTestBase):
    def setUp(self):
        super().setUp()
        self.qm = self.world.quest_manager
        self.world.quest_board = []

    def _guard_captain(self):
        return next(n for n in self.world.npcs.values() if n.template_id == "guard_captain")

    def test_both_bounties_are_posted_with_guard_captain_as_giver(self):
        self.qm.ensure_initial_quests(self.player)
        posted = {q["template_id"]: q for q in self.world.quest_board if q.get("template_id", "").startswith("quest_bounty_")}
        self.assertIn("quest_bounty_dire_wolf_alpha", posted)
        self.assertIn("quest_bounty_troll_elder", posted)
        guard_captain = self._guard_captain()
        for quest in posted.values():
            self.assertEqual(guard_captain.obj_id, quest.get("giver_instance_id"))

    def test_completed_bounty_reposts_on_next_replenish(self):
        self.qm.ensure_initial_quests(self.player)
        alpha_quest = next(q for q in self.world.quest_board if q["template_id"] == "quest_bounty_dire_wolf_alpha")
        instance_id = alpha_quest["instance_id"]

        # Simulate turning the bounty in and the board replenishing --
        # the completed quest is removed, then the same template reappears
        # because authored-board seeding never checks completion history.
        self.qm.replenish_board(instance_id, self.player)
        reposted = [q for q in self.world.quest_board if q["template_id"] == "quest_bounty_dire_wolf_alpha"]
        self.assertEqual(1, len(reposted))
        self.assertNotEqual(instance_id, reposted[0]["instance_id"])
