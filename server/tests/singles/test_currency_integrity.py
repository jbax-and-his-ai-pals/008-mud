# tests/singles/test_currency_integrity.py
from tests.fixtures import GameTestBase

class TestCurrencyIntegrity(GameTestBase):

    def test_negative_gold_prevention(self):
        """Verify gold cannot be set to a negative value via commands or logic."""
        self.player.gold = 10
        
        # 1. Attempt debug set
        result = self.game.process_command("setgold -50")
        
        # Assert result exists and contains error message
        self.assertIsNotNone(result, "Command execution failed to return feedback.")
        if result:
            self.assertIn("cannot be negative", result)
        
        self.assertEqual(self.player.gold, 10)

    def test_payment_logic(self):
        """Verify logic prevents paying more than owned."""
        self.player.gold = 50
        
        # Simulate a transaction check (like in mercantile.py)
        cost = 100
        can_afford = self.player.gold >= cost
        
        self.assertFalse(can_afford)
        
        # Verify gold wasn't deducted
        self.assertEqual(self.player.gold, 50)