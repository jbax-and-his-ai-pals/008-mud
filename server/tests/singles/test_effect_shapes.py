# tests/singles/test_effect_shapes.py
"""An effect's value is checked at authoring time, and an effect that fails says so.

The validator used to check an effect's *name* and the ids it referred to, never its
value. So `"set_flag": ["a", "b"]` set one flag literally called `['a', 'b']`;
`advance_quest` naming a quest template did nothing while reporting that it advanced
(active quests are keyed by instance); a `has_item` nested under `all` was never
checked against the items the set defines; one effect that raised stopped every effect
after it; and `give_gold: 0` was a silent no-op. `EFFECT_SHAPES` is the one description
of what each effect accepts, and the reader, the validator and the editor's vocabulary
dump all use it.
"""

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.dialogue import effects as effects_module
from engine.dialogue.effects import EFFECT_SHAPES, KNOWN_EFFECTS, apply_effects, effect_fields, effect_shape_issues
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class TestTheTable(unittest.TestCase):
    def test_it_describes_exactly_the_effects_the_reader_knows(self):
        self.assertEqual(set(KNOWN_EFFECTS), set(EFFECT_SHAPES))

    def test_the_object_shaped_effects_and_their_fields_are_what_the_editor_was_told(self):
        self.assertEqual({
            "adjust_relationship": ["amount", "delta", "npc"],
            "give_rewards": ["generated_item_data", "gold", "items", "xp"],
            "move_npc": ["message", "npc", "region", "room", "silent"],
            "raise": ["max_health", "max_mana", "stats"],
            "remove_npc": ["npc", "region", "room"],
            "restore": ["amount", "companions", "resource"],
            "reveal_exit": ["direction", "room"],
            "seal_exit": ["direction", "region", "room"],
            "advance_time": ["to_hour"],
            "spawn_npc": ["instance_id", "npc", "region", "room"],
            "teleport": ["message", "region", "room"],
            "set_respawn": ["region", "room"],
            "teach_companion": ["npc", "spell"],
            "place_vehicle": ["region", "room", "vehicle"],
        }, effect_fields())

    def test_each_object_effects_fields_are_the_ones_its_reader_reads(self):
        """The table is what the validator and the editor go by; the reader is what runs."""
        source = Path(effects_module.__file__).read_text(encoding="utf-8")
        readers = {
            "adjust_relationship": "_apply_relationship_effects",
            "move_npc": "_apply_move_npc_effect",
            "reveal_exit": "_apply_exit_effect",
            "give_rewards": "_apply_reward_effect",
            "restore": "_apply_restore_effect",
            "raise": "_apply_raise_effect",
            "spawn_npc": "_apply_spawn_npc_effect",
            "remove_npc": "_apply_remove_npc_effect",
            "teleport": "_apply_teleport_effect",
            "set_respawn": "_apply_set_respawn_effect",
            "teach_companion": "_apply_teach_companion_effect",
            "place_vehicle": "_apply_vehicle_effects",
            "seal_exit": "_apply_seal_exit_effect",
            "advance_time": "_apply_time_effect",
        }
        self.assertEqual(set(readers), set(effect_fields()))
        for effect, reader in readers.items():
            start = source.index("def %s(" % reader)
            end = source.find("\ndef ", start + 1)
            body = source[start:end if end != -1 else len(source)]
            read = set(re.findall(r'(?:raw|rewards)\.get\(\s*"([a-z_]+)"', body))
            with self.subTest(effect=effect):
                self.assertEqual(read, set(effect_fields()[effect]))


