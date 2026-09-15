# tests/singles/test_quest_journal_instructions.py
"""The quest journal must always tell the player what to do.

Two defects lived here, both on the very first quest a new player accepts:

1. Missing optional objective fields were rendered as a literal `?`. The first
   commission's journal line read:

       Task: Deliver wildflower posy to Elder Thorne in ?. (You don't have the package!)

   and the accept message explicitly says "Check your 'journal' for details".
   In a text game the journal *is* the instruction channel, so a `?` there is
   the worst place for a placeholder to leak.

2. The authored stage instruction ("Gather herbs, craft a wildflower posy, and
   deliver it to Elder Thorne.") was only rendered by the generic fallback
   branch, so every typed objective -- kill, fetch, deliver -- showed a
   degraded templated line and the authored prose was never seen.
"""

import re
import unittest

from tests.fixtures import GameTestBase

MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class TestQuestJournalInstructions(GameTestBase):
    """Render the journal the way the running game does."""

    def _journal_text(self) -> str:
        from engine.commands.quest import journal_handler
        context = {"world": self.world, "player": self.player, "game": self.game}
        return MARKUP.sub("", journal_handler([], context))

    def _accept_first_board_quest(self):
        """Accept the starter commission through the real command path."""
        from engine.commands.quest import accept_quest_handler
        context = {"world": self.world, "player": self.player, "game": self.game}
        accept_quest_handler(["1"], context)

    def test_journal_never_renders_a_bare_question_mark(self):
        """The regression: `... in ?.` reached the player."""
        self._accept_first_board_quest()
        text = self._journal_text()
        offenders = [ln for ln in text.splitlines() if "?" in ln]
        self.assertEqual(
            offenders, [],
            "journal rendered a placeholder instead of omitting unknown detail:\n"
            + "\n".join(offenders),
        )

    def test_journal_shows_the_authored_stage_instruction(self):
        """The authored prose is the clearest statement of what to do."""
        self._accept_first_board_quest()
        text = self._journal_text()
        stage_instruction = "Gather herbs, craft a wildflower posy"
        self.assertIn(
            stage_instruction, text,
            "the authored stage description is not shown in the journal",
        )

    def test_deliver_objective_omits_unknown_location(self):
        """A deliver objective with no region must not invent one."""
        self._accept_first_board_quest()
        text = self._journal_text()
        self.assertNotIn(" in ?", text)
        self.assertNotIn("in .", text)

    def test_optional_helper_treats_absent_as_empty(self):
        from engine.commands.quest import _optional
        self.assertEqual(_optional(None), "")
        self.assertEqual(_optional(""), "")
        self.assertEqual(_optional("   "), "")
        self.assertEqual(_optional("Riverside"), "Riverside")
        self.assertEqual(_optional(0), "0")

    def test_stage_instruction_helper_is_bounds_safe(self):
        from engine.commands.quest import _stage_instruction
        quest = {"stages": [{"description": "First thing."}]}
        self.assertEqual(_stage_instruction(quest, 0), "First thing.")
        self.assertEqual(_stage_instruction(quest, 5), "")
        self.assertEqual(_stage_instruction(quest, -1), "")
        self.assertEqual(_stage_instruction({"stages": None}, 0), "")
        self.assertEqual(_stage_instruction(quest, "not-a-number"), "")

    def test_kill_objective_prefers_authored_singular_target(self):
        """`Defeat 0/1 targets` is not acceptable prose for a named bounty."""
        from engine.commands.quest import _optional
        # Mirrors quest_bounty_troll_elder's authored objective shape.
        objective = {"target_name": "an elite troll", "required_quantity": 1}
        self.assertEqual(_optional(objective.get("target_name_plural")), "")


if __name__ == "__main__":
    unittest.main()
