import asyncio
import json
import os
import tempfile
import time
import unittest
from typing import Any

from poc_server import JsonLineMudServer as _JsonLineMudServer
from engine.server.feature_profile import FeatureProfile
from tests.fixtures import FANTASY_FRONTIER


class JsonLineMudServer(_JsonLineMudServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, content_set_path=FANTASY_FRONTIER, **kwargs)


class TestTcpSessionResume(unittest.IsolatedAsyncioTestCase):
    async def _read_available_events(self, reader: asyncio.StreamReader, max_events: int = 12) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for _ in range(max_events):
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.1)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            events.append(json.loads(line.decode("utf-8")))
        return events

    async def test_resume_unknown_session_sends_error(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json")
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write((json.dumps({"type": "resume_session", "session_id": "missing-session"}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            self.assertTrue(any(ev.get("type") == "error" for ev in events))
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_resume_rebinds_session_and_emits_state_bundle(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json")
        existing = app.server.create_session()
        existing_id = existing.session_id
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            ephemeral_id = str(hello.get("session_id"))
            await reader.readline()
            await reader.readline()

            writer.write((json.dumps({"type": "resume_session", "session_id": existing_id}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            types = [ev.get("type") for ev in events]
            self.assertIn("session_resumed", types)
            self.assertIn("auth_state", types)
            self.assertIn("server_policy", types)
            self.assertIn("party_state", types)
            self.assertIn("lock_state", types)
            self.assertNotIn(ephemeral_id, app.server.sessions)
            self.assertIn(existing_id, app.server.sessions)
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_resume_without_character_keeps_creation_gate(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", require_character_creation=True)
        existing = app.server.create_session()
        existing_id = existing.session_id
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write((json.dumps({"type": "resume_session", "session_id": existing_id}) + "\n").encode("utf-8"))
            await writer.drain()
            await self._read_available_events(reader)
            writer.write(b"look\n")
            await writer.drain()
            look_events = await self._read_available_events(reader)
            text_payloads = [str(ev.get("payload", "")) for ev in look_events if ev.get("type") == "text"]
            self.assertTrue(any("No character yet. Use: char create <name>" in payload for payload in text_payloads))
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_resume_with_character_allows_gameplay(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", require_character_creation=True)
        existing = app.server.create_session()
        existing_id = existing.session_id
        app.server.execute_command(existing_id, "char create ResumeTester")
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write((json.dumps({"type": "resume_session", "session_id": existing_id}) + "\n").encode("utf-8"))
            await writer.drain()
            await self._read_available_events(reader)
            writer.write(b"look\n")
            await writer.drain()
            look_events = await self._read_available_events(reader)
            self.assertTrue(any(ev.get("type") == "nearby" and ev.get("session_id") == existing_id for ev in look_events))
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            primary = app.server.create_session()
            secondary = app.server.create_session()
            _ = primary
            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await reader.readline()
                await reader.readline()
                await reader.readline()

                writer.write((json.dumps({"type": "resume_session", "session_id": secondary.session_id}) + "\n").encode("utf-8"))
                await writer.drain()
                events = await self._read_available_events(reader)
                errors = [str(ev.get("payload", "")) for ev in events if ev.get("type") == "error"]
                self.assertTrue(any("single_player_story" in msg for msg in errors))
            finally:
                writer.write(b'{"type":"disconnect"}\n')
                await writer.drain()
                await reader.readline()
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
        finally:
            os.remove(profile_path)

    async def test_party_presence_sync_survives_member_disconnect_and_resume(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", require_character_creation=True)
        app.server.feature_profile.world_mode = "co_op_party"
        leader = app.server.create_session(player_id="party_leader")
        member = app.server.create_session(player_id="party_member")
        leader_id = leader.session_id
        member_id = member.session_id
        app.server.execute_command(leader_id, "char create Leader")
        app.server.execute_command(member_id, "char create Member")
        app.server.execute_command(leader_id, "party invite Member")
        app.server.execute_command(member_id, "party join")

        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        leader_reader, leader_writer = await asyncio.open_connection(host, port)
        member_reader, member_writer = await asyncio.open_connection(host, port)
        try:
            for _ in range(3):
                await leader_reader.readline()
            for _ in range(3):
                await member_reader.readline()

            leader_writer.write((json.dumps({"type": "resume_session", "session_id": leader_id}) + "\n").encode("utf-8"))
            await leader_writer.drain()
            await self._read_available_events(leader_reader)

            member_writer.write((json.dumps({"type": "resume_session", "session_id": member_id}) + "\n").encode("utf-8"))
            await member_writer.drain()
            await self._read_available_events(member_reader)
            leader_presence_events = await self._read_available_events(leader_reader)
            self.assertTrue(any(ev.get("type") == "party_state" for ev in leader_presence_events))

            member_writer.write(b'{"type":"disconnect"}\n')
            await member_writer.drain()
            await member_reader.readline()
            leader_after_disconnect = await self._read_available_events(leader_reader)
            disconnected_states = [ev for ev in leader_after_disconnect if ev.get("type") == "party_state"]
            self.assertTrue(disconnected_states)
            member_row = next(
                row for row in disconnected_states[-1]["payload"]["members"] if row["name"] == "Member"
            )
            self.assertFalse(member_row["online"])

            member_writer.close()
            await member_writer.wait_closed()

            resumed_member_reader, resumed_member_writer = await asyncio.open_connection(host, port)
            try:
                for _ in range(3):
                    await resumed_member_reader.readline()
                resumed_member_writer.write((json.dumps({"type": "resume_session", "session_id": member_id}) + "\n").encode("utf-8"))
                await resumed_member_writer.drain()
                await self._read_available_events(resumed_member_reader)
                leader_after_resume = await self._read_available_events(leader_reader)
                resumed_states = [ev for ev in leader_after_resume if ev.get("type") == "party_state"]
                self.assertTrue(resumed_states)
                member_row_resumed = next(
                    row for row in resumed_states[-1]["payload"]["members"] if row["name"] == "Member"
                )
                self.assertTrue(member_row_resumed["online"])
            finally:
                resumed_member_writer.write(b'{"type":"disconnect"}\n')
                await resumed_member_writer.drain()
                await resumed_member_reader.readline()
                resumed_member_writer.close()
                await resumed_member_writer.wait_closed()
        finally:
            leader_writer.write(b'{"type":"disconnect"}\n')
            await leader_writer.drain()
            await leader_reader.readline()
            leader_writer.close()
            await leader_writer.wait_closed()
            server.close()
            await server.wait_closed()
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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            existing = app.server.create_session()
            existing_id = existing.session_id
            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await reader.readline()
                await reader.readline()
                await reader.readline()
                writer.write((json.dumps({"type": "resume_session", "session_id": existing_id}) + "\n").encode("utf-8"))
                await writer.drain()
                events = await self._read_available_events(reader)
                errors = [str(ev.get("payload", "")) for ev in events if ev.get("type") == "error"]
                self.assertTrue(any("session resume is disabled" in msg for msg in errors))
            finally:
                writer.write(b'{"type":"disconnect"}\n')
                await writer.drain()
                await reader.readline()
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            existing = app.server.create_session()
            existing_id = existing.session_id
            app.server.mark_session_connected(existing_id)
            app.server.mark_session_disconnected(existing_id)
            app.server.sessions[existing_id].disconnected_at = 0.0
            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await reader.readline()
                await reader.readline()
                await reader.readline()
                writer.write((json.dumps({"type": "resume_session", "session_id": existing_id}) + "\n").encode("utf-8"))
                await writer.drain()
                events = await self._read_available_events(reader)
                errors = [str(ev.get("payload", "")) for ev in events if ev.get("type") == "error"]
                self.assertTrue(any("grace window has expired" in msg for msg in errors))
                self.assertNotIn(existing_id, app.server.sessions)
            finally:
                writer.write(b'{"type":"disconnect"}\n')
                await writer.drain()
                await reader.readline()
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            expired = app.server.create_session()
            expired_id = expired.session_id
            app.server.execute_command(expired_id, "char create Expiring")
            app.server.mark_session_connected(expired_id)
            app.server.mark_session_disconnected(expired_id)
            app.server.sessions[expired_id].disconnected_at = 0.0
            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await reader.readline()
                await reader.readline()
                await reader.readline()
                writer.write(b'{"type":"disconnect"}\n')
                await writer.drain()
                await reader.readline()
                self.assertNotIn(expired_id, app.server.sessions)
            finally:
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            expired_a = app.server.create_session(player_id="expired_a")
            expired_b = app.server.create_session(player_id="expired_b")
            resumable = app.server.create_session(player_id="resumable_c")
            for session in (expired_a, expired_b, resumable):
                app.server.execute_command(session.session_id, f"char create {session.player_id}")
                app.server.mark_session_connected(session.session_id)
                app.server.mark_session_disconnected(session.session_id)
            app.server.sessions[expired_a.session_id].disconnected_at = 0.0
            app.server.sessions[expired_b.session_id].disconnected_at = 0.0
            app.server.sessions[resumable.session_id].disconnected_at = time.time()

            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await reader.readline()
                await reader.readline()
                await reader.readline()
                writer.write(b'{"type":"disconnect"}\n')
                await writer.drain()
                await reader.readline()

                self.assertNotIn(expired_a.session_id, app.server.sessions)
                self.assertNotIn(expired_b.session_id, app.server.sessions)
                self.assertIn(resumable.session_id, app.server.sessions)

                resume_reader, resume_writer = await asyncio.open_connection(host, port)
                try:
                    await resume_reader.readline()
                    await resume_reader.readline()
                    await resume_reader.readline()
                    resume_writer.write((json.dumps({"type": "resume_session", "session_id": resumable.session_id}) + "\n").encode("utf-8"))
                    await resume_writer.drain()
                    events = await self._read_available_events(resume_reader)
                    self.assertTrue(any(ev.get("type") == "session_resumed" for ev in events))
                    self.assertTrue(app.server.sessions[resumable.session_id].connected)
                finally:
                    resume_writer.write(b'{"type":"disconnect"}\n')
                    await resume_writer.drain()
                    await resume_reader.readline()
                    resume_writer.close()
                    await resume_writer.wait_closed()
            finally:
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
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
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile=FeatureProfile.load(profile_path))
            expired = app.server.create_session(player_id="expired_player")
            resumable_a = app.server.create_session(player_id="resumable_a")
            resumable_b = app.server.create_session(player_id="resumable_b")
            for session in (expired, resumable_a, resumable_b):
                app.server.execute_command(session.session_id, f"char create {session.player_id}")
                app.server.mark_session_connected(session.session_id)
                app.server.mark_session_disconnected(session.session_id)
            app.server.sessions[expired.session_id].disconnected_at = 0.0
            app.server.sessions[resumable_a.session_id].disconnected_at = time.time()
            app.server.sessions[resumable_b.session_id].disconnected_at = time.time()

            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            observer_reader, observer_writer = await asyncio.open_connection(host, port)
            try:
                await observer_reader.readline()
                await observer_reader.readline()
                await observer_reader.readline()

                observer_writer.write(b"help\n")
                await observer_writer.drain()
                await self._read_available_events(observer_reader)

                self.assertNotIn(expired.session_id, app.server.sessions)
                self.assertIn(resumable_a.session_id, app.server.sessions)
                self.assertIn(resumable_b.session_id, app.server.sessions)

                diagnostics_after_prune = app.server.build_shard_diagnostics_payload()
                self.assertEqual(3, diagnostics_after_prune["total_session_count"])
                self.assertEqual(1, diagnostics_after_prune["connected_session_count"])
                self.assertEqual(2, diagnostics_after_prune["resumable_session_count"])
                self.assertEqual(0, diagnostics_after_prune["expired_grace_window_session_count"])

                for resumable_session in (resumable_a, resumable_b):
                    resume_reader, resume_writer = await asyncio.open_connection(host, port)
                    try:
                        await resume_reader.readline()
                        await resume_reader.readline()
                        await resume_reader.readline()
                        resume_writer.write(
                            (json.dumps({"type": "resume_session", "session_id": resumable_session.session_id}) + "\n").encode("utf-8")
                        )
                        await resume_writer.drain()
                        resume_events = await self._read_available_events(resume_reader)
                        self.assertTrue(any(ev.get("type") == "session_resumed" for ev in resume_events))

                        diagnostics = app.server.build_shard_diagnostics_payload()
                        self.assertEqual(2, diagnostics["connected_session_count"])
                        self.assertEqual(1, diagnostics["resumable_session_count"])
                        self.assertEqual(0, diagnostics["expired_grace_window_session_count"])
                    finally:
                        resume_writer.write(b'{"type":"disconnect"}\n')
                        await resume_writer.drain()
                        await resume_reader.readline()
                        resume_writer.close()
                        await resume_writer.wait_closed()

                diagnostics_after_disconnects = app.server.build_shard_diagnostics_payload()
                self.assertEqual(1, diagnostics_after_disconnects["connected_session_count"])
                self.assertEqual(2, diagnostics_after_disconnects["resumable_session_count"])
                self.assertEqual(0, diagnostics_after_disconnects["expired_grace_window_session_count"])
            finally:
                observer_writer.write(b'{"type":"disconnect"}\n')
                await observer_writer.drain()
                await observer_reader.readline()
                observer_writer.close()
                await observer_writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
        finally:
            os.remove(profile_path)


if __name__ == "__main__":
    unittest.main()
