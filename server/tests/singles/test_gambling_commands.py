# tests/singles/test_gambling_commands.py
"""Coverage for engine/commands/gambling.py beyond what
test_gambling.py/test_gambling_logic.py already exercise: rules, bet dispatch
across all five games, hit/stand/guess edge cases, and the non-blackjack
minigame implementations (dice, slots, wheel, runebreaker)."""

from unittest.mock import patch, MagicMock

from tests.fixtures import GameTestBase
from engine.commands.gambling import bet_handler, draw_card, _check_location, RANKS, SUITS
from engine.npcs.npc_factory import NPCFactory


class TestDrawCard(GameTestBase):
    def test_returns_a_valid_rank_and_suit(self):
        rank, suit = draw_card()
        self.assertIn(rank, RANKS)
        self.assertIn(suit, SUITS)


class TestCheckLocation(GameTestBase):
    def test_no_active_minigame_returns_false(self):
        self.player.active_minigame = None
        self.assertFalse(_check_location(self.player))

    def test_deprecated_record_without_location_keys_is_treated_as_stationary(self):
        self.player.active_minigame = {"type": "blackjack"}
        self.assertTrue(_check_location(self.player))


class TestBetHandlerDirect(GameTestBase):
    def test_no_player_reports_not_found(self):
        result = bet_handler(["10"], {"world": self.world, "player": None})
        self.assertIn("Player not found", result)


class _CasinoTestBase(GameTestBase):
    def _place_dealer(self, template_id: str, region="casino", room="floor"):
        dealer = NPCFactory.create_npc_from_template(template_id, self.world)
        self.world.add_npc(dealer)
        dealer.current_region_id = region
        dealer.current_room_id = room
        self.world.current_region_id = region
        self.world.current_room_id = room
        self.player.current_region_id = region
        self.player.current_room_id = room
        self.player.runtime_state.gold = 100
        return dealer


class TestRulesCommand(_CasinoTestBase):
    def test_no_dealer_present_is_reported(self):
        result = self.game.process_command("rules")
        self.assertIn("no active games", result)

    def test_shows_dealer_rules_and_game_name(self):
        self._place_dealer("card_dealer")
        result = self.game.process_command("rules")
        self.assertIn("Blackjack", result)


class TestBetCommandGuards(_CasinoTestBase):
    def test_dead_player_cannot_gamble(self):
        # process_command() itself gates dead players before commands not in
        # its allowlist ever dispatch, so bet_handler's own check needs a
        # direct call to reach it.
        self._place_dealer("dice_dealer")
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = bet_handler(["10"], context)
        self.assertIn("cannot gamble while dead", result)

    def test_already_in_a_game_is_reported(self):
        self._place_dealer("dice_dealer")
        self.player.active_minigame = {"type": "blackjack"}
        result = self.game.process_command("bet 10")
        self.assertIn("already playing", result)

    def test_no_args_shows_usage(self):
        self._place_dealer("dice_dealer")
        result = self.game.process_command("bet")
        self.assertIn("Usage", result)

    def test_non_positive_amount_is_rejected(self):
        self._place_dealer("dice_dealer")
        result = self.game.process_command("bet 0")
        self.assertIn("positive amount", result)

    def test_invalid_amount_is_rejected(self):
        self._place_dealer("dice_dealer")
        result = self.game.process_command("bet not_a_number")
        self.assertIn("Invalid amount", result)

    def test_insufficient_gold_is_rejected(self):
        self._place_dealer("dice_dealer")
        self.player.runtime_state.gold = 5
        result = self.game.process_command("bet 10")
        self.assertIn("don't have enough gold", result)

    def test_no_dealer_present_is_reported(self):
        self.player.runtime_state.gold = 100
        result = self.game.process_command("bet 10")
        self.assertIn("no one here to take your bet", result)

    def test_dealer_without_a_known_game_is_confused(self):
        dealer = self._place_dealer("casino_receptionist")
        dealer.properties["is_dealer"] = True
        dealer.properties.pop("dealer_game", None)
        result = self.game.process_command("bet 10")
        self.assertIn("looks confused", result)


