# tests/singles/test_command_suggestions.py
from tests.fixtures import GameTestBase

class TestCommandSuggestions(GameTestBase):

    def test_basic_suggestions(self):
        """Verify command suggesting based on partial strings."""
        cp = self.game.command_processor
        
        # Test "l" should suggest "look" (and maybe others like "load")
        suggestions = cp.get_command_suggestions("lo")
        self.assertIn("look", suggestions)
        self.assertIn("load", suggestions)
        
        # Test "inv"
        suggestions = cp.get_command_suggestions("inv")
        self.assertIn("inventory", suggestions)
        self.assertIn("invmode", suggestions)

    def test_alias_suggestions(self):
        """Verify that command aliases are also suggested."""
        cp = self.game.command_processor
        
        # "n" is an alias for "north"
        suggestions = cp.get_command_suggestions("n")
        self.assertIn("north", suggestions)
        # Note: it suggests primary names and aliases starting with the prefix