import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


def _texts(events):
    return [str(e.get("payload", "")) for e in events if e.get("type") == "text"]


class _FieldFxTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create FieldTester")

    def tearDown(self) -> None:
        self.server.shutdown()

    def _cmd(self, text: str):
        return _texts(self.server.execute_command(self.session.session_id, text))


class TestBlightAndFieldPulse(_FieldFxTestBase):
    def test_blight_pulse_default_center(self):
        texts = self._cmd("blight pulse")
        self.assertTrue(any("Field pulse seeded: blight" in t for t in texts))

    def test_blight_pulse_with_coordinates_and_intensity(self):
        texts = self._cmd("blight pulse 2 3 0.5")
        self.assertTrue(any("at 2:3" in t and "0.50" in t for t in texts))

    def test_blight_pulse_rejects_out_of_bounds_coordinates(self):
        texts = self._cmd("blight pulse 99 99 1.0")
        self.assertTrue(any("out of bounds" in t for t in texts))

    def test_blight_pulse_rejects_non_numeric_args(self):
        texts = self._cmd("blight pulse abc def")
        self.assertTrue(any("Usage: blight pulse" in t for t in texts))

    def test_pulse_value_is_clamped_to_0_1(self):
        texts = self._cmd("blight pulse 1 1 5.0")
        self.assertTrue(any("value 1.00" in t for t in texts))

    def test_field_pulse_with_explicit_field_id(self):
        texts = self._cmd("field pulse sanctity 1 1 1.0")
        self.assertTrue(any("Field pulse seeded: sanctity" in t and "positive" in t for t in texts))

    def test_field_pulse_defaults_to_default_field_when_no_id_given(self):
        texts = self._cmd("field pulse 1 1 1.0")
        self.assertTrue(any("Field pulse seeded: blight" in t and "negative" in t for t in texts))

    def test_unrelated_command_is_not_intercepted(self):
        texts = self._cmd("look")
        self.assertFalse(any("Field pulse" in t for t in texts))

    def test_blocked_for_non_gm_session_when_authoring_is_restricted(self):
        self.server.feature_profile.authoring_mode = "gm_only"
        texts = self._cmd("blight pulse")
        self.assertTrue(any("require GM access" in t for t in texts))

    def test_allowed_for_gm_session_when_authoring_is_restricted(self):
        self.server.feature_profile.authoring_mode = "gm_only"
        self.session.capabilities.append("authoring.gm")
        texts = self._cmd("blight pulse")
        self.assertTrue(any("Field pulse seeded" in t for t in texts))


class TestFieldRules(_FieldFxTestBase):
    def test_field_rules_reports_pairwise_config(self):
        texts = self._cmd("field rules")
        self.assertTrue(any('"pairwise_rules"' in t for t in texts))

    def test_field_rule_alias(self):
        texts = self._cmd("field rule")
        self.assertTrue(any('"pairwise_rules"' in t for t in texts))

    def test_field_config_alias(self):
        texts = self._cmd("field config")
        self.assertTrue(any('"pairwise_rules"' in t for t in texts))


class TestFxDebugCommand(_FieldFxTestBase):
    def test_too_few_args_shows_usage(self):
        texts = self._cmd("fx shiver")
        self.assertTrue(any("Usage: fx" in t for t in texts))

    def test_unknown_effect_type_shows_usage(self):
        texts = self._cmd("fx sparkle 0.5")
        self.assertTrue(any("Usage: fx" in t for t in texts))

    def test_invalid_severity_shows_usage(self):
        texts = self._cmd("fx bleed not_a_number")
        self.assertTrue(any("Usage: fx" in t for t in texts))

    @staticmethod
    def _fx_payload(events):
        # Background ambient-NPC flavor text can add further "text" events
        # after the fx one, so find the fx payload (a dict) specifically.
        for e in events:
            if e.get("type") == "text" and isinstance(e.get("payload"), dict):
                return e["payload"]
        raise AssertionError("no fx payload text event found")

    def test_default_message_and_clamped_severity(self):
        events = self.server.execute_command(self.session.session_id, "fx rot 5.0")
        payload = self._fx_payload(events)
        self.assertEqual(1.0, payload["fx"]["severity"])
        self.assertEqual("rot", payload["fx"]["effect_type"])
        self.assertIn("Atmospheric effect sample", payload["text"])

    def test_custom_duration_and_message(self):
        events = self.server.execute_command(self.session.session_id, "fx shiver 0.3 2000 A cold wind blows.")
        payload = self._fx_payload(events)
        self.assertEqual(2000, payload["fx"]["duration_ms"])
        self.assertEqual("A cold wind blows.", payload["text"])

    def test_non_numeric_duration_falls_back_to_default_and_is_treated_as_message(self):
        events = self.server.execute_command(self.session.session_id, "fx shiver 0.3 not_a_duration extra words")
        payload = self._fx_payload(events)
        self.assertEqual(1200, payload["fx"]["duration_ms"])
        self.assertEqual("not_a_duration extra words", payload["text"])

    def test_duration_is_clamped_to_bounds(self):
        events = self.server.execute_command(self.session.session_id, "fx shiver 0.3 999999")
        payload = self._fx_payload(events)
        self.assertEqual(60000, payload["fx"]["duration_ms"])


if __name__ == "__main__":
    unittest.main()
