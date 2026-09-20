# tests/singles/test_boot_warning_codes.py
"""The warning-code list has three copies, and they must not drift.

`startup_diagnostics.fail_on_warning_codes` matches by exact string. There is no
partial match and no error for an unknown entry, so a misspelled code appears in
no warning, the policy never fires, and the operator is left believing startup is
guarded when it is not. That is not hypothetical: four codes in
`docs/reference/boot-warning-codes.md` were transposed (`provider.weather.unresolved`
for `weather.provider.not_found`) and a fifth was missing, and nothing noticed
because a wrong code produces no output to notice.

So the set exists in three places and this module is the thing that keeps them
equal:

1. `KNOWN_BOOT_WARNING_CODES` -- what the server accepts and enforces against.
2. `docs/reference/boot-warning-codes.md` -- what an operator reads and pastes.
3. the engine's own emitted codes -- what can actually appear.

A new warning has to be added to all three, which is the point.
"""
import re
import unittest
from pathlib import Path

from engine.server.headless.boot_warnings import KNOWN_BOOT_WARNING_CODES


SERVER_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVER_ROOT.parent
ENGINE = SERVER_ROOT / "engine"
DOC = REPO_ROOT / "docs" / "reference" / "boot-warning-codes.md"

# A code literal: `"content.items.dir_missing"`. Deliberately broad enough to
# catch a new emitter written in any style, then narrowed by the caller.
_CODE_LITERAL = re.compile(
    r'"((?:content|profile|weather|world_effects|runtime)\.[a-z_]+(?:\.[a-z_]+)+)"'
)

# Names that share the code prefix but are feature-profile section keys, not
# warnings. Listed explicitly so a new one is a deliberate addition rather than a
# silent widening of the accepted set.
SECTION_NAMES = {
    "weather.mode",
    "weather.chances",
    "weather.descriptions",
    "world_effects.mode",
}


def _emitted_codes() -> set[str]:
    """Every code-shaped literal the engine actually emits."""
    found: set[str] = set()
    for path in ENGINE.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.update(_CODE_LITERAL.findall(text))
    return found - SECTION_NAMES


class TestTheConstantMatchesTheEngine(unittest.TestCase):
    def test_the_scan_finds_codes_at_all(self):
        """Guard against a moved tree making every assertion below vacuous."""
        self.assertGreater(len(_emitted_codes()), 10)

    def test_every_emitted_code_is_in_the_constant(self):
        """A warning the server can raise must be one an operator can fail on."""
        missing = sorted(_emitted_codes() - KNOWN_BOOT_WARNING_CODES)
        self.assertEqual(
            [], missing,
            "these codes are emitted but not accepted in fail_on_warning_codes",
        )

    def test_every_constant_entry_is_emitted_somewhere(self):
        """The other direction: no entry that can never appear.

        Kept as an equality rather than a subset so that deleting an emitter shows
        up here rather than leaving a dead entry an operator may still configure.
        """
        unused = sorted(KNOWN_BOOT_WARNING_CODES - _emitted_codes())
        self.assertEqual([], unused, "these codes are accepted but nothing emits them")

    def test_the_section_names_are_not_warning_codes(self):
        """The exclusions above are real config keys, not a place to hide one."""
        for name in sorted(SECTION_NAMES):
            with self.subTest(name=name):
                self.assertNotIn(name, KNOWN_BOOT_WARNING_CODES)
        profile = (ENGINE / "server" / "feature_profile.py").read_text(encoding="utf-8")
        for name in ("weather.mode", "world_effects.mode"):
            with self.subTest(name=name):
                self.assertIn(f'"{name}"', profile,
                              f"{name} is excluded as a profile section; it should be one")


