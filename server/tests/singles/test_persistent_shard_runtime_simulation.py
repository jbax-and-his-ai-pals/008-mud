import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class _ProbeWorldEffectsProvider:
    mode = "builtin"
    provider_id = "test.probe.world_effects"

    def __init__(self) -> None:
        self.tick_calls = 0

    def tick(self, server_ref, session_id: str):
        self.tick_calls += 1
        return [
            server_ref._event(
                "world_state",
                session_id,
                {
                    "system": "world_effects",
                    "provider": self.provider_id,
                    "tick_calls": self.tick_calls,
                },
            )
        ]


class TestPersistentShardRuntimeSimulation(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, tick_rate_hz=10.0)
        self.server.feature_profile.world_mode = "persistent_shard"

        self.probe_provider = _ProbeWorldEffectsProvider()
        self.server.feature_profile.world_effects_mode = "custom"
        self.server.feature_profile.raw["world_effects"] = {
            "mode": "custom",
            "provider_id": self.probe_provider.provider_id,
        }
        self.server.register_world_effects_provider(self.probe_provider.provider_id, self.probe_provider)

        self.session_a = self.server.create_session(player_id="shard_a")
        self.session_b = self.server.create_session(player_id="shard_b")
        self.server.mark_session_connected(self.session_a.session_id)
        self.server.mark_session_connected(self.session_b.session_id)

        self.server.execute_command(self.session_a.session_id, "char create ShardA")
        self.server.execute_command(self.session_b.session_id, "char create ShardB")

    def tearDown(self) -> None:
        self.server.shutdown()

    def _drain_tick(self, session_id: str) -> list[dict]:
        events = self.server.tick(session_id, dt=1.0)
        events.extend(self.server._flush_background_batch(session_id))
        return events

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    def test_shard_runtime_modes_hold_under_multisession_flow(self) -> None:
        normal_events = self._drain_tick(self.session_a.session_id)
        self.assertTrue(any(event.get("type") == "world_state" for event in normal_events))
        self.assertEqual(1, self.probe_provider.tick_calls)

        ok, _message = self.server.set_shard_runtime_state("drain", "Queue shutdown")
        self.assertTrue(ok)

        drain_command_events = self.server.execute_command(self.session_a.session_id, "look")
        drain_text = self._text_payloads(drain_command_events)
        self.assertFalse(any("temporarily frozen" in text.lower() for text in drain_text))
        self.assertFalse(any("temporarily unavailable" in text.lower() for text in drain_text))

        newcomer = self.server.create_session(player_id="shard_new")
        self.server.mark_session_connected(newcomer.session_id)
        newcomer_events = self.server.execute_command(newcomer.session_id, "char create LateJoiner")
        newcomer_text = self._text_payloads(newcomer_events)
        self.assertTrue(any("draining" in text.lower() for text in newcomer_text))
        self.assertIsNone(self.server.get_player_for_session(newcomer.session_id))

        drain_tick_events = self._drain_tick(self.session_b.session_id)
        self.assertTrue(any(event.get("type") == "world_state" for event in drain_tick_events))
        self.assertEqual(3, self.probe_provider.tick_calls)

        ok, _message = self.server.set_shard_runtime_state("freeze", "Investigating simulation drift")
        self.assertTrue(ok)

        freeze_a = self.server.execute_command(self.session_a.session_id, "look")
        freeze_b = self.server.execute_command(self.session_b.session_id, "look")
        self.assertTrue(any("temporarily frozen" in text.lower() for text in self._text_payloads(freeze_a)))
        self.assertTrue(any("temporarily frozen" in text.lower() for text in self._text_payloads(freeze_b)))

        freeze_tick = self._drain_tick(self.session_a.session_id)
        self.assertEqual([], freeze_tick)
        self.assertEqual(3, self.probe_provider.tick_calls)

        ok, _message = self.server.set_shard_runtime_state("maintenance", "Rolling restart")
        self.assertTrue(ok)

        maintenance_a = self.server.execute_command(self.session_a.session_id, "look")
        self.assertTrue(any("maintenance" in text.lower() for text in self._text_payloads(maintenance_a)))

        newcomer_maintenance = self.server.execute_command(newcomer.session_id, "char create StillBlocked")
        self.assertTrue(any("maintenance" in text.lower() for text in self._text_payloads(newcomer_maintenance)))
        self.assertIsNone(self.server.get_player_for_session(newcomer.session_id))

        maintenance_tick = self._drain_tick(self.session_b.session_id)
        self.assertEqual([], maintenance_tick)
        self.assertEqual(3, self.probe_provider.tick_calls)

        ok, _message = self.server.set_shard_runtime_state("normal")
        self.assertTrue(ok)

        resumed_events = self.server.execute_command(self.session_a.session_id, "look")
        resumed_text = self._text_payloads(resumed_events)
        self.assertFalse(any("maintenance" in text.lower() for text in resumed_text))
        self.assertFalse(any("temporarily frozen" in text.lower() for text in resumed_text))

        resumed_tick = self._drain_tick(self.session_a.session_id)
        self.assertTrue(any(event.get("type") == "world_state" for event in resumed_tick))
        self.assertEqual(5, self.probe_provider.tick_calls)


if __name__ == "__main__":
    unittest.main()
