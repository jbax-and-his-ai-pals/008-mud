# tests/singles/test_work_contract.py
"""`work`: the fourth contract the engine evaluates rather than the content.

The shape being tested is one declaration plus two absolute numbers. A timer is
`started_at` and `ends_at`, so "is it done" is a comparison every reader makes
for itself and no loop has to fire at a particular moment. That is what makes a
duration survive a restart -- which is asserted here by round-tripping a timer
through JSON and reading it against a world whose clock has moved on, because
that is exactly what a save file does.

The other half is what the module refuses. Undeclared work, a timer with no
readable end, a world with no clock: each returns None or a stated reason rather
than inventing a duration, and each has a test, because "it fails closed" is a
claim that is only worth anything if it has been seen to fail.
"""

import json
import unittest

from engine.contracts import SCHEMA_VERSION, ContractRegistry, validate_fields
from engine.contracts.registry import CONTRACT_SCHEMAS, WORK_FIELDS
from engine.contracts.work import (
    SECONDS_PER_GAME_DAY,
    TIMER_FIELDS,
    begin,
    declaration_issues,
    duration_seconds,
    is_due,
    observe,
    remaining_seconds,
    work_for,
)
from engine.core.clock import SimulatedClock, WallClock


# -- the world the module reads from ------------------------------------------

class _World:
    """Minimal world: a clock, and whatever registry a test hands it."""

    def __init__(self, registry=None, clock=None):
        self.contract_registry = registry
        self.clock = clock


def _payload(work, **overrides):
    base = {
        "schema_version": SCHEMA_VERSION, "work": work,
        "resources": [], "item_families": [], "generation_profiles": [],
        "attack_profiles": [], "defense_profiles": [], "abilities": [],
        "effect_packets": [],
    }
    base.update(overrides)
    return base


def _registry(*declarations):
    registry = ContractRegistry()
    registry.ingest(_payload(list(declarations)))
    assert registry.issues == [], registry.issues
    return registry


def _world(work, clock=None, **fields):
    declaration = {"id": work, "label": work.replace("_", " ").title()}
    declaration.update(fields)
    return _World(registry=_registry(declaration),
                  clock=SimulatedClock() if clock is None else clock)



# -- the declaration ----------------------------------------------------------

class TestWorkDeclaration(unittest.TestCase):
    def test_an_id_and_a_label_are_the_whole_requirement(self):
        """Work with no duration is a recipe, not an error."""
        issues = []
        validate_fields({"id": "bake_bread", "label": "Bake bread"}, WORK_FIELDS, "work[0]", issues)
        self.assertEqual([], issues)

    def test_an_unknown_field_is_refused(self):
        issues = []
        validate_fields({"id": "x", "label": "X", "duration_day": 1}, WORK_FIELDS, "work[0]", issues)
        self.assertTrue(any("duration_day" in issue and "not a field" in issue for issue in issues), issues)

    def test_a_negative_duration_is_refused(self):
        issues = []
        validate_fields({"id": "x", "label": "X", "duration_days": -1}, WORK_FIELDS, "work[0]", issues)
        self.assertTrue(any("at least 0" in issue for issue in issues), issues)

    def test_an_input_entry_without_an_item_is_refused(self):
        issues = []
        validate_fields(
            {"id": "x", "label": "X", "inputs": [{"quantity": 2}]},
            WORK_FIELDS, "work[0]", issues,
        )
        self.assertTrue(any("inputs[0].item_id is required" in issue for issue in issues), issues)

    def test_work_is_a_top_level_section_of_the_same_language(self):
        """`work` is in CONTRACT_SCHEMAS, which is what makes the audit see it."""
        self.assertIn("work", CONTRACT_SCHEMAS)
        self.assertIs(WORK_FIELDS, CONTRACT_SCHEMAS["work"])

    def test_a_registry_declaring_only_work_is_not_empty(self):
        """Otherwise a work-only set reads as "declares no contracts" and is skipped."""
        registry = _registry({"id": "ferment", "label": "Ferment", "duration_days": 3})
        self.assertFalse(registry.is_empty)
        self.assertIn("work", registry.status())


