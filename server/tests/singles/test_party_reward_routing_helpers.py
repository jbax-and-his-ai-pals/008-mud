import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from engine.items.item_factory import ItemFactory

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestPartyRewardRoutingHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.server.feature_profile.world_mode = "co_op_party"
        self.leader = self.server.create_session()
        self.member = self.server.create_session()
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        self.leader_player = self.server.get_player_for_session(self.leader.session_id)
        self.member_player = self.server.get_player_for_session(self.member.session_id)
        # Co-locate so party_member_players' same-location filters pass.
        self.member_player.current_region_id = self.leader_player.current_region_id
        self.member_player.current_room_id = self.leader_player.current_room_id

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_split_int_amount_handles_zero_and_negative_count(self):
        self.assertEqual([], self.server._split_int_amount(10, 0))
        self.assertEqual([], self.server._split_int_amount(10, -1))

    def test_split_int_amount_distributes_remainder_to_first_recipients(self):
        self.assertEqual([4, 3, 3], self.server._split_int_amount(10, 3))

    def test_reward_routing_inactive_outside_co_op_party_mode(self):
        self.server.feature_profile.world_mode = "single_player_story"
        self.assertFalse(self.server.party_reward_routing_active(self.leader_player))

    def test_reward_routing_inactive_with_no_party(self):
        solo = self.server.create_session()
        self.server.execute_command(solo.session_id, "char create Solo")
        solo_player = self.server.get_player_for_session(solo.session_id)
        self.assertFalse(self.server.party_reward_routing_active(solo_player))

    def test_reward_routing_inactive_for_blank_actor_id(self):
        class _Blank:
            obj_id = ""
        self.assertFalse(self.server.party_reward_routing_active(_Blank()))

    def test_reward_routing_active_in_party(self):
        self.assertTrue(self.server.party_reward_routing_active(self.leader_player))

    def test_reward_recipients_outside_party_is_just_the_actor(self):
        solo = self.server.create_session()
        self.server.execute_command(solo.session_id, "char create Solo2")
        solo_player = self.server.get_player_for_session(solo.session_id)
        self.assertEqual([solo_player], self.server._reward_recipient_players(solo_player))

    def test_reward_recipients_leader_claims_policy(self):
        self.server.feature_profile.party_leader_claims_rewards = True  # if raw-config path exists this is a no-op
        self.server._raw_profile_config = getattr(self.server, "_raw_profile_config", {})
        # party_policy_value reads from feature_profile raw config; patch the accessor directly for isolation.
        original = self.server.party_policy_value
        self.server.party_policy_value = lambda key, default=None: "leader_claims" if key == "shared_rewards_policy" else original(key, default)
        try:
            recipients = self.server._reward_recipient_players(self.member_player)
            self.assertEqual([self.leader_player], recipients)
        finally:
            self.server.party_policy_value = original

    def test_distribute_party_loot_outside_co_op_party_mode(self):
        self.server.feature_profile.world_mode = "single_player_story"
        item = ItemFactory.create_item_from_template("item_starter_dagger", self.server.world)
        recipient, note = self.server.distribute_party_loot(self.leader_player, item)
        self.assertIs(recipient, self.leader_player)
        self.assertEqual("", note)

    def test_distribute_party_loot_leader_discretion_policy(self):
        original = self.server.party_policy_value
        self.server.party_policy_value = lambda key, default=None: "leader_discretion" if key == "loot_policy" else original(key, default)
        try:
            item = ItemFactory.create_item_from_template("item_starter_dagger", self.server.world)
            recipient, note = self.server.distribute_party_loot(self.member_player, item)
            self.assertIs(recipient, self.leader_player)
            self.assertIn("routed", note)
        finally:
            self.server.party_policy_value = original

    def test_distribute_party_loot_finder_keep_policy(self):
        original = self.server.party_policy_value
        self.server.party_policy_value = lambda key, default=None: "finder_keep" if key == "loot_policy" else original(key, default)
        try:
            item = ItemFactory.create_item_from_template("item_starter_dagger", self.server.world)
            recipient, note = self.server.distribute_party_loot(self.member_player, item)
            self.assertIs(recipient, self.member_player)
            self.assertEqual("", note)  # recipient == actor -> no note
        finally:
            self.server.party_policy_value = original

    def test_distribute_party_loot_falls_back_to_actor_when_recipient_cannot_hold_item(self):
        original = self.server.party_policy_value
        self.server.party_policy_value = lambda key, default=None: "leader_discretion" if key == "loot_policy" else original(key, default)
        try:
            item = ItemFactory.create_item_from_template("item_starter_dagger", self.server.world)
            self.leader_player.inventory.max_weight = 0.0  # leader cannot accept anything
            recipient, note = self.server.distribute_party_loot(self.member_player, item)
            self.assertIs(recipient, self.member_player)
        finally:
            self.server.party_policy_value = original

    def test_grant_party_rewards_splits_xp_and_gold(self):
        result = self.server.grant_party_rewards(self.leader_player, {"xp": 100, "gold": 10})
        self.assertIn("XP", result)
        self.assertIn("Gold", result)

    def test_grant_party_rewards_with_no_rewards_returns_empty_string(self):
        self.assertEqual("", self.server.grant_party_rewards(self.leader_player, {}))

    def test_grant_party_rewards_distributes_item_rewards(self):
        result = self.server.grant_party_rewards(
            self.leader_player, {"items": [{"item_id": "item_starter_dagger", "quantity": 1}]}
        )
        self.assertIn("received", result)

    def test_grant_party_rewards_distributes_generated_item_data(self):
        dagger = ItemFactory.create_item_from_template("item_starter_dagger", self.server.world)
        generated = dagger.to_dict()
        result = self.server.grant_party_rewards(self.leader_player, {"generated_item_data": generated})
        self.assertIn("received", result)

    def test_grant_party_gold_zero_or_negative_is_a_no_op(self):
        self.assertEqual("", self.server.grant_party_gold(self.leader_player, 0))
        self.assertEqual("", self.server.grant_party_gold(self.leader_player, -5))


if __name__ == "__main__":
    unittest.main()