class TestTheDocumentMatchesTheConstant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding="utf-8")
        # The `## Current Codes` section only; later sections quote codes in prose
        # and in preset examples, which are not the list.
        start = cls.doc.index("## Current Codes")
        end = cls.doc.index("## Typos are refused")
        cls.section = cls.doc[start:end]
        # Just the bullet entries, so a sentence *about* a wrong code is not
        # mistaken for the list containing one.
        cls.listed = set(re.findall(r"^- `([a-z_.]+)`$", cls.section, re.MULTILINE))

    def test_the_document_lists_every_code(self):
        missing = sorted(KNOWN_BOOT_WARNING_CODES - self.listed)
        self.assertEqual([], missing, "codes the server accepts but the page omits")

    def test_the_document_lists_nothing_else(self):
        """This is the failure that started it: a pasted code that does not exist."""
        extra = sorted(self.listed - KNOWN_BOOT_WARNING_CODES)
        self.assertEqual([], extra, "codes on the page that the server will refuse")

    def test_the_count_in_the_prose_is_right(self):
        """The page states a number; a number is easy to leave behind."""
        match = re.search(r"(\w+) codes, which is the complete set", self.section, re.IGNORECASE)
        self.assertIsNotNone(match, "the page should state how many codes there are")
        words = {
            "eighteen": 18, "nineteen": 19, "twenty": 20,
            "twenty-one": 21, "twenty-two": 22,
        }
        self.assertIn(match.group(1).lower(), words, "state the count as a word")
        self.assertEqual(
            len(KNOWN_BOOT_WARNING_CODES), words[match.group(1).lower()],
            "the stated count does not match the real set",
        )
        self.assertEqual(len(KNOWN_BOOT_WARNING_CODES), len(self.listed),
                         "the stated count does not match the number of bullets either")

    def test_the_list_does_not_contain_the_transposed_codes(self):
        """The exact strings that were wrong, so they cannot come back.

        Scoped to the bullets: the note under them quotes the transposed form on
        purpose, to explain what happened, so scanning the prose would forbid the
        explanation along with the mistake.
        """
        for wrong in ("provider.weather.", "provider.world_effects."):
            with self.subTest(wrong=wrong):
                offending = sorted(entry for entry in self.listed if entry.startswith(wrong))
                self.assertEqual(
                    [], offending,
                    f"{wrong} is the transposed form; the real code is weather.provider.<x>",
                )


class TestThePolicyRefusesATypo(unittest.TestCase):
    """The guard itself, exercised rather than described.

    `_enforce_boot_warning_policy` reads exactly two attributes, so a minimal
    object carrying them is enough to drive it -- no server, no world, no content
    set. That keeps the test about the policy.
    """

    def test_an_unknown_code_aborts_startup(self):
        """The whole point: a policy that cannot fire must not look armed."""
        from engine.server.headless.boot_warnings import BootWarningsMixin

        class _Probe(BootWarningsMixin):
            boot_warning_fail_codes = ["provider.weather.not_found"]
            boot_warning_records = []

        with self.assertRaises(RuntimeError) as caught:
            _Probe()._enforce_boot_warning_policy()
        message = str(caught.exception)
        self.assertIn("Unknown warning code(s)", message)
        self.assertIn("provider.weather.not_found", message)
        self.assertIn("boot-warning-codes.md", message, "the error should point at the list")

    def test_a_known_code_that_did_not_fire_does_not_abort(self):
        """An armed policy with nothing to fire on is the normal case."""
        from engine.server.headless.boot_warnings import BootWarningsMixin

        class _Probe(BootWarningsMixin):
            boot_warning_fail_codes = ["content.spells.dir_missing"]
            boot_warning_records = []

        _Probe()._enforce_boot_warning_policy()

    def test_a_known_code_that_did_fire_aborts_with_the_original_message(self):
        """The pre-existing behaviour must survive the new check."""
        from engine.server.headless.boot_warnings import BootWarningsMixin

        class _Probe(BootWarningsMixin):
            boot_warning_fail_codes = ["content.spells.dir_missing"]
            boot_warning_records = [{"code": "content.spells.dir_missing"}]

        with self.assertRaises(RuntimeError) as caught:
            _Probe()._enforce_boot_warning_policy()
        self.assertIn("Disallowed warning code(s)", str(caught.exception))

    def test_an_empty_policy_is_not_checked(self):
        """No list means no policy, and no reason to complain about one."""
        from engine.server.headless.boot_warnings import BootWarningsMixin

        class _Probe(BootWarningsMixin):
            boot_warning_fail_codes = []
            boot_warning_records = []

        _Probe()._enforce_boot_warning_policy()


if __name__ == "__main__":
    unittest.main()