class TestShapeIssues(unittest.TestCase):
    GOOD = [
        {"set_flag": "door_open"},
        {"set_flag": ["door_open", "guard_alerted"]},
        {"set_flag": {"name": "door_open", "value": False}},
        {"set_flag": [{"name": "a"}, "b"]},
        {"start_quest": "q"}, {"start_quest": ["q", "r"]}, {"start_quest": [{"quest_id": "q"}]},
        {"advance_quest": True}, {"complete_quest": "q"},
        {"give_item": "item_x"}, {"give_item": ["item_x", {"item_id": "item_y", "quantity": 2}]},
        {"give_item": {"item_x": 2}}, {"take_item": {"item_x": 1, "item_y": 3}},
        {"give_gold": 5},
        {"adjust_relationship": 3}, {"adjust_relationship": {"npc": "elder", "amount": -2}},
        {"reveal_exit": {"room": "town:cellar", "direction": "down"}},
        {"move_npc": {"npc": "kessa", "region": "hazevale", "room": "village_square"}},
        {"move_npc": {"region": "hazevale", "room": "village_square"}},
        {"give_rewards": {"xp": 10, "gold": 5, "items": ["item_x", {"item_id": "item_y", "quantity": 2}]}},
        {"message": "The priestess smiles."},
        {"take_gold": 30}, {"forget_spell": "fireball"}, {"forget_spell": ["a", "b"]},
        {"restore": "health"}, {"restore": "mana"}, {"restore": "all"},
        {"restore": {"resource": "mana", "amount": 5}}, {"restore": {"resource": "health", "amount": "full"}},
        {"restore": {"amount": 5}},
        {"raise": {"max_health": 10}}, {"raise": {"max_mana": 4}}, {"raise": {"stats": {"strength": 1}}},
        {"raise": {"max_health": 10, "max_mana": 2, "stats": {"strength": 1, "dexterity": 2}}},
        {"spawn_npc": {"npc": "fiend", "region": "keep", "room": "hall"}},
        {"spawn_npc": {"npc": "fiend", "region": "keep", "room": "hall", "instance_id": "the_fiend"}},
        {"remove_npc": "chancellor"}, {"remove_npc": {"npc": "chancellor"}},
        {"remove_npc": {"npc": "chancellor", "region": "keep", "room": "hall"}},
        {"teleport": {"region": "keep", "room": "hall"}},
        {"seal_exit": {"region": "keep", "room": "hall", "direction": "east"}},
        {"advance_time": {"to_hour": 6}}, {"play_scene": "the_crystal_falls"},
    ]
    BAD = [
        ({"set_flag": 5}, "set_flag"), ({"set_flag": []}, "set_flag"), ({"set_flag": [3]}, "set_flag"),
        ({"set_flag": {"value": True}}, "set_flag"),
        ({"start_quest": 7}, "start_quest"), ({"start_quest": [""]}, "start_quest"),
        ({"advance_quest": False}, "advance_quest"),
        ({"give_item": 7}, "give_item"), ({"give_item": {"item_x": 0}}, "give_item"),
        ({"give_item": {"item_x": "two"}}, "give_item"),
        ({"give_gold": 0}, "give_gold"), ({"give_gold": [5]}, "give_gold"), ({"give_gold": True}, "give_gold"),
        ({"give_gold": "lots"}, "give_gold"),
        ({"adjust_relationship": "kind"}, "adjust_relationship"), ({"adjust_relationship": {"npc": "x"}}, "adjust_relationship"),
        ({"adjust_relationship": {"npc": "x", "amount": 1, "extra": 2}}, "extra"),
        ({"reveal_exit": "down"}, "reveal_exit"), ({"reveal_exit": {"room": "town:cellar"}}, "direction"),
        ({"move_npc": {"npc": "a", "room": "r"}}, "region"), ({"move_npc": {"region": "r", "room": "x", "where": 1}}, "where"),
        ({"give_rewards": {"xp": "lots"}}, "xp"), ({"give_rewards": {"exp": 5}}, "exp"), ({"give_rewards": [1]}, "give_rewards"),
        ({"message": ""}, "message"), ({"message": 5}, "message"), ({"message": ["a"]}, "message"),
        ({"take_gold": 0}, "take_gold"), ({"take_gold": "lots"}, "take_gold"), ({"take_gold": True}, "take_gold"),
        ({"forget_spell": 5}, "forget_spell"), ({"forget_spell": [""]}, "forget_spell"),
        ({"restore": "everything"}, "restore"), ({"restore": 5}, "restore"),
        ({"restore": {"resource": "gold"}}, "resource"), ({"restore": {"amount": 0}}, "amount"),
        ({"restore": {"amount": "half"}}, "amount"), ({"restore": {"resource": "health", "speed": 3}}, "speed"),
        ({"raise": {}}, "raise"), ({"raise": "health"}, "raise"),
        ({"raise": {"max_health": 0}}, "max_health"), ({"raise": {"max_health": -3}}, "max_health"),
        ({"raise": {"max_mana": "lots"}}, "max_mana"), ({"raise": {"stats": {}}}, "stats"),
        ({"raise": {"stats": {"strength": 0}}}, "stats"), ({"raise": {"stats": ["strength"]}}, "stats"),
        ({"raise": {"max_health": 5, "speed": 3}}, "speed"),
        ({"spawn_npc": "fiend"}, "spawn_npc"), ({"spawn_npc": {"npc": "fiend"}}, "region"),
        ({"spawn_npc": {"npc": "fiend", "region": "keep"}}, "room"),
        ({"spawn_npc": {"region": "keep", "room": "hall"}}, "npc"),
        ({"spawn_npc": {"npc": "fiend", "region": "keep", "room": "hall", "home": "x"}}, "home"),
        ({"spawn_npc": {"npc": "fiend", "region": "keep", "room": 5}}, "room"),
        ({"remove_npc": ""}, "remove_npc"), ({"remove_npc": 5}, "remove_npc"), ({"remove_npc": {}}, "npc"),
        ({"remove_npc": {"npc": "chancellor", "region": "keep"}}, "together"),
        ({"remove_npc": {"npc": "chancellor", "room": "hall"}}, "together"),
        ({"remove_npc": {"npc": "chancellor", "where": "hall"}}, "where"),
        ({"teleport": "hall"}, "teleport"), ({"teleport": {"region": "keep"}}, "room"),
        ({"seal_exit": "east"}, "seal_exit"), ({"seal_exit": {"region": "keep", "room": "hall"}}, "direction"),
        ({"seal_exit": {"region": "keep", "direction": "east"}}, "room"),
        ({"advance_time": {"to_hour": 24}}, "to_hour"), ({"advance_time": {"to_hour": "dawn"}}, "to_hour"), ({"advance_time": {}}, "to_hour"),
        ({"advance_time": 6}, "advance_time"), ({"play_scene": 5}, "play_scene"), ({"play_scene": ""}, "play_scene"),
        ({"teleport": {"room": "hall"}}, "region"), ({"teleport": {"region": "keep", "room": "hall", "how": 1}}, "how"),
    ]

    def test_a_valid_value_draws_no_issue(self):
        for block in self.GOOD:
            with self.subTest(block=block):
                self.assertEqual([], effect_shape_issues(block))

    def test_an_invalid_value_draws_an_issue_that_names_the_effect_or_the_field(self):
        for block, needle in self.BAD:
            with self.subTest(block=block):
                issues = effect_shape_issues(block)
                self.assertTrue(issues, "expected the shape to be refused")
                self.assertTrue(any(needle in issue for issue in issues), issues)

    def test_an_unknown_effect_is_not_this_checks_business(self):
        self.assertEqual([], effect_shape_issues({"summon_a_dragon": True}))


