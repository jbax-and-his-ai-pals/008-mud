# tests/singles/test_spell_default_damage_type.py
"""The damage channel a spell deals when it does not declare one.

Every content set already declares its own `combat/elements.json`
`default_damage_type`, and the engine ignored all of them: the fallback was the
string `"magical"`, written into `magic/effects.py` by hand. A sci-fi set whose
channels are `kinetic`/`thermal` therefore dealt `magical` damage, which is not
one of its channels at all -- and nothing could report it, because a damage type
that matches no flavour entry falls back to the generic message and looks fine.

The default is read at world construction, after every module has imported the
config, so it is held in a mutable cell and read through a function. A module
level string would freeze at the built-in value, which is the same bug wearing a
different hat.
"""
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.config.config_combat import (
    configure_combat_elements,
    spell_default_damage_type,
)
from engine.magic.effects import apply_spell_effect
from engine.magic.spell import Spell


REPO_ROOT = Path(__file__).resolve().parents[3]
ORBITAL_DATA = str(REPO_ROOT / "content_sets" / "orbital_salvage" / "data")
NO_ELEMENTS_DATA = str(REPO_ROOT / "content_sets" / "modern_capsule" / "data")


def _damage_spell(damage_type=None):
    effect = {"type": "damage", "value": 10}
    if damage_type is not None:
        effect["damage_type"] = damage_type
    return Spell(spell_id="probe", name="Probe", description="test", effects=[effect])


class TestTheDefaultComesFromContent(GameTestBase):
    def test_configuring_a_set_replaces_the_built_in_default(self):
        configure_combat_elements(ORBITAL_DATA)
        self.addCleanup(configure_combat_elements, self.world.content_root)

        self.assertEqual("kinetic", spell_default_damage_type())

    def test_a_set_with_no_elements_file_keeps_the_built_in_default(self):
        configure_combat_elements(NO_ELEMENTS_DATA)
        self.addCleanup(configure_combat_elements, self.world.content_root)

        # Nothing to read, so the engine's own fallback stands rather than a
        # blank string, which would reach `take_damage` and match no resistance.
        self.assertTrue(spell_default_damage_type())


class TestASpellThatDeclaresNothingUsesIt(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.stats["intelligence"] = 10
        self.player.stats["spell_power"] = 0

    def _channel_dealt(self, spell):
        """The damage_type the spell actually handed to `take_damage`."""
        with patch.object(type(self.player), "take_damage", return_value=1) as dealt:
            with patch("random.uniform", return_value=0.0):
                apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertTrue(dealt.called, "the spell never dealt damage")
        return dealt.call_args.kwargs.get("damage_type")

    def test_an_undeclared_channel_is_the_sets_default(self):
        configure_combat_elements(ORBITAL_DATA)
        self.addCleanup(configure_combat_elements, self.world.content_root)

        self.assertEqual("kinetic", self._channel_dealt(_damage_spell()))

    def test_a_declared_channel_still_wins(self):
        configure_combat_elements(ORBITAL_DATA)
        self.addCleanup(configure_combat_elements, self.world.content_root)

        self.assertEqual("thermal", self._channel_dealt(_damage_spell("thermal")))

    def test_a_declared_channel_that_is_empty_is_not_a_declaration(self):
        """`damage_type: ""` is how a UI clears the field, not a channel."""
        configure_combat_elements(ORBITAL_DATA)
        self.addCleanup(configure_combat_elements, self.world.content_root)

        self.assertEqual("kinetic", self._channel_dealt(_damage_spell("")))
