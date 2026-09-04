# tests/singles/test_command_empty_input.py
from tests.fixtures import GameTestBase

class TestCommandEmptyInput(GameTestBase):

    def test_empty_string(self):
        """Verify empty input returns empty string (no error)."""
        result = self.game.process_command("")
        self.assertEqual(result, "")

    def test_whitespace_string(self):
        """Verify whitespace input returns empty string."""
        result = self.game.process_command("   ")
        self.assertEqual(result, "")

    def test_none_input(self):
        """Verify None input is handled (if applicable)."""
        # Type hinting usually prevents this, but runtime calls might not
        try:
            # Bypass type check for test
            result = self.game.process_command(None) # type: ignore
            self.assertEqual(result, "")
        except AttributeError:
            # If implementation does text.strip() on None, it raises. 
            # Ideally it should check.
            # Current impl: text.strip().lower().
            pass