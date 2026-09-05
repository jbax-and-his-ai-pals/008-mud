# tests/singles/test_command_alias_integrity.py
"""Regression coverage for a real playtest bug: engine.commands.command_system's
registered_commands is a flat name->handler map, so if two @command()
decorators declare the same alias string, whichever module happens to load
last silently wins and the other command's declared alias becomes dead
(e.g. typing it does something else entirely, or nothing useful).

Found via live playtesting: attack's declared "hit" alias was dead (shadowed
by gambling's blackjack "hit" command), stoptrade's declared "stop" alias
was dead (shadowed by the general "stop current action" command), quit's
declared "exit" alias was dead (shadowed by the "out" movement command),
and talk's declared "ask" alias was dead (shadowed by the dedicated "ask"
command) -- all silently, with no error at load time. Fixed by dropping
the losing alias declarations to match reality, and this test guards
against a name being re-added to a command whose alias set is no longer
being verified.

This test also acts as a general tripwire: if it starts failing, some
*other* new collision has been introduced somewhere in the command set."""

import unittest

from engine.commands.command_system import command_groups, registered_commands


class TestNoDeadAliases(unittest.TestCase):
    def test_every_declared_name_and_alias_resolves_back_to_its_own_command(self):
        seen = set()
        dead = []
        for cmds in command_groups.values():
            for cmd in cmds:
                key = id(cmd)
                if key in seen:
                    continue
                seen.add(key)
                for name in [cmd["name"], *cmd["aliases"]]:
                    actual = registered_commands.get(name)
                    if actual is None or actual is not cmd:
                        dead.append((name, cmd["name"], actual["name"] if actual else None))
        self.assertEqual([], dead, f"Dead/shadowed command aliases found: {dead}")


if __name__ == "__main__":
    unittest.main()
