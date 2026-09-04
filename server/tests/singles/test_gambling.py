# tests/singles/test_gambling.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.commands.gambling import get_hand_value
from engine.npcs.npc_factory import NPCFactory

class TestGambling(GameTestBase):

    def test_blackjack_math(self):
        """Verify card value calculations logic."""
        hand_soft = [("A", "H"), ("9", "S")]
        self.assertEqual(get_hand_value(hand_soft), 20)
        
        hand_aces = [("A", "H"), ("A", "S"), ("9", "D")]
        self.assertEqual(get_hand_value(hand_aces), 21)
        
        hand_bust = [("K", "H"), ("Q", "S"), ("5", "D")]
        self.assertEqual(get_hand_value(hand_bust), 25)

    def test_betting_flow(self):
        """Verify betting mechanics and state transitions."""
        self.player.runtime_state.gold = 100
        
        # Sync World location
        self.world.current_region_id = "casino"
        self.world.current_room_id = "dice_parlor"
        self.player.current_region_id = "casino"
        self.player.current_room_id = "dice_parlor"
        
        dealer = NPCFactory.create_npc_from_template("dice_dealer", self.world)
        
        if dealer:
            self.world.add_npc(dealer)
            dealer.current_region_id = "casino"
            dealer.current_room_id = "dice_parlor"

            # Act: Place Bet
            result = self.game.process_command("bet 50")
            
            # Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("You place 50 gold", result)
            
            # Check Gold Outcome (Win=150, Tie=50 (logic dependent), Loss=50)
            self.assertIn(self.player.runtime_state.gold, [50, 150])

    @patch('engine.commands.gambling.draw_card')
    def test_blackjack_state(self, mock_draw):
        """Verify Blackjack state persists between commands (Deterministic)."""
        # Force cards: Player(10, 2)=12, Dealer(10, 5)=15, NextHit(3)
        mock_draw.side_effect = [
            ('10', 'H'), ('2', 'D'),  # Player Init
            ('10', 'S'), ('5', 'C'),  # Dealer Init
            ('3', 'H')                # Player Hit
        ]

        self.player.runtime_state.gold = 100
        self.world.current_region_id = "casino"
        self.world.current_room_id = "card_room"
        self.player.current_region_id = "casino"
        self.player.current_room_id = "card_room"
        
        dealer = NPCFactory.create_npc_from_template("card_dealer", self.world)
        if dealer:
            self.world.add_npc(dealer)
            dealer.current_region_id = "casino"
            dealer.current_room_id = "card_room"
            
            # 1. Start Game
            self.game.process_command("bet 10")
            
            # 2. Assert Active (Deterministic: 12 is not 21)
            minigame = self.player.active_minigame
            self.assertIsNotNone(minigame, "Minigame should be active (Hand: 12)")
            
            if minigame:
                self.assertEqual(minigame["type"], "blackjack")
                
                # 3. Hit
                self.game.process_command("hit")
                
                # 4. Check Hand updated (12 + 3 = 15)
                self.assertEqual(len(minigame["hand"]), 3)