class TestHitAndStand(_CasinoTestBase):
    def test_hit_when_not_playing_is_reported(self):
        result = self.game.process_command("hit")
        self.assertEqual("You are not playing a card game right now.", result)

    def test_stand_when_not_playing_is_reported(self):
        result = self.game.process_command("stand")
        self.assertEqual("You are not playing a card game right now.", result)

    def test_hit_away_from_the_table_is_rejected(self):
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("2", "H")], "dealer_hand": [("2", "S")],
            "region_id": "casino", "room_id": "card_room",
        }
        self.player.current_region_id = "somewhere_else"
        self.player.current_room_id = "somewhere_else"
        result = self.game.process_command("hit")
        self.assertIn("return to the table", result)

    @patch("engine.commands.gambling.draw_card")
    def test_hit_busts_and_clears_minigame(self, mock_draw):
        mock_draw.return_value = ("K", "H")
        self.player.runtime_state.gold = 100
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("K", "H"), ("Q", "S")], "dealer_hand": [("2", "S"), ("3", "S")],
            "region_id": "town", "room_id": "town_square",
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("hit")
        self.assertIn("Bust!", result)
        self.assertIsNone(self.player.active_minigame)

    def test_stand_away_from_the_table_is_rejected(self):
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("2", "H")], "dealer_hand": [("2", "S")],
            "region_id": "casino", "room_id": "card_room",
        }
        self.player.current_region_id = "somewhere_else"
        self.player.current_room_id = "somewhere_else"
        result = self.game.process_command("stand")
        self.assertIn("return to the table", result)

    @patch("engine.commands.gambling.draw_card")
    def test_stand_dealer_busts_player_wins(self, mock_draw):
        mock_draw.return_value = ("K", "H")  # 16 + K busts the dealer
        self.player.runtime_state.gold = 90  # bet already deducted, as _start_blackjack would
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("9", "H"), ("8", "S")],
            "dealer_hand": [("8", "S"), ("8", "H")],
            "region_id": "town", "room_id": "town_square",
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("stand")
        self.assertIn("Dealer busts", result)
        # Bet is returned (+amount) and profit is separately granted via
        # _grant_party_profit's no-party fallback (+amount again) -- the same
        # even-money payout shape used by dice/slots/wheel.
        self.assertEqual(110, self.player.runtime_state.gold)
        self.assertIsNone(self.player.active_minigame)

    def test_stand_dealer_wins_outright(self):
        self.player.runtime_state.gold = 90
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("9", "H")],
            "dealer_hand": [("K", "S"), ("Q", "S")],  # dealer=20, stops drawing
            "region_id": "town", "room_id": "town_square",
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("stand")
        self.assertIn("Dealer wins", result)
        self.assertEqual(90, self.player.runtime_state.gold)  # no refund on a loss

    def test_stand_push_returns_wager(self):
        self.player.runtime_state.gold = 90
        self.player.active_minigame = {
            "type": "blackjack", "bet": 10, "hand": [("K", "H"), ("Q", "S")],
            "dealer_hand": [("K", "D"), ("Q", "D")],
            "region_id": "town", "room_id": "town_square",
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("stand")
        self.assertIn("Push", result)
        self.assertEqual(100, self.player.runtime_state.gold)


class TestGuessCommand(_CasinoTestBase):
    def _start_runebreaker(self, secret):
        self.player.active_minigame = {
            "type": "runebreaker", "bet": 10, "secret_code": secret, "attempts_left": 8,
            "region_id": "town", "room_id": "town_square",
            "symbols": ["fire", "water", "earth", "air"],
            "symbol_colors": {},
            "venue_name": "the Arcane Vault", "item_name": "element",
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.player.runtime_state.gold = 100

    def test_not_playing_is_reported(self):
        result = self.game.process_command("guess fire water earth")
        self.assertEqual("You are not playing Runebreaker.", result)

    def test_away_from_the_vault_is_rejected(self):
        self._start_runebreaker(["fire", "water", "earth"])
        self.player.current_region_id = "elsewhere"
        self.player.current_room_id = "elsewhere"
        result = self.game.process_command("guess fire water earth")
        self.assertIn("return to the Arcane Vault", result)

    def test_wrong_number_of_elements_is_rejected(self):
        self._start_runebreaker(["fire", "water", "earth"])
        result = self.game.process_command("guess fire water")
        self.assertIn("exactly 3 elements", result)

    def test_invalid_element_is_rejected(self):
        self._start_runebreaker(["fire", "water", "earth"])
        result = self.game.process_command("guess fire water lava")
        self.assertIn("Invalid element", result)

    def test_exact_guess_wins(self):
        self._start_runebreaker(["fire", "water", "earth"])
        result = self.game.process_command("guess fire water earth")
        self.assertIn("CODE BROKEN", result)
        self.assertEqual(150, self.player.runtime_state.gold)  # +10 refund +40 net win
        self.assertIsNone(self.player.active_minigame)

    def test_partial_guess_reports_remaining_attempts(self):
        self._start_runebreaker(["fire", "water", "earth"])
        result = self.game.process_command("guess air air air")
        self.assertIn("Attempts remaining", result)
        self.assertIsNotNone(self.player.active_minigame)

    def test_guess_with_right_element_wrong_position_counts_as_partial(self):
        self._start_runebreaker(["fire", "water", "earth"])
        # "water" and "earth" are both present but shifted out of position.
        result = self.game.process_command("guess air earth water")
        self.assertIn("2 Partial", result)

    def test_running_out_of_attempts_ends_the_game(self):
        self._start_runebreaker(["fire", "water", "earth"])
        self.player.active_minigame["attempts_left"] = 1
        result = self.game.process_command("guess air air air")
        self.assertIn("Out of attempts", result)
        self.assertIsNone(self.player.active_minigame)


class TestBlackjackNaturalOutcomes(_CasinoTestBase):
    @patch("engine.commands.gambling.draw_card")
    def test_natural_blackjack_wins(self, mock_draw):
        mock_draw.side_effect = [("A", "H"), ("K", "S"), ("2", "H"), ("3", "S")]
        self._place_dealer("card_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("BLACKJACK", result)
        self.assertEqual(115, self.player.runtime_state.gold)  # 100 -10 +10 +15
        self.assertIsNone(self.player.active_minigame)

    @patch("engine.commands.gambling.draw_card")
    def test_natural_blackjack_push_when_dealer_also_has_blackjack(self, mock_draw):
        mock_draw.side_effect = [("A", "H"), ("K", "S"), ("A", "D"), ("Q", "D")]
        self._place_dealer("card_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("Push", result)
        self.assertEqual(100, self.player.runtime_state.gold)


class TestDiceHighRoll(_CasinoTestBase):
    @patch("engine.commands.gambling.random.randint")
    def test_player_wins_on_higher_roll(self, mock_randint):
        mock_randint.side_effect = [90, 10]
        self._place_dealer("dice_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("You win", result)
        self.assertEqual(110, self.player.runtime_state.gold)

    @patch("engine.commands.gambling.random.randint")
    def test_player_loses_on_lower_roll(self, mock_randint):
        mock_randint.side_effect = [10, 90]
        self._place_dealer("dice_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("You lose", result)
        self.assertEqual(90, self.player.runtime_state.gold)


class TestSlots(_CasinoTestBase):
    @patch("engine.commands.gambling.random.choices")
    def test_jackpot_on_triple_match(self, mock_choices):
        mock_choices.return_value = ["[DRG]"]
        self._place_dealer("mechanical_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("Jackpot", result)
        self.assertEqual(1090, self.player.runtime_state.gold)  # 100 -10 +1000

    @patch("engine.commands.gambling.random.choices")
    def test_pair_returns_bet(self, mock_choices):
        mock_choices.side_effect = [["[DRG]"], ["[DRG]"], ["[SHD]"]]
        self._place_dealer("mechanical_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("Pair", result)
        self.assertEqual(100, self.player.runtime_state.gold)

    @patch("engine.commands.gambling.random.choices")
    def test_no_match_loses_bet(self, mock_choices):
        mock_choices.side_effect = [["[DRG]"], ["[SHD]"], ["[POT]"]]
        self._place_dealer("mechanical_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("No match", result)
        self.assertEqual(90, self.player.runtime_state.gold)

    @patch("engine.commands.gambling.random.choices")
    def test_jackpot_routes_profit_through_party_server(self, mock_choices):
        mock_choices.return_value = ["[DRG]"]
        self._place_dealer("mechanical_dealer")
        fake_server = MagicMock()
        fake_server.grant_party_gold.return_value = "Party profit shared!"
        with patch.object(self.world, "server", fake_server, create=True):
            result = self.game.process_command("bet 10")
        self.assertIn("Jackpot", result)
        self.assertIn("Party profit shared!", result)


class TestElementalWheel(_CasinoTestBase):
    @patch("engine.commands.gambling.random.choices")
    def test_winning_spin(self, mock_choices):
        mock_choices.return_value = [("AETHER", 10, "", 1)]
        self._place_dealer("wheel_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("Win", result)
        self.assertEqual(190, self.player.runtime_state.gold)

    @patch("engine.commands.gambling.random.choices")
    def test_losing_spin(self, mock_choices):
        mock_choices.return_value = [("VOID", 0, "", 60)]
        self._place_dealer("wheel_dealer")
        result = self.game.process_command("bet 10")
        self.assertIn("Loss", result)
        self.assertEqual(90, self.player.runtime_state.gold)

    @patch("engine.commands.gambling.random.choices")
    def test_winning_spin_routes_profit_through_party_server(self, mock_choices):
        mock_choices.return_value = [("AETHER", 10, "", 1)]
        self._place_dealer("wheel_dealer")
        fake_server = MagicMock()
        fake_server.grant_party_gold.return_value = "Party profit shared!"
        with patch.object(self.world, "server", fake_server, create=True):
            result = self.game.process_command("bet 10")
        self.assertIn("Win", result)
        self.assertIn("Party profit shared!", result)


class TestStartRunebreakerViaBet(_CasinoTestBase):
    def test_bet_starts_runebreaker(self):
        self._place_dealer("vault_keeper")
        result = self.game.process_command("bet 10")
        self.assertIn("Vault", result)
        self.assertIsNotNone(self.player.active_minigame)
        self.assertEqual("runebreaker", self.player.active_minigame["type"])
        self.assertEqual(90, self.player.runtime_state.gold)
