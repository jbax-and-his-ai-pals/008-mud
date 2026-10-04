"""One definition of each dialogue condition kind and effect: the engine's.

The label, hint and field kinds an author sees are defined next to the code that evaluates each kind
(`CONDITION_SPECS`, `EFFECT_EDITOR`); the editor's tables in `DialogueSchema.gd` are generated from them by
`toolkit/sync_editor_vocabulary.py` and the validator's reference tables are derived. These pin that: a spec added
without regenerating fails here, with the command to run.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import conditions
from engine.dialogue import effects
from engine.server import content_set
from toolkit import sync_editor_vocabulary as sync


class TestTheEnginesDefinitionIsTheOnlyOne(unittest.TestCase):
    def test_the_editors_tables_are_the_generated_ones(self) -> None:
        current = sync.SCHEMA.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(
            sync.regenerate(current), current,
            "DialogueSchema.gd's tables are out of date: run  python toolkit/sync_editor_vocabulary.py",
        )

    def test_a_new_kind_in_the_engine_shows_up_in_what_the_editor_would_get(self) -> None:
        extra = dict(conditions.CONDITION_SPECS)
        extra["probe_kind"] = {"label": "Probe", "fields": {"value": "int"}, "note": "for the test"}
        with patch.object(conditions, "CONDITION_SPECS", extra):
            self.assertIn('"probe_kind"', sync.condition_table())
        self.assertNotIn('"probe_kind"', sync.condition_table())

    def test_the_kinds_and_effects_are_the_specs(self) -> None:
        self.assertEqual(set(conditions.CONDITION_SPECS), set(conditions.KNOWN_KINDS))
        self.assertEqual(set(effects.EFFECT_EDITOR), set(effects.KNOWN_EFFECTS))

    def test_the_validators_reference_tables_come_from_them(self) -> None:
        self.assertIn(("has_item", "item_id", "items"), content_set._CONDITION_REFERENCES)
        self.assertIn(("companion_present", "npc_id", "npcs"), content_set._CONDITION_REFERENCES)
        self.assertIn(("give_item", "items"), effects.effect_references())
        self.assertIn(("recruit", "npcs"), effects.effect_references())
        for kind, field, bucket in content_set._CONDITION_REFERENCES:
            self.assertIn(field, conditions.CONDITION_SPECS[kind]["fields"], "%s.%s is a field of its kind" % (kind, field))


if __name__ == "__main__":
    unittest.main()