# -- lookups ------------------------------------------------------------------

class TestWorkLookup(unittest.TestCase):
    def test_a_declared_id_resolves(self):
        world = _world("ferment", duration_days=3)
        self.assertEqual("ferment", work_for(world, "ferment")["id"])
        self.assertEqual("ferment", world.contract_registry.work_declaration("ferment")["id"])

    def test_an_undeclared_id_resolves_to_nothing_rather_than_a_guess(self):
        world = _world("ferment", duration_days=3)
        self.assertIsNone(work_for(world, "no_such_work"))
        self.assertIsNone(work_for(world, ""))

    def test_a_world_with_no_registry_resolves_to_nothing(self):
        self.assertIsNone(work_for(_World(), "ferment"))
        self.assertIsNone(work_for(None, "ferment"))


# -- durations ----------------------------------------------------------------

class TestDuration(unittest.TestCase):
    def test_days_become_seconds(self):
        self.assertEqual(SECONDS_PER_GAME_DAY, duration_seconds({"duration_days": 1}))
        self.assertEqual(3 * SECONDS_PER_GAME_DAY, duration_seconds({"duration_days": 3}))
        self.assertEqual(0.5 * SECONDS_PER_GAME_DAY, duration_seconds({"duration_days": 0.5}))

    def test_no_duration_is_instant_not_unknown(self):
        self.assertEqual(0.0, duration_seconds({"id": "x", "label": "X"}))

    def test_a_duration_that_is_not_a_number_is_instant(self):
        """The schema refuses these; the reader must not multiply garbage."""
        for value in ("3", True, None, [], {}):
            self.assertEqual(0.0, duration_seconds({"duration_days": value}), value)

    def test_a_negative_duration_never_runs_backwards(self):
        self.assertEqual(0.0, duration_seconds({"duration_days": -5}))

    def test_a_declaration_that_is_not_an_object_is_instant(self):
        self.assertEqual(0.0, duration_seconds(None))
        self.assertEqual(0.0, duration_seconds(["duration_days", 3]))


# -- starting -----------------------------------------------------------------

class TestBegin(unittest.TestCase):
    def test_the_timer_is_the_four_fields_and_nothing_else(self):
        world = _world("ferment", duration_days=2)
        timer = begin(world, "ferment")
        self.assertEqual(set(TIMER_FIELDS), set(timer))

    def test_the_timer_is_anchored_to_the_world_clock(self):
        clock = SimulatedClock(start=1_000_000.0)
        world = _world("ferment", clock=clock, duration_days=2)
        timer = begin(world, "ferment")
        self.assertEqual(1_000_000.0, timer["started_at"])
        self.assertEqual(1_000_000.0 + 2 * SECONDS_PER_GAME_DAY, timer["ends_at"])
        self.assertEqual("ferment", timer["work"])

    def test_instant_work_ends_the_moment_it_starts(self):
        world = _World(registry=_registry({"id": "assemble", "label": "Assemble"}),
                       clock=SimulatedClock())
        timer = begin(world, "assemble")
        self.assertEqual(timer["started_at"], timer["ends_at"])
        self.assertTrue(is_due(world, timer))

    def test_a_caller_may_name_the_timer(self):
        """Two ferments in one room are two timers, not one overwritten."""
        world = _world("ferment", duration_days=2)
        first = begin(world, "ferment", timer_id="ferment:1")
        second = begin(world, "ferment", timer_id="ferment:2")
        self.assertEqual("ferment:1", first["id"])
        self.assertEqual("ferment:2", second["id"])

    def test_an_unnamed_timer_falls_back_to_the_work_id(self):
        world = _world("ferment", duration_days=2)
        self.assertEqual("ferment", begin(world, "ferment")["id"])

    def test_undeclared_work_does_not_start(self):
        world = _world("ferment", duration_days=2)
        self.assertIsNone(begin(world, "no_such_work"))

    def test_a_world_with_no_clock_does_not_start(self):
        """Anchoring to wall time instead would make a replay disagree with itself."""
        world = _World(registry=_registry({"id": "ferment", "label": "F", "duration_days": 2}))
        world.clock = None
        self.assertIsNone(begin(world, "ferment"))

    def test_a_clock_that_is_not_readable_does_not_start(self):
        class _Broken:
            def now(self):
                raise ValueError("no time today")

        world = _world("ferment", duration_days=2)
        world.clock = _Broken()
        self.assertIsNone(begin(world, "ferment"))

    def test_a_wall_clock_also_works(self):
        """The live server's clock, which is the other implementation of the protocol."""
        world = _World(
            registry=_registry({"id": "ferment", "label": "F", "duration_days": 1}),
            clock=WallClock(),
        )
        timer = begin(world, "ferment")
        self.assertFalse(is_due(world, timer))
        self.assertAlmostEqual(SECONDS_PER_GAME_DAY, remaining_seconds(world, timer), delta=1.0)


