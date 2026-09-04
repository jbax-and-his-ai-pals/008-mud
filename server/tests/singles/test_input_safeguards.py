import unittest

from engine.server.input_safeguards import InputSafeguards


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


if __name__ == "__main__":
    unittest.main()
