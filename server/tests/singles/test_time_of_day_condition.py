# tests/singles/test_time_of_day_condition.py
"""`time_of_day` is a registered condition that could never be true.

`conditions.py` read the clock value from `data.get("period", ...)`, but
`TimeManager._update_time_data_for_ui` publishes the key **`time_period`**. The
lookup therefore always returned `""`, every comparison was `"" != wanted`, and
the kind failed closed for every caller.

Nothing caught it because nothing used it: the kind is in `KNOWN_KINDS`, typed in
the editor's `DialogueSchema.gd`, and exercised by no content in any set. That is
the same shape as `default_damage_type` — a declaration the engine answers
wrongly, invisible because nothing reads it.

So this file tests the *match*, not the parse. A test that only asserted "the
condition evaluates without raising" would have passed against the broken code.
"""
import unittest

from tests.fixtures import GameTestBase
from engine.conditions import KNOWN_KINDS, evaluate, explain


class TestTheConditionCanBeTrue(GameTestBase):
    def _set_period(self, period: str) -> None:
        """Drive the world's clock to a period, through the real publisher."""
        time_manager = self.game.time_manager
        time_manager.current_time_period = period
        time_manager._update_time_data_for_ui()

    def test_the_kind_is_registered(self):
        self.assertIn("time_of_day", KNOWN_KINDS)

    def test_a_matching_period_satisfies_the_condition(self):
        self._set_period("night")
        result = evaluate({"kind": "time_of_day", "value": "night"}, self.player)
        self.assertTrue(
            result,
            "time_of_day 'night' must match a night clock; it read the wrong key "
            "and returned '' for every period until this was fixed",
        )

    def test_a_different_period_does_not(self):
        self._set_period("night")
        self.assertFalse(evaluate({"kind": "time_of_day", "value": "dawn"}, self.player))

    def test_every_period_the_engine_uses_round_trips(self):
        """The five period names in config_game, each matched and then refused."""
        for period in ("dawn", "morning", "afternoon", "dusk", "night"):
            self._set_period(period)
            self.assertTrue(
                evaluate({"kind": "time_of_day", "value": period}, self.player),
                "period %r did not round-trip" % period,
            )
            self.assertFalse(
                evaluate({"kind": "time_of_day", "value": "not_a_period"}, self.player),
                "period %r matched a name the engine never publishes" % period,
            )

    def test_season_still_works(self):
        """The sibling key was always read correctly; this is the control."""
        self.game.time_manager._update_time_data_for_ui()
        season = str(self.game.time_manager.time_data.get("season", ""))
        self.assertTrue(season, "the clock should publish a season")
        self.assertTrue(evaluate({"kind": "season", "value": season}, self.player))

    def test_the_reason_names_the_actual_period(self):
        """A refusal must say what the world thought the time was."""
        self._set_period("night")
        result = evaluate({"kind": "time_of_day", "value": "dawn"}, self.player)
        self.assertFalse(result)
        text = explain({"kind": "time_of_day", "value": "dawn"}, self.player)
        self.assertIn("night", str(text), "the explanation should report the real period")


class TestTheOlderKeySpellingsStillWork(GameTestBase):
    """A publisher using either older name should keep working."""

    def test_a_time_manager_publishing_period_is_read(self):
        self.game.time_manager.time_data = {"period": "dusk", "season": "fall"}
        self.assertTrue(evaluate({"kind": "time_of_day", "value": "dusk"}, self.player))

    def test_an_empty_time_data_does_not_match_anything(self):
        self.game.time_manager.time_data = {}
        self.assertFalse(evaluate({"kind": "time_of_day", "value": "night"}, self.player))


if __name__ == "__main__":
    unittest.main()
