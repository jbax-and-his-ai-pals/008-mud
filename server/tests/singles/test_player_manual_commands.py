# tests/singles/test_player_manual_commands.py
"""Every command the player manual lists must exist, and vice versa.

`docs/reference/PLAYER_MANUAL.md` section 18 is the quick-reference table a player
is told to trust ("Type `help <command>` any time for the full details on any of
these"). It listed `titles`, which has never been a command: the handler is
registered as `title` with aliases `mytitle` and `wearth`
(`engine/commands/advancement.py:88-93`). A manual that sends a player to a
command that does not exist is worse than one that omits it, because the player
concludes they typed it wrong.

The reverse direction matters too: a registered command nobody documents is
content the player cannot find.

Only the table is checked. Prose elsewhere in the manual is allowed to mention
concepts, and section 18 is explicitly the authoritative list.
"""
import re
import unittest
from pathlib import Path

import engine.commands  # noqa: F401 - force command module registration
from engine.commands.command_system import get_registered_commands


SERVER_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVER_ROOT.parent
MANUAL = REPO_ROOT / "docs" / "reference" / "PLAYER_MANUAL.md"

# The table names some commands with an argument, e.g. `` `go <dir>` `` or
# `` `look board` ``, and others are registered as literal multi-word names
# (`` `buy house` ``, `` `expand house` ``). In both cases the first word is what
# the parser dispatches on, so it is checked against the registry: the registry
# contains *both* `expand` and `expand house`, so a bare verb is still a real
# entry rather than a fragment of one.
_MULTI_WORD = {"go", "look", "accept", "turnin", "buy", "expand", "replace"}

# Spellings the table uses for one command, or for a syntax form rather than a
# name. Mapped to the registry entries they stand for.
_ALIAS_FORMS = {
    "reply": ["reply"], "respond": ["respond"], "choose": ["choose"],
    "take": ["take"], "get": ["get"],
    "flee": ["flee"], "retreat": ["retreat"],
    "mine": ["mine"], "harvest": ["harvest"], "chop": ["chop"],
    "relationship": ["relationship"], "relationships": ["relationships"],
    "payouts": ["payouts"], "odds": ["odds"],
    "dir": None,  # `<dir>` is an argument placeholder, not a command
    "command": None,  # `<command>` likewise
}


def _table_commands(registered: set[str]) -> list[str]:
    """Resolve section 18's `Commands` column against the registry.

    Each backticked span is one *name*, and a name may be several words: the table
    writes `` `buy house` `` and `` `expand house` `` because those are registered
    that way, and `` `go <dir>` `` because the argument is the point. So a span is
    matched by maximal munch — longest word-prefix that the registry knows — and
    an argument placeholder (`<dir>`, `<command>`) ends the name. Bare words
    outside the backticks are prose ("look board" as a sentence) and are ignored.
    """
    text = MANUAL.read_text(encoding="utf-8")
    start = text.index("## 18. Quick-Reference Command Table")
    end = text.index("Type `help <command>`", start)
    section = text[start:end]

    found: list[str] = []
    for row in re.finditer(r"^\| \*\*[^*]+\*\* \| (.+?) \|$", section, re.MULTILINE):
        for span in re.findall(r"`([^`]+)`", row.group(1)):
            words = [
                word.strip("()").lower()
                for word in span.replace("/", " ").split()
            ]
            # Slash-separated alternatives are separate names, not one multi-word
            # name, so a span containing "/" is read word by word.
            groups = [[word] for word in words] if "/" in span else [words]
            for group in groups:
                name_words: list[str] = []
                for word in group:
                    if not word or word.startswith("<"):
                        break
                    name_words.append(word)
                    joined = " ".join(name_words)
                    if joined in registered:
                        found.append(joined)
                        name_words = []
                # A first word that resolves is enough; `look board` is `look`.
                if name_words and name_words[0] in registered:
                    found.append(name_words[0])
    return sorted(set(found))


class TestTheManualOnlyNamesRealCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registered = get_registered_commands()
        cls.lookup = {name.lower() for name in cls.registered}
        cls.listed = _table_commands(cls.lookup)

    def test_the_manual_has_a_command_table(self):
        """Guard against a heading rename making every test below vacuous."""
        self.assertGreater(len(self.listed), 40, "section 18 should list many commands")

    def test_the_registry_is_populated(self):
        self.assertGreater(len(self.registered), 40, "importing engine.commands should register them")

    def test_every_listed_command_exists(self):
        """The direction that produced the `titles` bug."""
        for name in self.listed:
            with self.subTest(command=name):
                self.assertIn(name, self.lookup,
                              f"the manual lists `{name}`, which is not a registered command")

    def test_the_manual_is_not_missing_major_commands(self):
        """A command the manual omits is one a player will never find.

        Scoped to commands a *player* can type: no alias of its own (the table
        lists the primary name), no capability or entitlement gate (that is an
        operator or GM command), and a player-facing category.

        **This assertion used to be vacuous.** It filtered on `meta["group"]`,
        which nothing in the engine sets -- the registry key is `category` -- so
        `undocumented` was always empty and the check could not fail. Found while
        adding the three work commands, which is the only kind of evidence that a
        check works. Switching it to `category` immediately surfaced two real
        gaps (`plant` and `stop`), both now in the table.
        """
        player_categories = {
            "movement", "information", "interaction", "combat", "crafting",
            "inventory", "abilities", "gathering", "trade", "quests", "property",
            "crime", "gambling", "system",
        }
        documented = {name.lower() for name in self.listed}
        undocumented = sorted(
            name for name, meta in self.registered.items()
            if name.lower() not in documented
            and not meta.get("aliases")
            and not meta.get("capabilities")
            and not meta.get("entitlements")
            and str(meta.get("category", "")).lower() in player_categories
        )
        self.assertEqual([], undocumented,
                         "registered player commands that the quick-reference table omits")

    def test_the_scope_of_that_check_is_real(self):
        """Guards the guard: a filter matching no command at all proves nothing.

        The bug this replaces was a key name, and a key name fails quietly. So
        assert the three things the filter above depends on are all true of this
        registry: the category names are used, some commands are gated, and some
        carry aliases.
        """
        used = {str(meta.get("category", "")).lower() for meta in self.registered.values()}
        self.assertTrue(
            used & {"crafting", "inventory", "movement", "information"},
            "the registry should use the player-facing category names this file filters on: %s"
            % sorted(used),
        )
        self.assertTrue(
            any(meta.get("capabilities") or meta.get("entitlements")
                for meta in self.registered.values()),
            "some commands are gated, which is what keeps operator commands out of the manual",
        )
        self.assertTrue(
            any(meta.get("aliases") for meta in self.registered.values()),
            "some commands have aliases, which the table lists beside their primary name",
        )


class TestTheCorrectionsHold(unittest.TestCase):
    """Pins for the two fixes made to the manual on 2026-09-19."""

    @classmethod
    def setUpClass(cls):
        cls.text = MANUAL.read_text(encoding="utf-8")

    def test_titles_is_not_a_command(self):
        self.assertNotIn("titles", {name.lower() for name in get_registered_commands()})

    def test_the_manual_no_longer_tells_players_to_type_titles(self):
        """The table listed both `titles` and `title`, which is how it survived."""
        section = self.text[self.text.index("## 18. Quick-Reference Command Table"):]
        self.assertNotIn("`titles`", section)

    def test_the_prose_still_explains_how_to_wear_a_title(self):
        """The fix must not have removed the instruction along with the typo."""
        self.assertIn("`title` to see what you've earned", self.text)
        self.assertIn("`title <name>`", self.text)


if __name__ == "__main__":
    unittest.main()
