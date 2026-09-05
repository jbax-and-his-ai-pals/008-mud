# tests/singles/test_spell_model.py
"""Coverage for engine/magic/spell.py: the effects-validation guard,
can_cast()'s runtime_state-present vs. plain-object fallback paths, and
to_dict()'s serialization."""

import unittest
from types import SimpleNamespace

from engine.magic.spell import Spell


def _spell(**overrides):
    kwargs = dict(
        spell_id="probe_spell", name="Probe Spell", description="A test spell.",
        effects=[{"type": "damage", "value": 5}],
    )
    kwargs.update(overrides)
    return Spell(**kwargs)


class TestSpellValidation(unittest.TestCase):
    def test_none_effects_raises(self):
        with self.assertRaises(ValueError):
            _spell(effects=None)

    def test_empty_effects_raises(self):
        with self.assertRaises(ValueError):
            _spell(effects=[])

    def test_non_dict_effect_raises(self):
        with self.assertRaises(ValueError):
            _spell(effects=["not a dict"])

    def test_effect_missing_type_raises(self):
        with self.assertRaises(ValueError):
            _spell(effects=[{"value": 5}])


class TestCanCast(unittest.TestCase):
    def test_true_when_runtime_state_progression_level_meets_requirement(self):
        spell = _spell(level_required=5)
        caster = SimpleNamespace(runtime_state=SimpleNamespace(progression=SimpleNamespace(level=5)))
        self.assertTrue(spell.can_cast(caster))

    def test_false_when_runtime_state_progression_level_below_requirement(self):
        spell = _spell(level_required=5)
        caster = SimpleNamespace(runtime_state=SimpleNamespace(progression=SimpleNamespace(level=1)))
        self.assertFalse(spell.can_cast(caster))

    def test_falls_back_to_plain_level_attribute_without_runtime_state(self):
        spell = _spell(level_required=5)
        caster = SimpleNamespace(level=10)
        self.assertTrue(spell.can_cast(caster))

    def test_falls_back_to_default_level_one_without_level_attribute(self):
        spell = _spell(level_required=1)
        caster = SimpleNamespace()
        self.assertTrue(spell.can_cast(caster))


class TestToDict(unittest.TestCase):
    def test_serializes_expected_fields(self):
        spell = _spell(spell_id="fireball", name="Fireball", mana_cost=15, cooldown=8.0,
                        target_type="enemy", level_required=3)
        data = spell.to_dict()
        self.assertEqual(data["spell_id"], "fireball")
        self.assertEqual(data["name"], "Fireball")
        self.assertEqual(data["mana_cost"], 15)
        self.assertEqual(data["cooldown"], 8.0)
        self.assertEqual(data["target_type"], "enemy")
        self.assertEqual(data["level_required"], 3)
        self.assertEqual(data["effects"], spell.effects)


if __name__ == "__main__":
    unittest.main()
