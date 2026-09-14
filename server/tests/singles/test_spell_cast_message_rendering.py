# tests/singles/test_spell_cast_message_rendering.py
"""Spell.format_cast_message() only ever supplies caster_name/spell_name
(engine/magic/spell.py:50-51) and is called with no try/except at either
call site (engine/npcs/combat.py, engine/player/magic.py) -- a
cast_message referencing any other placeholder (e.g. offensive_spells.json's
"immolate" used to reference {target_name}) raises an unhandled KeyError
the moment anyone casts that spell. This proves every registered spell's
cast_message renders cleanly against the two keys the engine actually
supplies."""

import unittest

from tests.fixtures import make_test_server
from engine.magic import spell_registry


class _StubCaster:
    name = "Test Caster"


class TestSpellCastMessageRendering(unittest.TestCase):
    def test_every_registered_spells_cast_message_formats_cleanly(self) -> None:
        server = make_test_server()
        try:
            self.assertGreater(len(spell_registry.SPELL_REGISTRY), 0)
            failures = []
            for spell_id, spell in spell_registry.SPELL_REGISTRY.items():
                try:
                    spell.format_cast_message(_StubCaster())
                except (KeyError, IndexError) as exc:
                    failures.append(f"{spell_id}: cast_message {spell.cast_message!r} raised {exc!r}")
            self.assertEqual([], failures)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
