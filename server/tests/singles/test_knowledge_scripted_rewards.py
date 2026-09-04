import unittest

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestKnowledgeScriptedRewards(GameTestBase):
    def _spawn_test_npc(self):
        if "villager" not in self.world.npc_templates:
            self.world.npc_templates["villager"] = {
                "name": "Villager",
                "description": "A helpful villager.",
                "faction": "neutral",
            }
        return NPCFactory.create_npc_from_template("villager", self.world)

    def test_dialogue_give_gold_effect_grants_local_gold_with_feedback(self) -> None:
        npc = self._spawn_test_npc()
        self.assertIsNotNone(npc)
        if npc is None:
            return
        self.world.add_npc(npc)

        self.game.knowledge_manager.topics["reward_topic"] = {
            "display_name": "Reward Topic",
            "responses": [
                {
                    "text": "Take this for your trouble.",
                    "conditions": {},
                    "effects": {"give_gold": 7},
                }
            ],
        }

        response = self.game.knowledge_manager.get_response(npc, "reward_topic", self.player)
        self.assertIsNotNone(response)
        self.assertIn("Take this for your trouble.", str(response))
        self.assertIn("You receive 7 Gold.", str(response))
        self.assertEqual(7, self.player.runtime_state.gold)

    def test_dialogue_give_rewards_effect_grants_local_bundle_with_feedback(self) -> None:
        npc = self._spawn_test_npc()
        self.assertIsNotNone(npc)
        if npc is None:
            return
        self.world.add_npc(npc)

        self.game.knowledge_manager.topics["bundle_topic"] = {
            "display_name": "Bundle Topic",
            "responses": [
                {
                    "text": "You have earned this bundle.",
                    "conditions": {},
                    "effects": {"give_rewards": {"xp": 4, "gold": 5}},
                }
            ],
        }

        response = self.game.knowledge_manager.get_response(npc, "bundle_topic", self.player)
        self.assertIsNotNone(response)
        self.assertIn("You gain 4 XP.", str(response))
        self.assertIn("You receive 5 Gold.", str(response))
        assert self.player.runtime_state.progression is not None
        self.assertEqual(4, self.player.runtime_state.progression.experience)
        self.assertEqual(5, self.player.runtime_state.gold)


class TestKnowledgeScriptedRewardsParty(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.server.feature_profile.world_mode = "co_op_party"
        self.server.feature_profile.raw = {
            "party": {
                "shared_rewards_policy": "split",
            }
        }
        self.leader = self.server.create_session(player_id="reward_leader")
        self.member = self.server.create_session(player_id="reward_member")
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_dialogue_give_rewards_uses_party_split_policy(self) -> None:
        if "villager" not in self.server.world.npc_templates:
            self.server.world.npc_templates["villager"] = {
                "name": "Villager",
                "description": "A helpful villager.",
                "faction": "neutral",
            }
        npc = NPCFactory.create_npc_from_template("villager", self.server.world)
        self.assertIsNotNone(npc)
        if npc is None:
            return
        self.server.world.add_npc(npc)

        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        self.server.knowledge_manager.topics["party_reward_topic"] = {
            "display_name": "Party Reward",
            "responses": [
                {
                    "text": "This belongs to all of you.",
                    "conditions": {},
                    "effects": {"give_rewards": {"xp": 6, "gold": 5}},
                }
            ],
        }

        response = self.server.knowledge_manager.get_response(npc, "party_reward_topic", leader_player)
        self.assertIsNotNone(response)
        self.assertIn("Rewards: Leader +3 XP, Member +3 XP, Leader +3 Gold, Member +2 Gold", str(response))
        assert leader_player.runtime_state.progression is not None
        assert member_player.runtime_state.progression is not None
        self.assertEqual(3, leader_player.runtime_state.progression.experience)
        self.assertEqual(3, member_player.runtime_state.progression.experience)
        self.assertEqual(3, leader_player.runtime_state.gold)
        self.assertEqual(2, member_player.runtime_state.gold)


if __name__ == "__main__":
    unittest.main()
