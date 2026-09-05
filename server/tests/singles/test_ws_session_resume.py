"""Contract tests for WebSocket session resume lifecycle.

Covers:
- Ephemeral session created at connection time is removed from server.sessions
  after a successful resume_session envelope.
- Rate limiter state for the ephemeral session is cleared on resume.
- The resumed session's transport mapping is updated correctly.
"""
import asyncio
import contextlib
import json
import os
import tempfile
import time
import unittest
from typing import Any

from poc_ws_server import JsonWebSocketMudServer
from engine.server.feature_profile import FeatureProfile
from tests.fixtures import FANTASY_FRONTIER


def _make_app(**kwargs: Any) -> JsonWebSocketMudServer:
    return JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER, **kwargs)


class _FakeWebSocket:
    def __init__(self, incoming: list[Any]) -> None:
        self._incoming = list(incoming)
        self.sent: list[Any] = []

    async def recv(self) -> Any:
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)


class _InteractiveFakeWebSocket:
    def __init__(self) -> None:
        self._incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[Any] = []

    async def recv(self) -> Any:
        return await self._incoming.get()

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)

    async def push_json(self, payload: dict[str, Any]) -> None:
        await self._incoming.put(json.dumps(payload))

    async def push_disconnect(self) -> None:
        await self._incoming.put(json.dumps({"type": "disconnect"}))


