# tests/singles/test_gambling_logic.py
from tests.fixtures import GameTestBase
from engine.commands.gambling import get_hand_value

class TestGamblingLogic(GameTestBase):

    def test_blackjack_ace_calculation(self):
        """Verify Ace values adjust from 11 to 1 based on hand total."""
        # 1. Ace + 5 = 16 (Soft)
        hand_soft = [("A", "H"), ("5", "D")]
        self.assertEqual(get_hand_value(hand_soft), 16)

        # 2. Ace + King = 21 (Blackjack)
        hand_bj = [("A", "H"), ("K", "S")]
        self.assertEqual(get_hand_value(hand_bj), 21)

        # 3. Ace + King + 5 = 16 (Hard - Ace becomes 1)
        hand_hard = [("A", "H"), ("K", "S"), ("5", "D")]
        self.assertEqual(get_hand_value(hand_hard), 16)

    def test_multiple_aces(self):
        """Verify multiple Aces adjust correctly."""
        # 4. Ace + Ace = 12 (11 + 1)
        hand_two_aces = [("A", "H"), ("A", "D")]
        self.assertEqual(get_hand_value(hand_two_aces), 12)

        # 5. Ace + Ace + King = 12 (1 + 1 + 10)
        # One Ace is 11 -> 22 (Bust), so it drops to 1. 
        # Total: 1 (Ace) + 1 (Ace) + 10 (King) = 12.
        hand_aces_king = [("A", "H"), ("A", "D"), ("K", "C")]
        self.assertEqual(get_hand_value(hand_aces_king), 12)