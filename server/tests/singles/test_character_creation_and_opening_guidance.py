import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestCharacterCreationValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(str(e.get("payload", "")) for e in events if e.get("type") == "text")

    def test_name_too_short_is_rejected(self):
        self.assertIn("3-24 characters", self._text("char create Al"))

    def test_name_too_long_is_rejected(self):
        self.assertIn("3-24 characters", self._text("char create " + "A" * 25))

    def test_name_with_unsupported_characters_is_rejected(self):
        self.assertIn("unsupported characters", self._text("char create Hero#1"))

    def test_character_create_alternate_prefix(self):
        result = self._text("character create Adventurer")
        self.assertIn("Character created: Adventurer", result)

    def test_cannot_create_a_second_character_for_the_same_session(self):
        # execute_command() only calls _handle_character_creation_command when
        # get_player_for_session() is already None -- the same lookup this
        # guard re-checks -- so it's a defensive branch, not reachable through
        # a second "char create" typed normally. Call it directly instead.
        self._text("char create FirstOne")
        handled, message, created = self.server._handle_character_creation_command(
            self.session.session_id, "char create SecondOne"
        )
        self.assertTrue(handled)
        self.assertFalse(created)
        self.assertIn("already exists", message)

    def test_char_help_alias(self):
        for command in ("help", "?", "char help", "character help"):
            result = self._text(command)
            self.assertIn("char create", result)


class TestBuildOpeningGuidance(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_non_dict_opening_returns_empty_string(self):
        from dataclasses import replace
        self.server.content_set = replace(self.server.content_set, opening="not-a-dict")
        self.assertEqual("", self.server.build_opening_guidance())

    def test_objectives_with_non_dict_entries_are_skipped(self):
        from dataclasses import replace
        self.server.content_set = replace(
            self.server.content_set,
            opening={"heading": "Welcome", "intro": "", "objectives": ["not-a-dict", {"instruction": ""}]},
        )
        guidance = self.server.build_opening_guidance()
        self.assertEqual("Welcome", guidance)  # no usable objectives -> no "First steps" section

    def test_objective_without_command_omits_suffix(self):
        from dataclasses import replace
        self.server.content_set = replace(
            self.server.content_set,
            opening={"heading": "", "intro": "", "objectives": [{"instruction": "Look around"}]},
        )
        guidance = self.server.build_opening_guidance()
        self.assertIn("1. Look around", guidance)
        self.assertNotIn("(", guidance)

    def test_objective_with_command_includes_suffix(self):
        from dataclasses import replace
        self.server.content_set = replace(
            self.server.content_set,
            opening={"heading": "", "intro": "", "objectives": [{"instruction": "Look around", "command": "look"}]},
        )
        guidance = self.server.build_opening_guidance()
        self.assertIn("1. Look around (look)", guidance)

    def test_empty_objectives_list_omits_first_steps_section(self):
        from dataclasses import replace
        self.server.content_set = replace(
            self.server.content_set,
            opening={"heading": "Welcome", "intro": "", "objectives": []},
        )
        guidance = self.server.build_opening_guidance()
        self.assertEqual("Welcome", guidance)
        self.assertNotIn("First steps", guidance)


if __name__ == "__main__":
    unittest.main()
