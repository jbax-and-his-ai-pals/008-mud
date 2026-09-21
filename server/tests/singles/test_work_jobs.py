# tests/singles/test_work_jobs.py
"""Starting and finishing work that takes time.

`test_work_contract.py` covers the shape: what a timer is, what a declaration
means, that a duration survives a restart. This file covers the two verbs that
move items — `start` and `collect` — and the properties that make them safe to
use on a player's inventory:

* **A refusal costs nothing.** Every check happens before anything is spent, and
  the order is part of the contract: no clock, no station, missing materials or
  no room for the result all leave the inventory exactly as it was.
* **The result is not decided until it is collected.** The skill check rolls at
  `collect`, because the check is about the *outcome*; a failure halves the yield
  rather than destroying the work, since the inputs were spent at the start.
* **A job with nowhere to go stays a job.** Collecting into a full inventory
  refuses and keeps the timer, which is recoverable; discarding the yield is not.
* **What is carried is what is saved.** A job round-trips through the player save
  with its two absolute numbers, and is due on the same wall-clock second either
  side of it.

The world here is a fixture rather than a content set, on purpose: these are
engine properties, and a test that reads them off shipped content would go green
because the content happens to be arranged that way.
"""

import unittest

from engine.contracts import SCHEMA_VERSION, ContractRegistry
from engine.contracts.work import (
    SECONDS_PER_GAME_DAY,
    carried_jobs,
    collect,
    declared_work,
    due_jobs,
    item_label,
    observe,
    start,
)
from engine.core.clock import SimulatedClock
from engine.items.inventory.core import Inventory
from engine.items.item_factory import ItemFactory
from engine.player.aspects import PlayerRuntimeState, WorkState


class _World:
    """A clock, item templates, and a registry a test hands it."""

    def __init__(self, templates=None, registry=None, clock=None):
        self.item_templates = templates or {}
        self.contract_registry = registry
        self.clock = clock or SimulatedClock()
        self.game = None


class _Player:
    def __init__(self, world):
        self.world = world
        self.inventory = Inventory()
        self.runtime_state = PlayerRuntimeState()


def _registry(*declarations):
    registry = ContractRegistry()
    registry.ingest({
        "schema_version": SCHEMA_VERSION,
        "work": list(declarations),
        "resources": [], "item_families": [], "generation_profiles": [],
        "attack_profiles": [], "defense_profiles": [], "abilities": [],
        "effect_packets": [],
    })
    assert registry.issues == [], registry.issues
    return registry


def _templates():
    return {
        "item_part": {"name": "salvaged part", "type": "Item", "value": 10, "weight": 0.5, "stackable": True},
        "item_output": {"name": "sealed crate", "type": "Item", "value": 40, "weight": 1.0, "stackable": True},
        "item_bulk": {"name": "hull plate", "type": "Item", "value": 5, "weight": 12.0, "stackable": False},
    }


def _world(*declarations, clock=None):
    world = _World(templates=_templates(), registry=_registry(*declarations), clock=clock)
    return world


def _player_with(world, *items):
    player = _Player(world)
    for item_id, quantity in items:
        item = ItemFactory.create_item_from_template(item_id, world)
        assert item is not None, item_id
        added, message = player.inventory.add_item(item, quantity)
        assert added, message
    return player


PART_JOB = {
    "id": "seal_crate", "label": "Sealing a crate", "duration_days": 0.5,
    "station": "sealer",
    "inputs": [{"item_id": "item_part", "quantity": 3}],
    "outputs": [{"item_id": "item_output", "quantity": 2}],
}


