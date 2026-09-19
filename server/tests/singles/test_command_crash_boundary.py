# tests/singles/test_command_crash_boundary.py
"""A command that raises must not end the session.

Handlers are supposed to answer with text. When one raises -- an engine defect,
or content the handler read and could not make sense of -- nothing used to stop
it: `CommandProcessor.process_input` called the handler directly, so the
exception reached the single-player loop (ending the run) or the headless
command path (ending the connection, on a shared server).

`process_input` is the one place every game mode dispatches through, which is
why the boundary lives there and why these tests drive it rather than a handler.
"""
import unittest

from engine.commands.command_system import (
    CommandProcessor,
    command,
    command_failure_message,
    unregister_command,
)
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER, GameTestBase


RAISING_COMMAND = "cmdsys_hard_fail"
SECRET = "/home/someone/secret/path/content.json"


def register_raising_command() -> None:
    """Register the always-raising command.

    Registered per test class rather than once at import: the registry is
    process-global, so a class that unregisters it in `tearDown` would take it
    away from every later class, and the test that followed would fail for a
    reason that had nothing to do with what it was checking.
    """
    unregister_command(RAISING_COMMAND)

    @command(RAISING_COMMAND, category="other", help_text="always raises")
    def _always_raises(_args, _context):
        raise ValueError("could not read %s" % SECRET)


class TestTheProcessorContainsAHandlerFailure(unittest.TestCase):
    def setUp(self):
        register_raising_command()
        self.processor = CommandProcessor()

    def tearDown(self):
        unregister_command(RAISING_COMMAND)

    def test_a_raising_handler_returns_a_message_instead_of_propagating(self):
        result = self.processor.process_input(RAISING_COMMAND)
        self.assertIn(RAISING_COMMAND, result)
        self.assertIn("bug", result)

    def test_the_processor_still_works_afterwards(self):
        self.processor.process_input(RAISING_COMMAND)
        self.assertIn("Unknown command", self.processor.process_input("totally_bogus_xyz"))

    def test_the_message_does_not_leak_the_exceptions_text(self):
        """An exception's message can carry paths and internal identifiers."""
        result = self.processor.process_input(RAISING_COMMAND)
        self.assertNotIn(SECRET, result)
        self.assertNotIn("content.json", result)

    def test_the_message_names_the_exception_type(self):
        """The one detail that makes a bug report searchable."""
        self.assertIn("ValueError", self.processor.process_input(RAISING_COMMAND))

    def test_the_message_helper_names_the_command_that_failed(self):
        message = command_failure_message("craft", ValueError("x"))
        self.assertIn("craft", message)
        self.assertIn("ValueError", message)


class TestTheServerSurvivesAHandlerFailure(unittest.TestCase):
    def setUp(self):
        register_raising_command()
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create Crash Tester")

    def tearDown(self):
        unregister_command(RAISING_COMMAND)

    def _text(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(
            str(event.get("payload")) for event in events if event.get("type") in ("text", "error")
        )

    def test_a_failed_command_still_answers_the_player(self):
        result = self._text(RAISING_COMMAND)
        self.assertIn("bug", result)

    def test_the_session_keeps_working(self):
        self._text(RAISING_COMMAND)
        looked = self._text("look")
        self.assertIn("Town Square".upper(), looked.upper())

    def test_a_failure_is_recorded_for_the_operator(self):
        self._text(RAISING_COMMAND)
        self.assertEqual(1, self.server.command_failure_counts.get(RAISING_COMMAND))
        codes = {str(entry.get("code")) for entry in self.server.boot_warning_records}
        self.assertIn("runtime.command.failed", codes)

    def test_repeating_a_failure_is_counted_rather_than_hidden(self):
        """A command that has crashed four times is what an operator needs to see."""
        for _ in range(4):
            self._text(RAISING_COMMAND)
        self.assertEqual(4, self.server.command_failure_counts.get(RAISING_COMMAND))
        messages = [str(entry.get("message", "")) for entry in self.server.boot_warning_records]
        self.assertTrue(any("4 time(s)" in message for message in messages), messages)

    def test_other_players_are_unaffected(self):
        other = self.server.create_session()
        self.server.execute_command(other.session_id, "char create Bystander")
        self._text(RAISING_COMMAND)
        events = self.server.execute_command(other.session_id, "look")
        self.assertTrue(events)


class TestWhitespaceInputIsNotACrash(GameTestBase):
    """The dead-player branch split a possibly-empty line on whitespace.

    `game_manager.process_command` is the desktop input path, and it decides
    which commands a dead player may still use by taking the first word of the
    line. `text.strip().lower().split()[0]` raises IndexError on an empty line,
    so pressing Enter at the death screen ended the run.
    """

    def test_a_dead_player_pressing_enter_gets_an_answer(self):
        self.player.is_alive = False
        for text in ("", "   ", "\t", "  \t "):
            result = self.game.process_command(text)
            self.assertIsInstance(result, str)

    def test_a_dead_player_typing_a_command_is_still_refused_by_name(self):
        self.player.is_alive = False
        result = self.game.process_command("attack nobody")
        self.assertIn("dead", result.lower())

    def test_a_dead_player_may_still_look(self):
        self.player.is_alive = False
        result = self.game.process_command("look")
        self.assertNotIn("You are dead", result or "")


if __name__ == "__main__":
    unittest.main()