# -- reading ------------------------------------------------------------------

class TestRemainingAndDue(unittest.TestCase):
    def test_remaining_counts_down_as_the_clock_advances(self):
        clock = SimulatedClock()
        world = _world("ferment", clock=clock, duration_days=1)
        timer = begin(world, "ferment")
        clock.advance(SECONDS_PER_GAME_DAY / 4)
        self.assertEqual(0.75 * SECONDS_PER_GAME_DAY, remaining_seconds(world, timer))

    def test_a_finished_timer_is_zero_not_negative(self):
        """A week-overdue timer is finished, not "-604800 seconds left"."""
        clock = SimulatedClock()
        world = _world("ferment", clock=clock, duration_days=1)
        timer = begin(world, "ferment")
        clock.advance(8 * SECONDS_PER_GAME_DAY)
        self.assertEqual(0.0, remaining_seconds(world, timer))

    def test_due_flips_exactly_at_the_end(self):
        clock = SimulatedClock()
        world = _world("ferment", clock=clock, duration_days=1)
        timer = begin(world, "ferment")
        clock.advance(SECONDS_PER_GAME_DAY - 1)
        self.assertFalse(is_due(world, timer))
        clock.advance(1)
        self.assertTrue(is_due(world, timer))

    def test_an_unreadable_timer_is_not_due(self):
        """Failing closed keeps a corrupt record from completing work nobody asked for."""
        world = _world("ferment", duration_days=1)
        for timer in (None, "ferment", 7, [], {}, {"work": "ferment"},
                      {"ends_at": "soon"}, {"ends_at": True}, {"ends_at": None}):
            self.assertIsNone(remaining_seconds(world, timer), timer)
            self.assertFalse(is_due(world, timer), timer)

    def test_a_timer_cannot_be_read_without_a_clock(self):
        world = _world("ferment", duration_days=1)
        timer = begin(world, "ferment")
        world.clock = None
        self.assertIsNone(remaining_seconds(world, timer))
        self.assertFalse(is_due(world, timer))


class TestObserve(unittest.TestCase):
    def test_observe_reports_the_shape_a_reader_can_print(self):
        world = _world("ferment", duration_days=2)
        timer = begin(world, "ferment")
        seen = observe(world, timer)
        self.assertTrue(seen["ok"])
        self.assertEqual("ferment", seen["work"])
        self.assertEqual("Ferment", seen["label"])
        self.assertFalse(seen["ready"])
        self.assertEqual(2.0, seen["remaining_days"])
        self.assertEqual(timer["started_at"], seen["started_at"])
        self.assertEqual(timer["ends_at"], seen["ends_at"])

    def test_observe_does_not_complete_anything(self):
        """Reading a ready timer leaves it ready; nothing is consumed by looking."""
        world = _world("ferment", duration_days=1)
        timer = begin(world, "ferment")
        world.clock.advance(2 * SECONDS_PER_GAME_DAY)
        self.assertTrue(observe(world, timer)["ready"])
        self.assertTrue(observe(world, timer)["ready"])
        self.assertEqual(set(TIMER_FIELDS), set(timer))

    def test_observe_names_what_it_cannot_read(self):
        world = _world("ferment", duration_days=2)
        self.assertEqual("not a timer", observe(world, "ferment")["reason"])
        self.assertIn("undeclared work", observe(world, {"work": "ghost", "ends_at": 0})["reason"])
        self.assertIn("no readable end", observe(world, {"work": "ferment"})["reason"])

    def test_the_label_comes_from_the_declaration_not_the_engine(self):
        """A caller prints `label` and is right for work it has never heard of."""
        world = _World(
            registry=_registry({"id": "x9", "label": "Charge the capacitor", "duration_days": 0.25}),
            clock=SimulatedClock(),
        )
        seen = observe(world, begin(world, "x9"))
        self.assertEqual("Charge the capacitor", seen["label"])


