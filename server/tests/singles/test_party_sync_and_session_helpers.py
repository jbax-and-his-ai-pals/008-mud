import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestSessionConnectionHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_mark_connected_on_unknown_session_is_a_no_op(self):
        self.server.mark_session_connected("not_a_real_session")  # must not raise

    def test_mark_disconnected_on_unknown_session_is_a_no_op(self):
        self.server.mark_session_disconnected("not_a_real_session")  # must not raise

    def test_mark_connected_sets_flag_and_clears_disconnect_timestamp(self):
        session = self.server.create_session()
        self.server.mark_session_disconnected(session.session_id)
        self.assertIsNotNone(session.disconnected_at)
        self.server.mark_session_connected(session.session_id)
        self.assertTrue(session.connected)
        self.assertIsNone(session.disconnected_at)

    def test_display_name_falls_back_to_player_id_when_no_player_loaded(self):
        name = self.server._display_name_for_player_id("nonexistent_player_id")
        self.assertEqual("nonexistent_player_id", name)


class TestFindPlayerIdByName(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.a = self.server.create_session()
        self.b = self.server.create_session()
        self.server.execute_command(self.a.session_id, "char create Alice")
        self.server.execute_command(self.b.session_id, "char create Bob")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_empty_name_is_rejected(self):
        player_id, error = self.server._find_player_id_by_name("   ")
        self.assertEqual("", player_id)
        self.assertIn("Missing player name", error)

    def test_no_match_is_reported(self):
        player_id, error = self.server._find_player_id_by_name("Nobody")
        self.assertEqual("", player_id)
        self.assertIn("No player found", error)

    def test_unique_match_by_name(self):
        player_id, error = self.server._find_player_id_by_name("alice")
        self.assertEqual("", error)
        self.assertEqual(str(self.a.player_id), player_id)

    def test_multiple_matches_are_reported(self):
        # Force a name collision directly on player state.
        alice = self.server.get_player_for_session(self.a.session_id)
        bob = self.server.get_player_for_session(self.b.session_id)
        bob.name = alice.name
        player_id, error = self.server._find_player_id_by_name(alice.name)
        self.assertEqual("", player_id)
        self.assertIn("Multiple players match", error)


class TestPartyQuestSyncGuardBranches(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.server.feature_profile.world_mode = "co_op_party"
        self.leader = self.server.create_session(player_id="leader_p")
        self.member = self.server.create_session(player_id="member_p")
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.leader_player = self.server.get_player_for_session(self.leader.session_id)
        self.member_player = self.server.get_player_for_session(self.member.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_mirror_acceptance_is_a_no_op_outside_co_op_party_mode(self):
        self.server.feature_profile.world_mode = "single_player_story"
        events = self.server.mirror_party_quest_acceptance(self.leader_player, ["q1"])
        self.assertEqual([], events)

    def test_mirror_acceptance_is_a_no_op_when_policy_is_not_mirror_all(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "leader_driven"}}
        events = self.server.mirror_party_quest_acceptance(self.leader_player, ["q1"])
        self.assertEqual([], events)

    def test_mirror_acceptance_is_a_no_op_with_no_party(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "mirror_all"}}
        events = self.server.mirror_party_quest_acceptance(self.leader_player, ["q1"])
        self.assertEqual([], events)

    def test_completion_sync_is_a_no_op_outside_co_op_party_mode(self):
        self.server.feature_profile.world_mode = "single_player_story"
        events = self.server.sync_party_quest_completion(self.leader_player, {"instance_id": "q1"})
        self.assertEqual([], events)

    def test_completion_sync_is_a_no_op_when_policy_is_not_mirror_all(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "leader_driven"}}
        events = self.server.sync_party_quest_completion(self.leader_player, {"instance_id": "q1"})
        self.assertEqual([], events)

    def test_completion_sync_is_a_no_op_with_no_party(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "mirror_all"}}
        events = self.server.sync_party_quest_completion(self.leader_player, {"instance_id": "q1"})
        self.assertEqual([], events)

    def test_completion_sync_is_a_no_op_with_blank_root_id(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "mirror_all"}}
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.sync_party_quest_completion(self.leader_player, {})
        self.assertEqual([], events)

    def test_completion_sync_skips_members_without_a_mirrored_quest(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "mirror_all"}}
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        # Member has no active quests at all, so the mirrored-id lookup finds nothing.
        events = self.server.sync_party_quest_completion(
            self.leader_player, {"instance_id": "root_quest", "party_shared_root_id": "root_quest"}
        )
        self.assertEqual([], events)

    def test_mirror_acceptance_skips_quest_ids_missing_from_active(self):
        self.server.feature_profile.raw = {"party": {"shared_quest_policy": "mirror_all"}}
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.mirror_party_quest_acceptance(self.leader_player, ["not_actually_active"])
        self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