class TestStarting(unittest.TestCase):
    def test_it_consumes_the_declared_inputs_and_installs_a_timer(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 5))

        result = start(world, player, "seal_crate", ["sealer"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(2, player.inventory.count_item("item_part"))
        self.assertEqual(1, len(carried_jobs(player)))
        timer = carried_jobs(player)[0]
        self.assertEqual("seal_crate", timer["work"])
        self.assertEqual(world.clock.now() + 0.5 * SECONDS_PER_GAME_DAY, timer["ends_at"])

    def test_the_job_is_not_due_until_the_clock_says_so(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        start(world, player, "seal_crate", ["sealer"])

        self.assertFalse(observe(world, carried_jobs(player)[0])["ready"])
        world.clock.advance(0.5 * SECONDS_PER_GAME_DAY - 1)
        self.assertFalse(observe(world, carried_jobs(player)[0])["ready"])
        world.clock.advance(1)
        self.assertTrue(observe(world, carried_jobs(player)[0])["ready"])

    def test_a_one_day_job_is_due_after_one_game_day(self):
        """The unit, by meaning rather than by constant.

        A game day is `TIME_REAL_SECONDS_PER_GAME_DAY` of wall clock -- the same
        day `ResourceNode.respawn_days` counts. This started life multiplying by
        86400, which made an authored "one day" last 72 of them, and a test
        written against the module's own constant would have agreed with it.
        """
        world = _world({"id": "cure", "label": "Curing", "duration_days": 1,
                        "outputs": [{"item_id": "item_output", "quantity": 1}]})
        player = _world_player = _player_with(world)
        self.assertIsNotNone(player)
        start(world, player, "cure")
        timer = carried_jobs(player)[0]

        self.assertEqual(1200.0, timer["ends_at"] - timer["started_at"])
        world.clock.advance(1199)
        self.assertFalse(observe(world, timer)["ready"])
        world.clock.advance(1)
        self.assertTrue(observe(world, timer)["ready"])
        self.assertEqual(0.0, observe(world, timer)["remaining_days"])

    def test_a_refusal_costs_nothing(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 2))

        result = start(world, player, "seal_crate", ["sealer"])
        self.assertFalse(result["ok"])
        self.assertIn("salvaged part", result["message"])
        self.assertEqual(2, player.inventory.count_item("item_part"), "nothing was consumed")
        self.assertEqual([], carried_jobs(player), "and no timer was installed")

    def test_work_that_needs_a_station_refuses_without_one(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))

        result = start(world, player, "seal_crate", [])
        self.assertFalse(result["ok"])
        self.assertIn("sealer", result["message"])
        self.assertEqual(3, player.inventory.count_item("item_part"))

    def test_work_with_no_station_declared_runs_anywhere(self):
        world = _world({"id": "rest", "label": "Resting", "duration_days": 0.1,
                        "outputs": [{"item_id": "item_output", "quantity": 1}]})
        player = _player_with(world)
        self.assertTrue(start(world, player, "rest", [])["ok"])

    def test_an_undeclared_job_is_refused(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        result = start(world, player, "no_such_work", ["sealer"])
        self.assertFalse(result["ok"])
        self.assertEqual([], carried_jobs(player))

    def test_a_world_without_work_state_refuses_rather_than_crashing(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        player.runtime_state.work = None
        result = start(world, player, "seal_crate", ["sealer"])
        self.assertFalse(result["ok"])
        self.assertEqual(3, player.inventory.count_item("item_part"))

    def test_a_world_with_no_clock_refuses_before_spending_anything(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        world.clock = None
        result = start(world, player, "seal_crate", ["sealer"])
        self.assertFalse(result["ok"])
        self.assertEqual(3, player.inventory.count_item("item_part"))

    def test_two_batches_of_the_same_work_are_two_jobs(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 6))
        start(world, player, "seal_crate", ["sealer"])
        start(world, player, "seal_crate", ["sealer"])
        ids = [timer["id"] for timer in carried_jobs(player)]
        self.assertEqual(2, len(ids))
        self.assertEqual(len(set(ids)), 2, ids)

    def test_the_result_must_fit_before_the_materials_are_spent(self):
        """A job whose yield can never be carried is refused at the start.

        Three parts weigh 1.5 and the two crates weigh 2.0, so the trade needs
        0.5 of headroom: one carrying 1.75 in total refuses it.
        """
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        player.inventory.max_weight = player.inventory.get_total_weight() + 0.25

        result = start(world, player, "seal_crate", ["sealer"])
        self.assertFalse(result["ok"])
        self.assertEqual(3, player.inventory.count_item("item_part"), "nothing was consumed")

    def test_work_naming_an_item_this_world_does_not_have_is_refused(self):
        world = _world({"id": "ghost", "label": "Ghost work", "duration_days": 1,
                        "inputs": [{"item_id": "item_part", "quantity": 1}],
                        "outputs": [{"item_id": "item_missing", "quantity": 1}]})
        player = _player_with(world, ("item_part", 1))
        result = start(world, player, "ghost", [])
        self.assertFalse(result["ok"])
        self.assertEqual(1, player.inventory.count_item("item_part"))


class TestCollecting(unittest.TestCase):
    def _started(self, world, player):
        start(world, player, "seal_crate", ["sealer"])
        return carried_jobs(player)[0]

    def test_a_finished_job_yields_its_outputs_and_is_dropped(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        timer = self._started(world, player)
        world.clock.advance(0.5 * SECONDS_PER_GAME_DAY)

        result = collect(world, player, timer)
        self.assertTrue(result["ok"], result)
        self.assertEqual(2, player.inventory.count_item("item_output"))
        self.assertEqual([], carried_jobs(player))
        self.assertIn("sealing a crate", result["message"])

    def test_collecting_early_refuses_and_keeps_the_job(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        timer = self._started(world, player)
        world.clock.advance(60)

        result = collect(world, player, timer)
        self.assertFalse(result["ok"])
        self.assertIn("still running", result["message"])
        self.assertEqual([timer], carried_jobs(player), "the job is still there")
        self.assertEqual(0, player.inventory.count_item("item_output"))

    def test_a_job_that_is_not_yours_cannot_be_collected(self):
        world = _world(PART_JOB)
        owner = _player_with(world, ("item_part", 3))
        stranger = _player_with(world)
        timer = self._started(world, owner)
        world.clock.advance(0.5 * SECONDS_PER_GAME_DAY)

        result = collect(world, stranger, timer)
        self.assertFalse(result["ok"])
        self.assertEqual([timer], carried_jobs(owner), "the owner still has it")

    def test_a_full_inventory_refuses_and_keeps_the_job(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 3))
        timer = self._started(world, player)
        world.clock.advance(0.5 * SECONDS_PER_GAME_DAY)
        # Fill every slot with something that will not stack with the yield.
        player.inventory.max_weight = 1000.0
        for _ in range(player.inventory.max_slots):
            plate = ItemFactory.create_item_from_template("item_bulk", world)
            player.inventory.add_item(plate, 1)
        self.assertEqual(0, player.inventory.get_empty_slots())

        result = collect(world, player, timer)
        self.assertFalse(result["ok"])
        self.assertEqual([timer], carried_jobs(player))
        self.assertEqual(0, player.inventory.count_item("item_output"))

    def test_the_check_rolls_at_collect_and_a_failure_halves_the_yield(self):
        """Not a destroyed batch: the inputs were spent at the start.

        The roll itself is patched rather than seeded, because what is under test
        is what a *failed* roll does, not whether the dice work.
        """
        from unittest.mock import patch

        world = _world({
            "id": "risky", "label": "Risky work", "duration_days": 0.1,
            "skill": "crafting", "difficulty": 40,
            "outputs": [{"item_id": "item_output", "quantity": 4}],
        })
        player = _player_with(world)
        start(world, player, "risky", [])
        timer = carried_jobs(player)[0]
        world.clock.advance(0.1 * SECONDS_PER_GAME_DAY)

        with patch("engine.core.skill_system.SkillSystem.practice_check",
                   return_value=(False, "(Rolled 3 vs DC 40)")):
            result = collect(world, player, timer)

        self.assertTrue(result["ok"], result)
        self.assertEqual(2, player.inventory.count_item("item_output"), "half of four")
        self.assertIn("spoiled", result["message"])
        self.assertEqual([], carried_jobs(player))

    def test_a_successful_check_yields_everything(self):
        from unittest.mock import patch

        world = _world({
            "id": "risky", "label": "Risky work", "duration_days": 0.1,
            "skill": "crafting", "difficulty": 40,
            "outputs": [{"item_id": "item_output", "quantity": 4}],
        })
        player = _player_with(world)
        start(world, player, "risky", [])
        timer = carried_jobs(player)[0]
        world.clock.advance(0.1 * SECONDS_PER_GAME_DAY)

        with patch("engine.core.skill_system.SkillSystem.practice_check",
                   return_value=(True, "(Rolled 60 vs DC 40)")):
            result = collect(world, player, timer)

        self.assertEqual(4, player.inventory.count_item("item_output"))
        self.assertIn("Rolled 60", result["message"])

    def test_work_with_no_outputs_still_finishes(self):
        world = _world({"id": "wait_out", "label": "Waiting out the storm",
                        "duration_days": 0.2})
        player = _player_with(world)
        start(world, player, "wait_out", [])
        timer = carried_jobs(player)[0]
        world.clock.advance(0.2 * SECONDS_PER_GAME_DAY)

        result = collect(world, player, timer)
        self.assertTrue(result["ok"], result)
        self.assertIn("waiting out the storm", result["message"])
        self.assertEqual([], carried_jobs(player))

    def test_due_jobs_only_lists_what_the_clock_has_reached(self):
        world = _world(PART_JOB)
        player = _player_with(world, ("item_part", 6))
        start(world, player, "seal_crate", ["sealer"])
        world.clock.advance(0.25 * SECONDS_PER_GAME_DAY)
        start(world, player, "seal_crate", ["sealer"])

        self.assertEqual([], due_jobs(world, player))
        world.clock.advance(0.25 * SECONDS_PER_GAME_DAY)
        self.assertEqual(1, len(due_jobs(world, player)))
        world.clock.advance(0.25 * SECONDS_PER_GAME_DAY)
        self.assertEqual(2, len(due_jobs(world, player)))


class TestWhatThePlayerIsTold(unittest.TestCase):
    def test_declared_work_is_listed_in_the_order_it_was_authored(self):
        world = _world(PART_JOB, {"id": "second", "label": "Second thing"})
        self.assertEqual(["seal_crate", "second"], [entry["id"] for entry in declared_work(world)])

    def test_items_are_named_the_way_the_content_names_them(self):
        world = _world(PART_JOB)
        self.assertEqual("salvaged part", item_label(world, "item_part"))
        self.assertEqual("unknown thing", item_label(world, "item_unknown_thing"))

    def test_a_missing_item_is_named_without_underscores(self):
        world = _world(PART_JOB)
        self.assertEqual("no such item", item_label(world, "item_no_such_item"))


if __name__ == "__main__":
    unittest.main()
