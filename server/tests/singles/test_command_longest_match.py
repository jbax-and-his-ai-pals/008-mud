# tests/singles/test_command_longest_match.py
from tests.fixtures import GameTestBase
from engine.commands.command_system import command, unregister_command

class TestCommandLongestMatch(GameTestBase):

    def setUp(self):
        super().setUp()
        # Register two conflicting commands for testing
        
        @command("test command", [], "debug", "Long command")
        def long_handler(args, context):
            return "Executed Long"

        @command("test", [], "debug", "Short command")
        def short_handler(args, context):
            return f"Executed Short with args: {args}"
            
    def tearDown(self):
        unregister_command("test command")
        unregister_command("test")
        super().tearDown()

    def test_priority_parsing(self):
        """Verify 'test command' executes the specific handler, not 'test' with arg 'command'."""
        # Act
        result = self.game.process_command("test command")
        
        # Assert
        self.assertIsNotNone(result)
        if result:
            # If short handler ran, result would be "Executed Short with args: ['command']"
            self.assertEqual(result, "Executed Long")

    def test_fallback_parsing(self):
        """Verify 'test other' falls back to the short handler."""
        result = self.game.process_command("test other")
        
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Executed Short", result)
            self.assertIn("other", result)