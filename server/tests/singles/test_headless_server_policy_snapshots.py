import json
import os
import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER
from tests.singles.snapshot_assertions import assert_snapshot


class TestHeadlessServerPolicySnapshots(unittest.TestCase):
    def _snapshot_path(self, name: str) -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "snapshots", name))

    def test_readonly_policy_blocks_mutation_command_snapshot(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, tick_rate_hz=10.0)
        session = server.create_session(player_id="snapshot_player")
        try:
            server.feature_profile.world_mutation_mode = "readonly"
            events = server.execute_command(session.session_id, "drop all")
            assert_snapshot(
                self,
                self._snapshot_path("headless_server_readonly_events.json"),
                {
                    "policy": {
                        "world_mutation_mode": server.feature_profile.world_mutation_mode,
                        "combat_mode": server.feature_profile.combat_mode,
                    },
                    "events": events,
                },
            )
        finally:
            server.shutdown()

    def test_no_combat_policy_blocks_attack_snapshot(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, tick_rate_hz=10.0)
        session = server.create_session(player_id="snapshot_player")
        try:
            server.feature_profile.combat_mode = "disabled"
            events = server.execute_command(session.session_id, "attack goblin")
            assert_snapshot(
                self,
                self._snapshot_path("headless_server_no_combat_events.json"),
                {
                    "policy": {
                        "world_mutation_mode": server.feature_profile.world_mutation_mode,
                        "combat_mode": server.feature_profile.combat_mode,
                    },
                    "events": events,
                },
            )
        finally:
            server.shutdown()

    def test_custom_provider_routing_snapshot(self) -> None:
        profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".tmp"))
        os.makedirs(profile_dir, exist_ok=True)
        profile_path = os.path.join(profile_dir, "snapshot_provider_profile.json")
        profile_payload = {
            "weather": {"mode": "custom", "provider_id": "mod.weather.missing"},
            "world_effects": {"mode": "custom", "provider_id": "mod.effects.missing"},
            "mods": {"mode": "disabled"},
        }
        with open(profile_path, "w", encoding="utf-8") as handle:
            json.dump(profile_payload, handle)

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            deterministic_test_mode=True,
            tick_rate_hz=10.0,
            feature_profile_path=profile_path,
        )
        try:
            events = server.execute_command(server.create_session().session_id, "look")
            world_state_events = [event for event in events if event.get("type") == "world_state"]
            snapshot_payload = {
                "profile": profile_payload,
                "provider_state": {
                    "weather_mode": getattr(server.weather_provider, "mode", ""),
                    "weather_provider_id": getattr(server.weather_provider, "provider_id", ""),
                    "world_effects_mode": getattr(server.world_effects_provider, "mode", ""),
                    "world_effects_provider_id": getattr(server.world_effects_provider, "provider_id", ""),
                    "world_state_event_count": len(world_state_events),
                },
                "warnings": sorted(server.boot_warnings),
            }
            assert_snapshot(self, self._snapshot_path("headless_server_provider_routing.json"), snapshot_payload)
        finally:
            server.shutdown()
            if os.path.exists(profile_path):
                try:
                    os.remove(profile_path)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
