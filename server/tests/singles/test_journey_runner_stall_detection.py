# tests/singles/test_journey_runner_stall_detection.py
"""Coverage for journey_runner.py's repeated-failure/stall detector:
gameplay_failure_count is only a raw sum across a whole run, so a player
who hits one failure every ten steps looks identical to one stuck
repeating the same failing action forever. _detect_repeated_failure_stalls
flags a run of consecutive failure-classified steps with no intervening
success -- these tests exercise it directly against hand-built
JourneyStep lists, with no live server needed."""

import unittest

from tests.journey_runner import (
    JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES,
    JourneyReport,
    JourneyStep,
    MultiJourneyReport,
    _detect_repeated_failure_stalls,
)


def _step(index: int, failed: bool) -> JourneyStep:
    return JourneyStep(
        index=index,
        command="whatever",
        event_types=["text"],
        error_messages=[],
        location=("town", "town_square"),
        health=100,
        inventory_slots_used=1,
        text_messages=["You need a pickaxe to gather from this."] if failed else ["You look around."],
        gameplay_failures=["You need a pickaxe to gather from this."] if failed else [],
    )


class TestDetectRepeatedFailureStalls(unittest.TestCase):
    def test_short_streak_below_threshold_is_not_flagged(self):
        steps = [_step(i, failed=True) for i in range(JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES - 1)]
        self.assertEqual([], _detect_repeated_failure_stalls(steps, JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES))

    def test_streak_at_threshold_is_flagged_with_the_right_range(self):
        steps = [_step(i, failed=True) for i in range(JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES)]
        errors = _detect_repeated_failure_stalls(steps, JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES)
        self.assertEqual(1, len(errors))
        self.assertIn(f"steps 0-{JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES - 1}", errors[0])
        self.assertIn(f"{JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES} consecutive", errors[0])

    def test_a_success_in_the_middle_resets_the_streak_and_prevents_a_false_positive(self):
        steps = (
            [_step(i, failed=True) for i in range(2)]
            + [_step(2, failed=False)]
            + [_step(i, failed=True) for i in range(3, 5)]
        )
        self.assertEqual([], _detect_repeated_failure_stalls(steps, JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES))

    def test_two_streaks_separated_by_a_success_produce_two_separate_messages(self):
        threshold = JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES
        steps = (
            [_step(i, failed=True) for i in range(threshold)]
            + [_step(threshold, failed=False)]
            + [_step(threshold + 1 + i, failed=True) for i in range(threshold)]
        )
        errors = _detect_repeated_failure_stalls(steps, threshold)
        self.assertEqual(2, len(errors))
        self.assertIn(f"steps 0-{threshold - 1}", errors[0])
        self.assertIn(f"steps {threshold + 1}-{2 * threshold}", errors[1])

    def test_a_longer_streak_still_produces_exactly_one_message(self):
        steps = [_step(i, failed=True) for i in range(JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES + 6)]
        errors = _detect_repeated_failure_stalls(steps, JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES)
        self.assertEqual(1, len(errors))

    def test_empty_steps_produce_no_errors(self):
        self.assertEqual([], _detect_repeated_failure_stalls([], JOURNEY_MAX_CONSECUTIVE_GAMEPLAY_FAILURES))


class TestStallErrorsFailTheReport(unittest.TestCase):
    def test_journey_report_with_stall_errors_is_not_passed(self):
        report = JourneyReport(
            seed=1, player_name="Tester", action_interval_s=5.0,
            requested_duration_s=10.0, simulated_duration_s=10.0,
            steps=[], invariant_errors=[], outcome_errors=[],
            stall_errors=["steps 0-3: 4 consecutive gameplay failures with no progress"],
        )
        self.assertFalse(report.passed)

    def test_journey_report_with_no_errors_at_all_is_passed(self):
        report = JourneyReport(
            seed=1, player_name="Tester", action_interval_s=5.0,
            requested_duration_s=10.0, simulated_duration_s=10.0,
            steps=[], invariant_errors=[], outcome_errors=[], stall_errors=[],
        )
        self.assertTrue(report.passed)

    def test_multi_journey_report_with_stall_errors_is_not_passed(self):
        report = MultiJourneyReport(
            seed=1, action_interval_s=5.0, requested_duration_s=10.0,
            agents={}, invariant_errors=[],
            stall_errors=["agent_1: steps 0-3: 4 consecutive gameplay failures with no progress"],
        )
        self.assertFalse(report.passed)

    def test_multi_journey_report_with_no_errors_at_all_is_passed(self):
        report = MultiJourneyReport(
            seed=1, action_interval_s=5.0, requested_duration_s=10.0,
            agents={}, invariant_errors=[], stall_errors=[],
        )
        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
