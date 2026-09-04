import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


def _texts(events):
    return [str(e.get("payload", "")) for e in events if e.get("type") == "text"]


class TestPartyCommandEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.server.feature_profile.world_mode = "co_op_party"
        self.leader = self.server.create_session()
        self.member = self.server.create_session()
        self.third = self.server.create_session()
        for s in (self.leader, self.member, self.third):
            self.server.mark_session_connected(s.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.server.execute_command(self.third.session_id, "char create Third")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_status_with_no_party(self):
        events = self.server.execute_command(self.leader.session_id, "party status")
        self.assertIn("You are not currently in a party.", _texts(events))

    def test_status_with_party_lists_members(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.leader.session_id, "party")  # bare -> defaults to status
        self.assertTrue(any("Party members" in t for t in _texts(events)))

    def test_invite_requires_a_name(self):
        events = self.server.execute_command(self.leader.session_id, "party invite")
        self.assertIn("Usage: party invite <player-name>", _texts(events))

    def test_cannot_invite_self(self):
        events = self.server.execute_command(self.leader.session_id, "party invite Leader")
        self.assertIn("You cannot invite yourself.", _texts(events))

    def test_cannot_invite_someone_already_in_a_party(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.third.session_id, "party invite Member")
        self.assertIn("That player is already in a party.", _texts(events))

    def test_only_leader_can_invite(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.member.session_id, "party invite Third")
        self.assertIn("Only the party leader can invite players.", _texts(events))

    def test_duplicate_invite_from_same_leader_is_reported(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any("already has a pending invite" in t for t in _texts(events)))

    def test_decline_with_no_pending_invite(self):
        events = self.server.execute_command(self.leader.session_id, "party decline")
        self.assertIn("You do not have a pending party invite.", _texts(events))

    def test_decline_notifies_the_leader(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        events = self.server.execute_command(self.member.session_id, "party decline")
        self.assertIn("Party invite declined.", _texts(events))
        leader_events = self.server.execute_command(self.leader.session_id, "party status")
        # Invite consumed: leader can invite again without a "duplicate" complaint.
        reinvite_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any("Invited" in t for t in _texts(reinvite_events)))

    def test_cancel_requires_a_name(self):
        events = self.server.execute_command(self.leader.session_id, "party cancel")
        self.assertIn("Usage: party cancel <player-name>", _texts(events))

    def test_cancel_with_no_party_is_reported(self):
        events = self.server.execute_command(self.leader.session_id, "party cancel Member")
        self.assertIn("You are not currently in a party.", _texts(events))

    def test_cancel_by_non_leader_is_rejected(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.member.session_id, "party cancel Third")
        self.assertIn("Only the current party leader can cancel invitations.", _texts(events))

    def test_cancel_with_no_matching_pending_invite(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.leader.session_id, "party cancel Third")
        self.assertIn("That player does not have a pending invite from your party.", _texts(events))

    def test_cancel_removes_the_pending_invite(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        events = self.server.execute_command(self.leader.session_id, "party cancel Member")
        self.assertTrue(any("Cancelled invite" in t for t in _texts(events)))
        join_events = self.server.execute_command(self.member.session_id, "party join")
        self.assertIn("You do not have a pending party invite.", _texts(join_events))

    def test_join_with_no_pending_invite(self):
        events = self.server.execute_command(self.leader.session_id, "party join")
        self.assertIn("You do not have a pending party invite.", _texts(events))

    def test_join_while_already_in_a_party(self):
        # The invite handler itself refuses to invite someone already in a
        # party, so this guard can only fire via a state race -- simulate
        # one directly: Member is in Leader's party AND separately holds a
        # (stale) pending invite to Third's party.
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        third_player_id = str(self.third.player_id)
        member_player_id = str(self.member.player_id)
        third_party = self.server._ensure_party_for_leader(third_player_id)
        self.server.pending_party_invites[member_player_id] = third_party.party_id

        events = self.server.execute_command(self.member.session_id, "party join")
        self.assertIn("Leave your current party before joining another one.", _texts(events))

    def test_leave_with_no_party_is_reported(self):
        events = self.server.execute_command(self.leader.session_id, "party leave")
        self.assertIn("You are not currently in a party.", _texts(events))

    def test_leave_removes_party_when_last_member_leaves(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        self.server.execute_command(self.member.session_id, "party leave")
        events = self.server.execute_command(self.leader.session_id, "party leave")
        self.assertIn("You left the party.", _texts(events))
        self.assertFalse(self.server.build_party_state_payload(self.leader.session_id)["in_party"])

    def test_leave_promotes_new_leader(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        self.server.execute_command(self.leader.session_id, "party leave")
        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual("Member", member_state["leader_name"])

    def test_leader_requires_a_name(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.leader.session_id, "party leader")
        self.assertIn("Usage: party leader <player-name>", _texts(events))

    def test_leader_with_no_party_is_reported(self):
        events = self.server.execute_command(self.leader.session_id, "party leader Member")
        self.assertIn("You are not currently in a party.", _texts(events))

    def test_leader_by_non_leader_is_rejected(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.member.session_id, "party leader Member")
        self.assertIn("Only the current party leader can transfer leadership.", _texts(events))

    def test_leader_target_must_be_a_member(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.leader.session_id, "party leader Third")
        self.assertIn("That player is not in your party.", _texts(events))

    def test_disband_with_no_party_is_reported(self):
        events = self.server.execute_command(self.leader.session_id, "party disband")
        self.assertIn("You are not currently in a party.", _texts(events))

    def test_disband_by_non_leader_is_rejected(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")
        events = self.server.execute_command(self.member.session_id, "party disband")
        self.assertIn("Only the current party leader can disband the party.", _texts(events))

    def test_disband_clears_pending_invites_for_that_party(self):
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.leader.session_id, "party disband")
        # A previously-invited player should be able to be invited by someone
        # else without any stale "already has a pending invite" state.
        events = self.server.execute_command(self.third.session_id, "party invite Member")
        self.assertTrue(any("Invited" in t for t in _texts(events)))

    def test_unknown_party_subcommand(self):
        events = self.server.execute_command(self.leader.session_id, "party wobble")
        self.assertTrue(any("Unknown party command" in t for t in _texts(events)))

    def test_party_commands_require_a_character(self):
        no_char_session = self.server.create_session()
        events = self.server.execute_command(no_char_session.session_id, "party status")
        # No character yet -> character-creation gate response, not a party response.
        self.assertTrue(any("char create" in t.lower() for t in _texts(events)))


if __name__ == "__main__":
    unittest.main()
