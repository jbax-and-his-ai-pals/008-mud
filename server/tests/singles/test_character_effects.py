# tests/singles/test_character_effects.py
"""Dialogue and items can change the character, not just hand it things.

Before this, no effect could heal, spend gold, raise maximum health or a stat, or
make a character forget a spell: a heart container could only heal, an inn could
not charge, and a class change was a title that granted nothing. `restore`,
`raise`, `take_gold`, `forget_spell` and `message` close that, and a consumable
item can run any effects mapping (`effect_type: "effects"`).

`raise` is a power channel outside levelling, so the validator warns on one that
can be repeated or is large: a heart container is treasure, not a menu.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import KNOWN_EFFECTS, RAISE_LARGE, apply_effects
from engine.items.consumable import CONSUMABLE_EFFECT_TYPES, Consumable
from engine.player.core import Player
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Effects(GameTestBase):
    def apply(self, effects):
        return apply_effects(effects, {"player": self.player, "world": self.world})

    def numeric_stat(self):
        return next(name for name, value in self.player.stats.items()
                    if isinstance(value, int) and not isinstance(value, bool))


class TestTheVocabulary(unittest.TestCase):
    def test_the_new_effects_are_known(self):
        for name in ("message", "restore", "raise", "take_gold", "forget_spell"):
            self.assertIn(name, KNOWN_EFFECTS)

    def test_a_consumable_can_run_effects(self):
        self.assertIn("effects", CONSUMABLE_EFFECT_TYPES)

    def test_the_consumable_effect_types_are_the_ones_use_dispatches_on(self):
        import re
        import engine.items.consumable as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        dispatched = set(re.findall(r'effect_type == "([a-z_]+)"', source))
        self.assertEqual(dispatched, set(CONSUMABLE_EFFECT_TYPES))


class TestRestore(_Effects):
    def test_health_is_filled(self):
        self.player.health = 1
        report = self.apply({"restore": "health"})
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertTrue(any("health" in entry for entry in report.applied), report.summary())
        self.assertIn("recover", report.message())

    def test_an_amount_restores_that_much_and_no_more_than_the_maximum(self):
        self.player.health = 1
        self.apply({"restore": {"resource": "health", "amount": 5}})
        self.assertEqual(6, self.player.health)
        self.apply({"restore": {"resource": "health", "amount": 10 ** 6}})
        self.assertEqual(self.player.max_health, self.player.health)

    def test_full_health_is_reported_as_nothing_to_do_not_as_success(self):
        self.player.health = self.player.max_health
        report = self.apply({"restore": "health"})
        self.assertEqual([], report.applied)
        self.assertTrue(report.unchanged, report.summary())
        self.assertEqual([], report.failed)

    def test_the_ability_pool_is_filled(self):
        magic = self.player.runtime_state.magic
        magic.mana = 0
        report = self.apply({"restore": "mana"})
        self.assertEqual(magic.max_mana, magic.mana)
        self.assertTrue(report.applied, report.summary())

    def test_all_fills_both(self):
        magic = self.player.runtime_state.magic
        self.player.health, magic.mana = 1, 0
        self.apply({"restore": "all"})
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(magic.max_mana, magic.mana)

    def test_a_game_with_no_ability_pool_says_so_for_mana_and_shrugs_for_all(self):
        self.player.runtime_state.magic = None
        self.player.health = 1
        self.assertTrue(self.apply({"restore": "mana"}).failed)
        report = self.apply({"restore": "all"})
        self.assertEqual([], report.failed)
        self.assertEqual(self.player.max_health, self.player.health)


class TestRaise(_Effects):
    def test_maximum_health_rises_and_so_does_current_health(self):
        before, health = self.player.max_health, self.player.health
        report = self.apply({"raise": {"max_health": 10}})
        self.assertEqual(before + 10, self.player.max_health)
        self.assertEqual(health + 10, self.player.health, "a heart container is felt at once")
        self.assertIn("maximum health", report.message().lower())

    def test_the_ability_pool_rises(self):
        magic = self.player.runtime_state.magic
        before, mana = magic.max_mana, magic.mana
        self.apply({"raise": {"max_mana": 4}})
        self.assertEqual(before + 4, magic.max_mana)
        self.assertEqual(mana + 4, magic.mana)

    def test_a_stat_rises(self):
        stat = self.numeric_stat()
        before = self.player.stats[stat]
        self.apply({"raise": {"stats": {stat: 2}}})
        self.assertEqual(before + 2, self.player.stats[stat])

    def test_a_stat_the_character_does_not_have_is_reported_and_changes_nothing(self):
        before = dict(self.player.stats)
        report = self.apply({"raise": {"stats": {"charisma_of_the_moon": 1}}})
        self.assertTrue(any("charisma_of_the_moon" in failure for failure in report.failed), report.summary())
        self.assertEqual(before, self.player.stats)

    def test_a_pool_the_game_does_not_have_is_reported(self):
        self.player.runtime_state.magic = None
        report = self.apply({"raise": {"max_mana": 4}})
        self.assertTrue(report.failed, report.summary())

    def test_what_was_raised_survives_a_save(self):
        stat = self.numeric_stat()
        self.apply({"raise": {"max_health": 10, "max_mana": 3, "stats": {stat: 1}}})
        before = (self.player.max_health, self.player.runtime_state.magic.max_mana, self.player.stats[stat])
        data = json.loads(json.dumps(self.player.to_dict(self.world)))
        again = Player.from_dict(data, self.world)
        self.assertEqual(before, (again.max_health, again.runtime_state.magic.max_mana, again.stats[stat]))


class TestMessageGoldAndForgetting(_Effects):
    def test_a_message_is_shown_first(self):
        report = self.apply({"give_gold": 5, "message": "The priestess smiles."})
        self.assertEqual("The priestess smiles.", report.messages[0])

    def test_gold_is_taken(self):
        self.player.runtime_state.gold = 50
        report = self.apply({"take_gold": 30})
        self.assertEqual(20, self.player.runtime_state.gold)
        self.assertTrue(report.applied, report.summary())

    def test_gold_the_character_does_not_have_is_not_taken_and_is_reported(self):
        self.player.runtime_state.gold = 10
        report = self.apply({"take_gold": 30})
        self.assertEqual(10, self.player.runtime_state.gold, "no partial payment")
        self.assertTrue(any("take_gold" in failure for failure in report.failed), report.summary())

    def test_a_service_is_paid_for_before_it_is_delivered(self):
        self.player.runtime_state.gold = 50
        self.player.health = 1
        self.apply({"restore": "health", "take_gold": 30})
        self.assertEqual(20, self.player.runtime_state.gold)
        self.assertEqual(self.player.max_health, self.player.health)

    def test_a_spell_is_forgotten(self):
        magic = self.player.runtime_state.magic
        spell_id = self._spell_ids()[0]
        magic.known_spells.add(spell_id)
        report = self.apply({"forget_spell": spell_id})
        self.assertNotIn(spell_id, magic.known_spells)
        self.assertTrue(report.applied, report.summary())

    def test_forgetting_a_spell_not_known_is_nothing_to_do(self):
        report = self.apply({"forget_spell": "a_spell_never_learned"})
        self.assertEqual([], report.applied)
        self.assertTrue(report.unchanged, report.summary())

    def test_forgetting_comes_before_learning_so_a_swap_works(self):
        magic = self.player.runtime_state.magic
        first, second = self._spell_ids()[:2]
        magic.known_spells.add(first)
        self.apply({"forget_spell": first, "teach_spell": second})
        self.assertNotIn(first, magic.known_spells)
        self.assertIn(second, magic.known_spells)

    def _spell_ids(self):
        from engine.magic.spell_registry import SPELL_REGISTRY
        return sorted(SPELL_REGISTRY)


class TestConsumablesRunEffects(_Effects):
    def potion(self, effects, **kwargs):
        return Consumable(obj_id="probe", name="Elixir", uses=1, effect_type="effects", effects=effects, **kwargs)

    def test_the_effects_run_and_the_item_is_used_up(self):
        self.player.health = 1
        item = self.potion({"restore": "health", "message": "Warmth spreads."})
        result = item.use(self.player)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertIn("Warmth spreads.", result)
        self.assertEqual(0, item.get_property("uses"))

    def test_an_item_that_did_nothing_is_not_spent(self):
        self.player.health = self.player.max_health
        item = self.potion({"restore": "health"})
        result = item.use(self.player)
        self.assertEqual(1, item.get_property("uses"))
        self.assertIn("nothing happens", result.lower())

    def test_a_heart_container_raises_and_heals(self):
        before = self.player.max_health
        item = self.potion({"raise": {"max_health": 10}, "restore": "health"})
        item.use(self.player)
        self.assertEqual(before + 10, self.player.max_health)
        self.assertEqual(before + 10, self.player.health)

    def test_an_item_with_no_effects_is_inert_and_kept(self):
        item = self.potion({})
        result = item.use(self.player)
        self.assertEqual(1, item.get_property("uses"))
        self.assertIn("inert", result.lower())


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing only one conversation and one item."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.graph = self.package / "data" / "dialogue" / "hermit_gift.json"

    def _issues(self, edit):
        payload = json.loads(self.graph.read_text(encoding="utf-8"))
        edit(payload)
        self.graph.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [issue for issue in issues if "hermit_gift" in issue.message]

    def _choice(self, payload):
        return payload["nodes"]["greeting"]["choices"][0]

    def _messages(self, edit, severity):
        return [issue.message for issue in self._issues(edit) if issue.severity == severity]

    def _set(self, effects, condition=None):
        def edit(payload):
            choice = self._choice(payload)
            choice["effects"] = effects
            if condition is None:
                choice.pop("condition", None)
            else:
                choice["condition"] = condition
        return edit

    NOT_YET = {"not": {"kind": "flag", "flag": "took_the_blessing"}}

    def test_a_raise_that_can_be_repeated_draws_a_warning(self):
        warnings = self._messages(self._set({"raise": {"max_health": 5}}), "warning")
        self.assertTrue(any("raise" in m and "repeat" in m for m in warnings), warnings)

    def test_a_raise_behind_a_flag_it_sets_draws_none(self):
        edit = self._set({"raise": {"max_health": 5}, "set_flag": "took_the_blessing"}, self.NOT_YET)
        self.assertEqual([], [m for m in self._messages(edit, "warning") if "raise" in m])

    def test_a_large_raise_draws_a_warning_even_when_guarded(self):
        big = RAISE_LARGE["max_health"] + 1
        edit = self._set({"raise": {"max_health": big}, "set_flag": "took_the_blessing"}, self.NOT_YET)
        self.assertTrue(any("raise" in m and "large" in m for m in self._messages(edit, "warning")))

    def test_a_raise_in_a_nodes_own_effects_draws_a_warning(self):
        def edit(payload):
            payload["nodes"]["greeting"]["effects"] = {"raise": {"max_health": 5}}
        self.assertTrue(any("raise" in m for m in self._messages(edit, "warning")))

    def test_taking_gold_with_no_guard_draws_a_warning(self):
        warnings = self._messages(self._set({"take_gold": 30, "restore": "all"}), "warning")
        self.assertTrue(any("take_gold" in m and "gold_at_least" in m for m in warnings), warnings)

    def test_taking_gold_behind_a_gold_check_draws_none(self):
        edit = self._set({"take_gold": 30, "restore": "all"}, {"kind": "gold_at_least", "value": 30})
        self.assertEqual([], [m for m in self._messages(edit, "warning") if "take_gold" in m])

    def test_a_guard_nested_under_all_counts(self):
        condition = {"all": [{"kind": "gold_at_least", "value": 30}, self.NOT_YET]}
        edit = self._set({"take_gold": 30, "restore": "all"}, condition)
        self.assertEqual([], [m for m in self._messages(edit, "warning") if "take_gold" in m])

    def test_the_new_effects_are_shape_checked_in_a_conversation(self):
        errors = self._messages(self._set({"restore": "everything"}), "error")
        self.assertTrue(any("restore" in m for m in errors), errors)
        errors = self._messages(self._set({"raise": {"max_health": 0}}), "error")
        self.assertTrue(any("raise" in m for m in errors), errors)

    def test_a_stat_named_in_a_raise_must_exist_in_this_set(self):
        errors = self._messages(self._set({"raise": {"stats": {"charisma_of_the_moon": 1}}, "set_flag": "x"}), "error")
        self.assertTrue(any("charisma_of_the_moon" in m for m in errors), errors)

    # -- a consumable that runs effects -----------------------------------------

    def _item_issues(self, properties):
        items = self.package / "data" / "items"
        target = sorted(items.glob("*.json"))[0]
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["probe_elixir"] = {
            "name": "Elixir", "description": "A probe.", "type": "Consumable", "weight": 0.1, "value": 1,
            "properties": properties,
        }
        target.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [issue for issue in issues if "probe_elixir" in issue.message]

    def test_an_effects_consumable_with_good_effects_is_accepted(self):
        issues = self._item_issues({"effect_type": "effects", "uses": 1, "effects": {"restore": "health"}})
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])

    def test_an_effects_consumable_needs_effects(self):
        issues = self._item_issues({"effect_type": "effects", "uses": 1})
        self.assertTrue(any("effects" in i.message and i.severity == "error" for i in issues), [i.message for i in issues])

    def test_the_effects_of_a_consumable_are_checked_like_a_conversations(self):
        issues = self._item_issues({"effect_type": "effects", "effects": {"give_gold": 0, "summon_a_dragon": True}})
        text = " ".join(i.message for i in issues if i.severity == "error")
        self.assertIn("give_gold", text)
        self.assertIn("summon_a_dragon", text)

    def test_an_effect_type_nothing_executes_draws_a_warning(self):
        """A consumable with such a type does nothing and is used up doing it. A warning, so
        a set that carries one still boots; the shipped fantasy set's fungus was one."""
        issues = self._item_issues({"effect_type": "heal_a_lot", "uses": 1})
        self.assertTrue(any("heal_a_lot" in i.message and i.severity == "warning" for i in issues), [i.message for i in issues])
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])

    def test_effects_on_a_consumable_that_does_not_run_them_draws_a_warning(self):
        issues = self._item_issues({"effect_type": "heal", "effect_value": 5, "effects": {"restore": "health"}})
        self.assertTrue(any("effects" in i.message and i.severity == "warning" for i in issues), [i.message for i in issues])


if __name__ == "__main__":
    unittest.main()
