"""Coverage for toolkit/template_placeholder_validator.py."""

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import template_placeholder_validator as tpv


class TestLiveContentSetsHaveNoTemplateIssues(unittest.TestCase):
    def test_fantasy_frontier_has_no_template_issues(self) -> None:
        issues = tpv.validate_content_set(REPO_ROOT / "content_sets" / "fantasy_frontier")
        self.assertEqual([], [i for i in issues if i.severity == "error"])

    def test_modern_capsule_has_no_template_issues(self) -> None:
        issues = tpv.validate_content_set(REPO_ROOT / "content_sets" / "modern_capsule")
        self.assertEqual([], [i for i in issues if i.severity == "error"])

    def test_night_shift_has_no_template_issues(self) -> None:
        issues = tpv.validate_content_set(REPO_ROOT / "content_sets" / "night_shift")
        self.assertEqual([], [i for i in issues if i.severity == "error"])

    def test_orbital_salvage_has_no_template_issues(self) -> None:
        issues = tpv.validate_content_set(REPO_ROOT / "content_sets" / "orbital_salvage")
        self.assertEqual([], [i for i in issues if i.severity == "error"])


class _CaseRootMixin:
    def _case_root(self) -> Path:
        root = Path("tmp") / f"template_placeholder_test_{uuid.uuid4().hex}"
        (root / "data" / "npcs").mkdir(parents=True, exist_ok=True)
        (root / "data" / "magic").mkdir(parents=True, exist_ok=True)
        (root / "data" / "items").mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write(self, path: Path, payload) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


class TestNpcDialogChecks(_CaseRootMixin, unittest.TestCase):
    def test_unformatted_dialog_field_with_placeholder_is_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "npcs" / "hostiles.json", {
            "wolf": {"dialog": {"greeting": "{name} growls menacingly!"}},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual(1, len(issues))
        self.assertIn("dialog.greeting", issues[0].path)

    def test_trade_field_with_known_placeholder_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "npcs" / "villagers.json", {
            "merchant": {"dialog": {"trade": "What can I get for you, traveler? -{name}"}},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)

    def test_default_dialog_with_known_placeholder_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "npcs" / "villagers.json", {
            "merchant": {"default_dialog": "The {name} nods."},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)

    def test_greeting_extended_with_wrong_key_is_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "npcs" / "quest_npcs.json", {
            "worried_homeowner": {"dialog": {"greeting_extended": "It's over at the {wrong_key}."}},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual(1, len(issues))
        self.assertIn("dialog.greeting_extended", issues[0].path)

    def test_plain_dialog_with_no_placeholder_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "npcs" / "hostiles.json", {
            "wolf": {"dialog": {"greeting": "The wolf growls menacingly!"}},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)


class TestSpellMessageChecks(_CaseRootMixin, unittest.TestCase):
    def test_cast_message_referencing_unsupplied_target_name_is_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "magic" / "offensive_spells.json", {
            "immolate": {"cast_message": "{caster_name} burns {target_name}!"},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual(1, len(issues))
        self.assertIn("immolate.cast_message", issues[0].path)

    def test_well_formed_hit_message_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "magic" / "offensive_spells.json", {
            "zap": {"hit_message": "{caster_name} zaps {target_name} for {value} {damage_type} damage!"},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)


class TestProceduralItemAndAffixChecks(_CaseRootMixin, unittest.TestCase):
    def test_procedural_item_name_with_wrong_key_is_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "items" / "consumables.json", {
            "item_scroll_random": {
                "name": "Scroll of {spell_id}",
                "properties": {"is_procedural": True},
            },
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual(1, len(issues))
        self.assertIn("item_scroll_random.name", issues[0].path)

    def test_non_procedural_item_with_brace_in_name_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "items" / "consumables.json", {
            "item_odd_name": {"name": "Not a template {ignored}"},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)

    def test_affix_pattern_with_correct_key_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write(root / "data" / "items" / "affixes.json", {
            "affix_flaming": {"generated_effect_name_pattern": "Enchantment of {item_name}"},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)


class TestQuestTextTemplateChecks(_CaseRootMixin, unittest.TestCase):
    def _write_ruleset(self, root: Path, text_templates: dict) -> None:
        self._write(root / "rules" / "ruleset.json", {
            "quest_generation": {"text_templates": text_templates},
        })

    def test_deliver_template_missing_a_referenced_key_is_flagged(self) -> None:
        root = self._case_root()
        self._write_ruleset(root, {
            "deliver": {"title": "Delivery: {item_to_deliver_name} via {unsupported_key}"},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual(1, len(issues))
        self.assertIn("deliver.title", issues[0].path)

    def test_well_formed_kill_template_is_not_flagged(self) -> None:
        root = self._case_root()
        self._write_ruleset(root, {
            "kill": {"description": "{giver_name} needs {quantity} {target_name_plural} dealt with, found in {location_description}."},
        })
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)

    def test_missing_ruleset_file_is_not_an_error(self) -> None:
        root = self._case_root()
        issues = tpv.validate_content_set(root)
        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
