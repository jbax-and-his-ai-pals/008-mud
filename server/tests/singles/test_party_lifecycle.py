import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestPartyLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.server.feature_profile.world_mode = "co_op_party"
        self.leader = self.server.create_session()
        self.member = self.server.create_session()
        self.third = self.server.create_session()
        self.fourth = self.server.create_session()
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.mark_session_connected(self.third.session_id)
        self.server.mark_session_connected(self.fourth.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.server.execute_command(self.third.session_id, "char create Third")
        self.server.execute_command(self.fourth.session_id, "char create Fourth")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_invite_join_and_state_sync(self) -> None:
        invite_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any(event.get("type") == "party_state" for event in invite_events))
        self.assertTrue(
            any(
                event.get("session_id") == self.member.session_id
                and "invited you to join their party" in str(event.get("payload", "")).lower()
                for event in invite_events
                if event.get("type") == "text"
            )
        )

        join_events = self.server.execute_command(self.member.session_id, "party join")
        self.assertTrue(any(event.get("type") == "party_state" for event in join_events))

        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertTrue(leader_state["in_party"])
        self.assertEqual(leader_state["party_id"], member_state["party_id"])
        self.assertEqual(2, len(leader_state["members"]))
        self.assertEqual("Leader", leader_state["leader_name"])

    def test_leader_transfer_and_disband(self) -> None:
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")

        transfer_events = self.server.execute_command(self.leader.session_id, "party leader Member")
        self.assertTrue(
            any("leadership transferred" in str(event.get("payload", "")).lower() for event in transfer_events)
        )
        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual("Member", member_state["leader_name"])

        disband_events = self.server.execute_command(self.member.session_id, "party disband")
        self.assertTrue(any("party disbanded" in str(event.get("payload", "")).lower() for event in disband_events))
        self.assertFalse(self.server.build_party_state_payload(self.leader.session_id)["in_party"])
        self.assertFalse(self.server.build_party_state_payload(self.member.session_id)["in_party"])

    def test_invite_decline_and_cancel(self) -> None:
        invite_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any(event.get("type") == "party_state" for event in invite_events))
        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual(1, len(member_state["pending_invites"]))

        decline_events = self.server.execute_command(self.member.session_id, "party decline")
        self.assertTrue(any("declined" in str(event.get("payload", "")).lower() for event in decline_events))
        member_state_after_decline = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual([], member_state_after_decline["pending_invites"])

        self.server.execute_command(self.leader.session_id, "party invite Third")
        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        self.assertEqual("Third", leader_state["outgoing_invites"][0]["name"])

        cancel_events = self.server.execute_command(self.leader.session_id, "party cancel Third")
        self.assertTrue(any("cancelled invite" in str(event.get("payload", "")).lower() for event in cancel_events))
        leader_state_after_cancel = self.server.build_party_state_payload(self.leader.session_id)
        self.assertEqual([], leader_state_after_cancel["outgoing_invites"])
        third_state = self.server.build_party_state_payload(self.third.session_id)
        self.assertEqual([], third_state["pending_invites"])

    def test_party_commands_are_mode_gated(self) -> None:
        self.server.feature_profile.world_mode = "persistent_shard"
        events = self.server.execute_command(self.leader.session_id, "party status")
        payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("co_op_party" in payload for payload in payloads))

    def test_party_presence_tracks_connected_sessions(self) -> None:
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")

        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        member_row = next(member for member in leader_state["members"] if member["name"] == "Member")
        self.assertTrue(member_row["online"])

        self.server.mark_session_disconnected(self.member.session_id)
        leader_state_after_disconnect = self.server.build_party_state_payload(self.leader.session_id)
        member_row_after_disconnect = next(
            member for member in leader_state_after_disconnect["members"] if member["name"] == "Member"
        )
        self.assertFalse(member_row_after_disconnect["online"])

        self.server.mark_session_connected(self.member.session_id)
        leader_state_after_reconnect = self.server.build_party_state_payload(self.leader.session_id)
        member_row_after_reconnect = next(
            member for member in leader_state_after_reconnect["members"] if member["name"] == "Member"
        )
        self.assertTrue(member_row_after_reconnect["online"])

    def test_competing_invite_replaces_previous_pending_invite(self) -> None:
        first_invite_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any("invited you to join their party" in str(event.get("payload", "")).lower() for event in first_invite_events))

        replacement_events = self.server.execute_command(self.third.session_id, "party invite Member")
        self.assertTrue(
            any("replaced their pending invite from leader" in str(event.get("payload", "")).lower() for event in replacement_events)
        )
        self.assertTrue(
            any(
                event.get("session_id") == self.member.session_id
                and "replacing your pending invite from leader" in str(event.get("payload", "")).lower()
                for event in replacement_events
                if event.get("type") == "text"
            )
        )
        self.assertTrue(
            any(
                event.get("session_id") == self.leader.session_id
                and "was replaced by third's party invite" in str(event.get("payload", "")).lower()
                for event in replacement_events
                if event.get("type") == "text"
            )
        )

        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual("Third", member_state["pending_invites"][0]["leader_name"])
        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        third_state = self.server.build_party_state_payload(self.third.session_id)
        self.assertEqual([], leader_state["outgoing_invites"])
        self.assertEqual("Member", third_state["outgoing_invites"][0]["name"])

    def test_duplicate_invite_from_same_party_is_rejected(self) -> None:
        self.server.execute_command(self.leader.session_id, "party invite Member")
        duplicate_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(
            any("already has a pending invite from your party" in str(event.get("payload", "")).lower() for event in duplicate_events)
        )
        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        self.assertEqual(1, len(leader_state["outgoing_invites"]))

    def test_offline_loaded_player_invite_persists_until_reconnect(self) -> None:
        self.server.mark_session_disconnected(self.member.session_id)
        invite_events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any("invited member to the party" in str(event.get("payload", "")).lower() for event in invite_events))
        member_state = self.server.build_party_state_payload(self.member.session_id)
        self.assertEqual("Leader", member_state["pending_invites"][0]["leader_name"])

        self.server.mark_session_connected(self.member.session_id)
        join_events = self.server.execute_command(self.member.session_id, "party join")
        self.assertTrue(any("you joined leader's party" in str(event.get("payload", "")).lower() for event in join_events))
        leader_state = self.server.build_party_state_payload(self.leader.session_id)
        self.assertEqual(2, len(leader_state["members"]))

    def test_offline_invites_can_be_disabled_by_policy(self) -> None:
        self.server.feature_profile.raw = {"party": {"offline_invites_supported": False}}
        self.server.mark_session_disconnected(self.member.session_id)
        events = self.server.execute_command(self.leader.session_id, "party invite Member")
        self.assertTrue(any("offline party invites are disabled by server policy" in str(event.get("payload", "")).lower() for event in events))


if __name__ == "__main__":
    unittest.main()
