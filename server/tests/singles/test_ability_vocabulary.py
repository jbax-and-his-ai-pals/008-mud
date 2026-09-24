"""The ability vocabulary constants are what the engine actually does.

`ABILITY_EFFECT_FIELDS` must name exactly the effect types `apply_spell_effect`
executes, and exactly the effect keys it reads; `ABILITY_TARGET_TYPES` exactly
the target types the cast command resolves; `ABILITY_MESSAGE_PLACEHOLDERS` the
names each message is formatted with. The validator refuses content by these,
and the editor offers them (schema_parity_smoke.gd).
"""
import inspect
import re
import unittest

from engine.commands import magic as magic_command
from engine.magic import effects, spell
from engine.magic.spell import (
    ABILITY_EFFECT_FIELDS, ABILITY_MESSAGE_PLACEHOLDERS, ABILITY_TARGET_TYPES, Spell,
)


def _arguments(source: str, start: int) -> str:
    """A call's argument text, from just after its opening parenthesis."""
    depth = 1
    for index in range(start, len(source)):
        depth += {"(": 1, ")": -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index]
    return source[start:]


class TestAbilityVocabulary(unittest.TestCase):
    def setUp(self):
        self.executor = inspect.getsource(effects.apply_spell_effect)

    def test_effect_types_are_the_ones_the_executor_runs(self):
        executed = set(re.findall(r'eff_type == "([a-z_]+)"', self.executor))
        executed |= set(re.findall(r'has_effect_type\("([a-z_]+)"\)', self.executor))
        for group in re.findall(r'eff_type in \[([^\]]+)\]', self.executor):
            executed |= set(re.findall(r'"([a-z_]+)"', group))
        self.assertEqual(set(ABILITY_EFFECT_FIELDS), executed)

    def test_effect_keys_are_the_ones_the_executor_reads(self):
        read = set(re.findall(r'effect_def(?:\.get\(|\[)"([a-z_]+)"', self.executor)) - {"type"}
        declared = {"damage_type"} | {key for fields in ABILITY_EFFECT_FIELDS.values() for key in fields}
        self.assertEqual(declared, read)

    def test_target_types_are_the_ones_the_cast_command_resolves(self):
        source = inspect.getsource(magic_command.cast_handler)
        resolved = set(re.findall(r'target_type (?:==|!=) "([a-z_]+)"', source))
        self.assertEqual(set(ABILITY_TARGET_TYPES), resolved)

    def test_message_placeholders_are_the_ones_each_message_is_formatted_with(self):
        sources = inspect.getsource(effects) + inspect.getsource(spell)
        for key, names in ABILITY_MESSAGE_PLACEHOLDERS.items():
            # The heal messages are picked into `msg` first and formatted there.
            picked = re.search(r'msg = spell\.%s if' % key, sources) or re.search(r'else spell\.%s\b' % key, sources)
            pattern = r'msg\.format\(' if picked else r'\b%s\.format\(' % key
            calls = [_arguments(sources, match.end()) for match in re.finditer(pattern, sources)]
            self.assertTrue(calls, key)
            for call in calls:
                self.assertEqual(set(names), set(re.findall(r'(\w+)=', call)), key)

    def test_every_message_is_a_spell_field(self):
        self.assertTrue(set(ABILITY_MESSAGE_PLACEHOLDERS) <= set(inspect.signature(Spell.__init__).parameters))


if __name__ == "__main__":
    unittest.main()