class TestRunning(GameTestBase):
    def _context(self):
        return {"player": self.player, "world": self.world}

    def test_set_flag_given_a_list_sets_every_flag_it_names(self):
        report = apply_effects({"set_flag": ["door_open", "guard_alerted"]}, self._context())
        self.assertIs(True, self.player.flags.get("door_open"))
        self.assertIs(True, self.player.flags.get("guard_alerted"))
        self.assertEqual([], report.failed)
        self.assertEqual(2, len([a for a in report.applied if a.startswith("flag ")]))

    def test_set_flag_given_a_mixed_list_keeps_each_entrys_own_value(self):
        apply_effects({"set_flag": [{"name": "quiet", "value": False}, "loud"]}, self._context())
        self.assertIs(False, self.player.flags.get("quiet"))
        self.assertIs(True, self.player.flags.get("loud"))

    def test_the_mapping_form_of_an_item_list_gives_the_quantities(self):
        apply_effects({"give_item": {"item_healing_potion_small": 3}}, self._context())
        self.assertEqual(3, self.player.inventory.count_item("item_healing_potion_small"))

    def test_give_gold_that_is_not_a_positive_whole_number_says_so(self):
        for value in (0, -3, "lots", [5]):
            with self.subTest(value=value):
                report = apply_effects({"give_gold": value}, self._context())
                self.assertTrue(any("give_gold" in failure for failure in report.failed), report.summary())

    def test_one_effect_that_raises_does_not_stop_the_ones_after_it(self):
        with mock.patch.object(effects_module, "_apply_item_effects", side_effect=RuntimeError("boom")):
            report = apply_effects({"give_item": "item_healing_potion_small", "set_flag": "still_ran"}, self._context())
        self.assertIs(True, self.player.flags.get("still_ran"))
        self.assertTrue(any("boom" in failure for failure in report.failed), report.summary())

    def test_advance_quest_naming_a_template_advances_the_active_instance(self):
        self.world.quest_manager.quest_templates["stepped"] = {
            "title": "Stepped", "type": "quest",
            "stages": [
                {"stage_index": 0, "description": "one", "objective": {"type": "fetch", "item_id": "x", "required_quantity": 1}, "turn_in_id": "npc"},
                {"stage_index": 1, "description": "two", "objective": {"type": "fetch", "item_id": "y", "required_quantity": 1}, "turn_in_id": "npc"},
            ],
        }
        self.assertTrue(self.world.quest_manager.start_quest("stepped", self.player))
        instance = next(key for key in self.player.runtime_state.quests.active if key.startswith("stepped"))
        report = apply_effects({"advance_quest": "stepped"}, self._context())
        self.assertEqual(1, self.player.runtime_state.quests.active[instance]["current_stage_index"])
        self.assertEqual([], report.failed)

    def test_advance_quest_naming_a_quest_that_is_not_active_reports_a_failure_not_success(self):
        report = apply_effects({"advance_quest": "a_quest_nobody_started"}, self._context())
        self.assertTrue(any("a_quest_nobody_started" in failure for failure in report.failed), report.summary())
        self.assertFalse(any(applied.startswith("advanced") for applied in report.applied))


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing only its hermit's conversation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.graph = self.package / "data" / "dialogue" / "hermit_gift.json"

    def _errors(self, edit):
        payload = json.loads(self.graph.read_text(encoding="utf-8"))
        edit(payload)
        self.graph.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [issue.message for issue in issues if issue.severity == "error"]

    def _choice(self, payload):
        return payload["nodes"]["greeting"]["choices"][0]

    def test_a_flag_given_as_a_number_is_refused(self):
        errors = self._errors(lambda p: self._choice(p)["effects"].update({"set_flag": 5}))
        self.assertTrue(any("set_flag" in m and "hermit_gift" in m for m in errors), errors)

    def test_a_list_of_flags_is_accepted(self):
        errors = self._errors(lambda p: self._choice(p)["effects"].update({"set_flag": ["got_the_sword", "met_the_hermit"]}))
        self.assertEqual([], [m for m in errors if "hermit_gift" in m], errors)

    def test_gold_that_is_not_a_positive_whole_number_is_refused(self):
        errors = self._errors(lambda p: self._choice(p)["effects"].update({"give_gold": [10]}))
        self.assertTrue(any("give_gold" in m for m in errors), errors)

    def test_an_item_nested_under_all_is_checked_against_the_items_the_set_defines(self):
        def nest(payload):
            self._choice(payload)["condition"] = {"all": [{"kind": "has_item", "item_id": "item_nobody_authored"}]}
        errors = self._errors(nest)
        self.assertTrue(any("item_nobody_authored" in m for m in errors), errors)

    def test_an_item_nested_under_not_and_any_is_checked_too(self):
        def nest(payload):
            self._choice(payload)["condition"] = {"any": [{"not": {"kind": "has_item", "item_id": "item_missing_a"}}]}
        errors = self._errors(nest)
        self.assertTrue(any("item_missing_a" in m for m in errors), errors)


if __name__ == "__main__":
    unittest.main()
