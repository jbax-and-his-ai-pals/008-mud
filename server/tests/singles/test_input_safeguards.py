import unittest

from engine.server.input_safeguards import InputSafeguards, SessionRateLimiter


class TestInputSafeguards(unittest.TestCase):
    def test_command_length_guard(self) -> None:
        guards = InputSafeguards(max_command_chars=12)
        ok_short, _ = guards.check_command_text("look")
        ok_long, reason = guards.check_command_text("x" * 32)
        self.assertTrue(ok_short)
        self.assertFalse(ok_long)
        self.assertIn("command too long", reason.lower())

    def test_envelope_size_guard(self) -> None:
        guards = InputSafeguards(max_envelope_bytes=64)
        ok_small, _ = guards.check_envelope_size(32)
        ok_large, reason = guards.check_envelope_size(128)
        self.assertTrue(ok_small)
        self.assertFalse(ok_large)
        self.assertIn("envelope too large", reason.lower())

    def test_rate_limit_guard(self) -> None:
        guards = InputSafeguards(command_rate_limit_per_sec=1.0, command_burst=2)
        a1, _ = guards.consume_rate_budget("s1")
        a2, _ = guards.consume_rate_budget("s1")
        a3, retry = guards.consume_rate_budget("s1")
        self.assertTrue(a1)
        self.assertTrue(a2)
        self.assertFalse(a3)
        self.assertGreater(retry, 0.0)

    def test_blank_session_id_is_never_allowed(self) -> None:
        limiter = SessionRateLimiter(rate_per_sec=10.0, burst=5)
        result = limiter.consume("   ")
        self.assertFalse(result.allowed)
        self.assertEqual(1.0, result.retry_after_s)

    def test_clearing_a_blank_session_id_is_a_no_op(self) -> None:
        limiter = SessionRateLimiter(rate_per_sec=10.0, burst=5)
        limiter.clear("")  # must not raise

    def test_evict_stale_sessions_removes_inactive_state(self) -> None:
        guards = InputSafeguards()
        guards.consume_rate_budget("active_session")
        guards.consume_rate_budget("stale_session")

        removed = guards.evict_stale_sessions({"active_session"})

        self.assertEqual(1, removed)
        self.assertNotIn("stale_session", guards._limiter._tokens_by_session)
        self.assertIn("active_session", guards._limiter._tokens_by_session)


if __name__ == "__main__":
    unittest.main()
