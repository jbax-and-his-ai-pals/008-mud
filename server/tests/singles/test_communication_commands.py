# tests/singles/test_communication_commands.py
"""Coverage for engine/commands/communication.py's say/yell commands:
guard clauses (no player, dead player, blank message), successful output,
and the game.broadcast_to_room/broadcast_global delegation branches --
previously entirely untested."""

from unittest.mock import MagicMock

from tests.fixtures import GameTestBase
from engine.commands.communication import say_command, yell_command


class TestSayCommand(GameTestBase):
    def test_no_player_reports_cannot_speak(self):
        result = say_command(["hello"], {"player": None})
        self.assertEqual("You cannot speak.", result)

    def test_dead_player_cannot_speak(self):
        self.player.is_alive = False
        result = say_command(["hello"], {"player": self.player})
        self.assertIn("dead and cannot speak", result)

    def test_no_args_prompts_for_message(self):
        result = say_command([], {"player": self.player})
        self.assertEqual("What do you want to say?", result)

    def test_whitespace_only_message_prompts_for_message(self):
        result = say_command(["   "], {"player": self.player})
        self.assertEqual("What do you want to say?", result)

    def test_successful_say_via_process_command(self):
        result = self.game.process_command("say hello there")
        self.assertIn('You say, "hello there"', result)

    def test_broadcasts_to_room_when_game_supports_it(self):
        fake_game = MagicMock()
        context = {"player": self.player, "game": fake_game, "session_id": "sess1"}
        say_command(["hello"], context)
        fake_game.broadcast_to_room.assert_called_once_with(
            self.player.current_region_id, self.player.current_room_id,
            '[[CYAN]]{} says, "hello"[[/]]'.format(self.player.name),
            exclude_session_id="sess1",
        )

    def test_no_broadcast_when_game_lacks_broadcast_to_room(self):
        fake_game = MagicMock(spec=[])
        context = {"player": self.player, "game": fake_game}
        result = say_command(["hello"], context)  # must not raise
        self.assertIn("You say", result)

    def test_no_broadcast_when_game_missing_entirely(self):
        result = say_command(["hello"], {"player": self.player})  # must not raise
        self.assertIn("You say", result)


class TestYellCommand(GameTestBase):
    def test_no_player_reports_cannot_speak(self):
        result = yell_command(["hello"], {"player": None})
        self.assertEqual("You cannot speak.", result)

    def test_dead_player_cannot_speak(self):
        self.player.is_alive = False
        result = yell_command(["hello"], {"player": self.player})
        self.assertIn("dead and cannot speak", result)

    def test_no_args_prompts_for_message(self):
        result = yell_command([], {"player": self.player})
        self.assertEqual("What do you want to yell?", result)

    def test_whitespace_only_message_prompts_for_message(self):
        result = yell_command(["   "], {"player": self.player})
        self.assertEqual("What do you want to yell?", result)

    def test_successful_yell_via_process_command(self):
        result = self.game.process_command("yell incoming!")
        self.assertIn('You yell, "incoming!"', result)

    def test_broadcasts_globally_when_game_supports_it(self):
        fake_game = MagicMock()
        context = {"player": self.player, "game": fake_game, "session_id": "sess1"}
        yell_command(["incoming"], context)
        fake_game.broadcast_global.assert_called_once_with(
            '[[YELLOW]]{} yells, "incoming"[[/]]'.format(self.player.name),
            exclude_session_id="sess1",
        )

    def test_no_broadcast_when_game_lacks_broadcast_global(self):
        fake_game = MagicMock(spec=[])
        context = {"player": self.player, "game": fake_game}
        result = yell_command(["incoming"], context)  # must not raise
        self.assertIn("You yell", result)

    def test_no_broadcast_when_game_missing_entirely(self):
        result = yell_command(["incoming"], {"player": self.player})  # must not raise
        self.assertIn("You yell", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
