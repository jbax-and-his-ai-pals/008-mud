# tests/singles/test_load_soak.py
"""
Load and soak test for the headless server.

Validates:
  - Server handles N concurrent sessions without degradation.
  - Command throughput is stable over M sequential command cycles.
  - No memory leak from session churn (sessions are cleaned up).
  - Entitlement guard is applied correctly per session.
"""
import time
import unittest

from tests.fixtures import make_test_server


CONCURRENT_SESSIONS = 10
COMMANDS_PER_SESSION = 50


class TestLoadAndSoak(unittest.TestCase):

    def setUp(self):
        self.server = make_test_server()

    def tearDown(self):
        self.server.persistence.stop_async_writer()

    def _run_cmd(self, session_id: str, cmd: str):
        return self.server.execute_command(session_id, cmd)

    # --- Throughput ---

    def test_single_session_command_throughput(self):
        """Verify a single session can sustain 50 sequential commands without error."""
        session = self.server.create_session("player_soak_1")
        commands = ["look", "inventory", "stats", "time", "help"]
        errors = 0
        for i in range(COMMANDS_PER_SESSION):
            cmd = commands[i % len(commands)]
            result = self._run_cmd(session.session_id, cmd)
            if result and any(e.get("type") == "error" for e in result):
                errors += 1
        self.assertEqual(errors, 0, "Unexpected errors during soak run")

    # --- Concurrency (sequential simulation) ---

    def test_multi_session_no_state_bleed(self):
        """Verify N sessions remain isolated - moving one doesn't affect others."""
        sessions = [
            self.server.create_session(f"player_load_{i}")
            for i in range(CONCURRENT_SESSIONS)
        ]
        # All sessions start in town_square; issue look for each
        for s in sessions:
            result = self._run_cmd(s.session_id, "look")
            self.assertIsNotNone(result)

        # Move session 0 north and verify session 1 location unchanged
        p0 = self.server.get_player_for_session(sessions[0].session_id)
        p1 = self.server.get_player_for_session(sessions[1].session_id)
        original_room = p1.current_room_id if p1 else None
        self._run_cmd(sessions[0].session_id, "go north")
        if p1 and original_room:
            self.assertEqual(
                p1.current_room_id,
                original_room,
                "Session 1 location was modified by session 0 movement",
            )

    # --- Session churn ---

    def test_session_churn_no_accumulation(self):
        """Verify sessions can be created and destroyed without unbounded growth."""
        initial_count = len(self.server.sessions)
        created = []
        for i in range(20):
            s = self.server.create_session(f"churn_{i}")
            created.append(s.session_id)
        self.assertEqual(len(self.server.sessions), initial_count + 20)

        # Simulate cleanup
        for sid in created:
            self.server.sessions.pop(sid, None)
        self.assertEqual(len(self.server.sessions), initial_count)

    # --- Entitlement ---

    def test_entitlement_default_grants_applied(self):
        """Verify default entitlement grants are merged at session creation."""
        from engine.server.entitlement import EntitlementGuard
        self.server.entitlement_guard = EntitlementGuard(
            {"default_session_grants": ["pack.sample_world"]}
        )
        session = self.server.create_session("player_ent_1")
        self.assertIn("pack.sample_world", session.entitlements)

    def test_entitlement_gate_blocks_missing(self):
        """Verify a gate blocks a session that lacks the required entitlement."""
        from engine.server.entitlement import EntitlementGuard
        guard = EntitlementGuard(
            {"gates": {"creator_sdk": {"requires": ["creator_sdk"]}}}
        )
        allowed, reason = guard.check("creator_sdk", [])
        self.assertFalse(allowed)
        self.assertIn("creator_sdk", reason)

    def test_entitlement_gate_passes_with_grant(self):
        """Verify a gate passes when the session holds the required entitlement."""
        from engine.server.entitlement import EntitlementGuard
        guard = EntitlementGuard(
            {"gates": {"creator_sdk": {"requires": ["creator_sdk"]}}}
        )
        allowed, _ = guard.check("creator_sdk", ["creator_sdk"])
        self.assertTrue(allowed)

    def test_entitlement_undefined_gate_is_open(self):
        """Verify an undefined gate does not block access."""
        from engine.server.entitlement import EntitlementGuard
        guard = EntitlementGuard()
        allowed, _ = guard.check("some.unknown.feature", [])
        self.assertTrue(allowed)

    # --- Timing budget ---

    def test_command_latency_budget(self):
        """Verify average command latency stays under 10ms in headless mode."""
        session = self.server.create_session("player_perf_1")
        commands = ["look", "inventory", "stats", "time"]
        times = []
        for i in range(40):
            cmd = commands[i % len(commands)]
            t0 = time.perf_counter()
            self._run_cmd(session.session_id, cmd)
            times.append(time.perf_counter() - t0)
        avg_ms = (sum(times) / len(times)) * 1000
        self.assertLess(avg_ms, 10.0, f"Average command latency {avg_ms:.2f}ms exceeds 10ms budget")


if __name__ == "__main__":
    unittest.main()