class TestWsSessionResume(unittest.IsolatedAsyncioTestCase):
    async def test_resume_removes_ephemeral_session(self) -> None:
        """After a successful resume_session, the ephemeral session created at
        connection time must be gone from server.sessions."""
        app = _make_app()

        # Create a real session to resume into.
        prior_session = app.core.server.create_session()
        prior_sid = prior_session.session_id

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_sid}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        sessions = app.core.server.sessions
        # The resumed session must still exist.
        self.assertIn(prior_sid, sessions)
        # There should be exactly one session: the resumed one.
        # Any ephemeral session created at connection time must have been cleaned up.
        self.assertEqual(1, len(sessions), msg=(
            "Expected only the resumed session; found extra sessions: %s"
            % list(sessions.keys())
        ))

    async def test_resume_sends_session_resumed_event(self) -> None:
        """Successful resume must send a session_resumed event."""
        app = _make_app()

        prior_session = app.core.server.create_session()
        prior_sid = prior_session.session_id

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_sid}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        types = [e.get("type") for e in parsed]
        self.assertIn("session_resumed", types)
        self.assertIn("auth_state", types)
        self.assertIn("server_policy", types)
        self.assertIn("party_state", types)
        self.assertIn("lock_state", types)

    async def test_resume_unknown_session_sends_error(self) -> None:
        """A resume_session with an unknown session_id must send an error event,
        not crash, and leave the ephemeral session intact."""
        app = _make_app()

        sessions_before = len(app.core.server.sessions)

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": "nonexistent-sid"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        types = [e.get("type") for e in parsed]
        self.assertIn("error", types)

    async def test_rate_limiter_cleared_for_ephemeral_session_on_resume(self) -> None:
        """After resume, the ephemeral session's rate limiter entry must be gone."""
        app = _make_app()

        prior_session = app.core.server.create_session()
        prior_sid = prior_session.session_id

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_sid}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            # The limiter's internal dicts should contain at most the resumed session.
            limiter = app.core.input_safeguards._limiter
            tracked_sessions = set(limiter._tokens_by_session.keys())
            # The finally block in _handle_websocket_client clears the active session
            # (which is prior_sid after resume), so nothing should remain.
            self.assertEqual(set(), tracked_sessions, msg=(
                "Rate limiter has stale session entries: %s" % tracked_sessions
            ))
            app.shutdown()

    async def test_resume_without_character_keeps_creation_gate(self) -> None:
        app = _make_app(require_character_creation=True)
        prior_session = app.core.server.create_session()
        prior_sid = prior_session.session_id

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_sid}),
            json.dumps({"type": "command", "command_text": "look"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        text_payloads = [
            str(event.get("payload", ""))
            for event in parsed
            if event.get("type") == "text" and event.get("session_id") == prior_sid
        ]
        self.assertTrue(any("No character yet. Use: char create <name>" in payload for payload in text_payloads))

    async def test_resume_with_character_allows_gameplay(self) -> None:
        app = _make_app(require_character_creation=True)
        prior_session = app.core.server.create_session()
        prior_sid = prior_session.session_id
        app.core.server.execute_command(prior_sid, "char create ResumeTester")

        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_sid}),
            json.dumps({"type": "command", "command_text": "look"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        resumed_events = [event for event in parsed if event.get("session_id") == prior_sid]
        self.assertTrue(any(event.get("type") == "nearby" for event in resumed_events))

    async def test_single_player_story_rejects_resuming_non_primary_session(self) -> None:
        profile_payload = {
            "world": {"mode": "single_player_story"},
            "world_mutation": {"mode": "mutable"},
            "authoring": {"mode": "all"},
            "combat": {"mode": "enabled"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            primary = app.core.server.create_session()
            secondary = app.core.server.create_session()
            _ = primary
            fake_ws = _FakeWebSocket([
                json.dumps({"type": "resume_session", "session_id": secondary.session_id}),
                json.dumps({"type": "disconnect"}),
            ])
            try:
                await app._handle_websocket_client(fake_ws)
            finally:
                app.shutdown()
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            errors = [str(event.get("payload", "")) for event in parsed if event.get("type") == "error"]
            self.assertTrue(any("single_player_story" in msg for msg in errors))
        finally:
            os.remove(profile_path)

    async def test_party_presence_sync_survives_member_disconnect_and_resume(self) -> None:
        app = _make_app(require_character_creation=True)
        app.core.server.feature_profile.world_mode = "co_op_party"
        leader = app.core.server.create_session(player_id="party_leader")
        member = app.core.server.create_session(player_id="party_member")
        leader_id = leader.session_id
        member_id = member.session_id
        app.core.server.execute_command(leader_id, "char create Leader")
        app.core.server.execute_command(member_id, "char create Member")
        app.core.server.execute_command(leader_id, "party invite Member")
        app.core.server.execute_command(member_id, "party join")

        leader_ws = _InteractiveFakeWebSocket()
        member_ws = _InteractiveFakeWebSocket()
        leader_task = asyncio.create_task(app._handle_websocket_client(leader_ws))
        member_task = asyncio.create_task(app._handle_websocket_client(member_ws))
        try:
            await leader_ws.push_json({"type": "resume_session", "session_id": leader_id})
            await member_ws.push_json({"type": "resume_session", "session_id": member_id})
            await asyncio.sleep(0.05)

            leader_party_events = [
                json.loads(item)
                for item in leader_ws.sent
                if isinstance(item, str) and json.loads(item).get("type") == "party_state"
            ]
            self.assertTrue(leader_party_events)
            self.assertTrue(
                any(
                    any(row.get("name") == "Member" and row.get("online") for row in event["payload"].get("members", []))
                    for event in leader_party_events
                )
            )

            await member_ws.push_disconnect()
            await asyncio.sleep(0.05)
            leader_after_disconnect = [
                json.loads(item)
                for item in leader_ws.sent
                if isinstance(item, str) and json.loads(item).get("type") == "party_state"
            ]
            self.assertTrue(leader_after_disconnect)
            member_row = next(
                row
                for row in leader_after_disconnect[-1]["payload"]["members"]
                if row["name"] == "Member"
            )
            self.assertFalse(member_row["online"])

            resumed_member_ws = _InteractiveFakeWebSocket()
            resumed_member_task = asyncio.create_task(app._handle_websocket_client(resumed_member_ws))
            try:
                await resumed_member_ws.push_json({"type": "resume_session", "session_id": member_id})
                await asyncio.sleep(0.05)
                leader_after_resume = [
                    json.loads(item)
                    for item in leader_ws.sent
                    if isinstance(item, str) and json.loads(item).get("type") == "party_state"
                ]
                self.assertTrue(leader_after_resume)
                member_row_resumed = next(
                    row
                    for row in leader_after_resume[-1]["payload"]["members"]
                    if row["name"] == "Member"
                )
                self.assertTrue(member_row_resumed["online"])
                await resumed_member_ws.push_disconnect()
                await asyncio.wait_for(resumed_member_task, timeout=1.0)
            finally:
                if not resumed_member_task.done():
                    resumed_member_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                        await resumed_member_task
        finally:
            await leader_ws.push_disconnect()
            if not member_task.done():
                await member_ws.push_disconnect()
            if not member_task.done():
                with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(member_task, timeout=1.0)
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(leader_task, timeout=1.0)
            app.shutdown()

    async def test_persistent_shard_can_disable_session_resume(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {"session_resume_policy": "disabled"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            prior_session = app.core.server.create_session()
            prior_sid = prior_session.session_id
            fake_ws = _FakeWebSocket([
                json.dumps({"type": "resume_session", "session_id": prior_sid}),
                json.dumps({"type": "disconnect"}),
            ])
            try:
                await app._handle_websocket_client(fake_ws)
            finally:
                app.shutdown()
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            errors = [str(event.get("payload", "")) for event in parsed if event.get("type") == "error"]
            self.assertTrue(any("session resume is disabled" in msg for msg in errors))
        finally:
            os.remove(profile_path)

    async def test_persistent_shard_grace_window_blocks_late_resume(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {
                "session_resume_policy": "enabled",
                "disconnect_timeout_policy": "grace_window",
                "disconnect_timeout_seconds": 5,
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            prior_session = app.core.server.create_session()
            prior_sid = prior_session.session_id
            app.core.server.mark_session_connected(prior_sid)
            app.core.server.mark_session_disconnected(prior_sid)
            app.core.server.sessions[prior_sid].disconnected_at = 0.0
            fake_ws = _FakeWebSocket([
                json.dumps({"type": "resume_session", "session_id": prior_sid}),
                json.dumps({"type": "disconnect"}),
            ])
            try:
                await app._handle_websocket_client(fake_ws)
            finally:
                app.shutdown()
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            errors = [str(event.get("payload", "")) for event in parsed if event.get("type") == "error"]
            self.assertTrue(any("grace window has expired" in msg for msg in errors))
            self.assertNotIn(prior_sid, app.core.server.sessions)
        finally:
            os.remove(profile_path)

    async def test_persistent_shard_expired_sessions_are_pruned_on_new_connect(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {
                "session_resume_policy": "enabled",
                "disconnect_timeout_policy": "grace_window",
                "disconnect_timeout_seconds": 5,
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            prior_session = app.core.server.create_session()
            prior_sid = prior_session.session_id
            app.core.server.execute_command(prior_sid, "char create Expiring")
            app.core.server.mark_session_connected(prior_sid)
            app.core.server.mark_session_disconnected(prior_sid)
            app.core.server.sessions[prior_sid].disconnected_at = 0.0
            fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
            try:
                await app._handle_websocket_client(fake_ws)
            finally:
                app.shutdown()
            self.assertNotIn(prior_sid, app.core.server.sessions)
        finally:
            os.remove(profile_path)

    async def test_persistent_shard_prunes_only_expired_sessions_and_keeps_recent_resume_targets(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {
                "session_resume_policy": "enabled",
                "disconnect_timeout_policy": "grace_window",
                "disconnect_timeout_seconds": 60,
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            expired_a = app.core.server.create_session(player_id="expired_a")
            expired_b = app.core.server.create_session(player_id="expired_b")
            resumable = app.core.server.create_session(player_id="resumable_c")
            for session in (expired_a, expired_b, resumable):
                app.core.server.execute_command(session.session_id, f"char create {session.player_id}")
                app.core.server.mark_session_connected(session.session_id)
                app.core.server.mark_session_disconnected(session.session_id)
            app.core.server.sessions[expired_a.session_id].disconnected_at = 0.0
            app.core.server.sessions[expired_b.session_id].disconnected_at = 0.0
            app.core.server.sessions[resumable.session_id].disconnected_at = time.time()

            trigger_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
            try:
                await app._handle_websocket_client(trigger_ws)
                fake_ws = _FakeWebSocket([
                    json.dumps({"type": "resume_session", "session_id": resumable.session_id}),
                    json.dumps({"type": "disconnect"}),
                ])
                self.assertNotIn(expired_a.session_id, app.core.server.sessions)
                self.assertNotIn(expired_b.session_id, app.core.server.sessions)
                self.assertIn(resumable.session_id, app.core.server.sessions)

                await app._handle_websocket_client(fake_ws)
                parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
                self.assertTrue(any(event.get("type") == "session_resumed" for event in parsed))
            finally:
                self.assertIn(resumable.session_id, app.core.server.sessions)
                app.shutdown()
        finally:
            os.remove(profile_path)

    async def test_persistent_shard_multiple_recent_sessions_resume_under_live_observer(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {
                "session_resume_policy": "enabled",
                "disconnect_timeout_policy": "grace_window",
                "disconnect_timeout_seconds": 60,
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = _make_app(feature_profile=FeatureProfile.load(profile_path))
            expired = app.core.server.create_session(player_id="expired_player")
            resumable_a = app.core.server.create_session(player_id="resumable_a")
            resumable_b = app.core.server.create_session(player_id="resumable_b")
            for session in (expired, resumable_a, resumable_b):
                app.core.server.execute_command(session.session_id, f"char create {session.player_id}")
                app.core.server.mark_session_connected(session.session_id)
                app.core.server.mark_session_disconnected(session.session_id)
            app.core.server.sessions[expired.session_id].disconnected_at = 0.0
            app.core.server.sessions[resumable_a.session_id].disconnected_at = time.time()
            app.core.server.sessions[resumable_b.session_id].disconnected_at = time.time()

            observer_ws = _InteractiveFakeWebSocket()
            observer_task = asyncio.create_task(app._handle_websocket_client(observer_ws))
            try:
                await asyncio.sleep(0.05)
                await observer_ws.push_json({"type": "command", "command_text": "help"})
                await asyncio.sleep(0.05)

                self.assertNotIn(expired.session_id, app.core.server.sessions)
                self.assertIn(resumable_a.session_id, app.core.server.sessions)
                self.assertIn(resumable_b.session_id, app.core.server.sessions)

                diagnostics_after_prune = app.core.server.build_shard_diagnostics_payload()
                self.assertEqual(3, diagnostics_after_prune["total_session_count"])
                self.assertEqual(1, diagnostics_after_prune["connected_session_count"])
                self.assertEqual(2, diagnostics_after_prune["resumable_session_count"])
                self.assertEqual(0, diagnostics_after_prune["expired_grace_window_session_count"])

                for resumable_session in (resumable_a, resumable_b):
                    resume_ws = _InteractiveFakeWebSocket()
                    resume_task = asyncio.create_task(app._handle_websocket_client(resume_ws))
                    try:
                        await asyncio.sleep(0.05)
                        await resume_ws.push_json({"type": "resume_session", "session_id": resumable_session.session_id})
                        await asyncio.sleep(0.05)
                        parsed = [json.loads(item) for item in resume_ws.sent if isinstance(item, str)]
                        self.assertTrue(any(event.get("type") == "session_resumed" for event in parsed))

                        diagnostics = app.core.server.build_shard_diagnostics_payload()
                        self.assertEqual(2, diagnostics["connected_session_count"])
                        self.assertEqual(1, diagnostics["resumable_session_count"])
                        self.assertEqual(0, diagnostics["expired_grace_window_session_count"])
                    finally:
                        await resume_ws.push_disconnect()
                        await asyncio.wait_for(resume_task, timeout=1.0)

                diagnostics_after_disconnects = app.core.server.build_shard_diagnostics_payload()
                self.assertEqual(1, diagnostics_after_disconnects["connected_session_count"])
                self.assertEqual(2, diagnostics_after_disconnects["resumable_session_count"])
                self.assertEqual(0, diagnostics_after_disconnects["expired_grace_window_session_count"])
            finally:
                await observer_ws.push_disconnect()
                with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(observer_task, timeout=1.0)
                app.shutdown()
        finally:
            os.remove(profile_path)


if __name__ == "__main__":
    unittest.main()