class TestSurvivesARestart(unittest.TestCase):
    """The claim the whole two-numbers design rests on."""

    def test_a_saved_timer_is_still_meaningful_after_the_process_is_gone(self):
        clock = SimulatedClock(start=1_000_000.0)
        world = _world("ferment", clock=clock, duration_days=3)
        saved = json.dumps(begin(world, "ferment"))

        # The process stops, days pass, the process comes back with a later clock.
        clock.set(1_000_000.0 + 4 * SECONDS_PER_GAME_DAY)
        restored = json.loads(saved)
        self.assertEqual(set(TIMER_FIELDS), set(restored))
        self.assertTrue(is_due(world, restored))
        self.assertEqual("ferment", observe(world, restored)["work"])

    def test_a_saved_timer_that_has_not_elapsed_is_not_due_on_return(self):
        clock = SimulatedClock(start=1_000_000.0)
        world = _world("ferment", clock=clock, duration_days=3)
        saved = json.dumps(begin(world, "ferment"))
        clock.set(1_000_000.0 + 1 * SECONDS_PER_GAME_DAY)
        self.assertFalse(is_due(world, json.loads(saved)))


# -- the vocabulary check -----------------------------------------------------

class TestDeclarationIssues(unittest.TestCase):
    def test_a_clean_declaration_has_nothing_to_say(self):
        self.assertEqual([], declaration_issues({
            "id": "ferment", "label": "Ferment", "duration_days": 3,
            "inputs": [{"item_id": "item_grain", "quantity": 2}],
            "outputs": [{"item_id": "item_ale"}],
            "skill": "brewing", "difficulty": 12, "tags": ["crafting"],
        }))

    def test_work_with_no_gate_at_all_is_legal(self):
        self.assertEqual([], declaration_issues({"id": "wait", "label": "Wait", "duration_days": 1}))

    def test_a_skill_with_no_difficulty_gates_nothing(self):
        issues = declaration_issues({"id": "ferment", "label": "F", "skill": "brewing"})
        self.assertTrue(any("brewing" in issue and "no difficulty" in issue for issue in issues), issues)

    def test_a_difficulty_with_no_skill_rolls_nothing(self):
        issues = declaration_issues({"id": "ferment", "label": "F", "difficulty": 12})
        self.assertTrue(any("nothing rolls it" in issue for issue in issues), issues)

    def test_inputs_and_outputs_must_be_lists(self):
        issues = declaration_issues({"id": "ferment", "label": "F", "inputs": {"item_id": "grain"}})
        self.assertTrue(any("inputs must be a list" in issue for issue in issues), issues)

    def test_an_entry_with_no_item_id_is_reported(self):
        """Both spellings of the mistake: a blank id, and an entry that is not an object."""
        issues = declaration_issues({
            "id": "ferment", "label": "F",
            "inputs": [{"item_id": "grain"}], "outputs": [{"item_id": "  "}, "ale"],
        })
        self.assertEqual([], [i for i in issues if "inputs has an entry" in i], issues)
        self.assertEqual(2, len([i for i in issues if "outputs has an entry" in i]), issues)

    def test_a_non_object_declaration_is_reported_not_crashed_on(self):
        self.assertEqual(["work must be an object"], declaration_issues("ferment"))
        self.assertEqual(["work must be an object"], declaration_issues(None))


if __name__ == "__main__":
    unittest.main()
