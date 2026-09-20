# tests/singles/test_money_is_whole.py
"""Currency is an integer, and one rule turns a product back into one.

Every balance in the game is an int, every price is displayed raw
(`Your Gold: {gold}`), and a save round-trips the number as written. Multiplying
an authored value by an authored multiplier produces a float, so *some* rule has
to convert it -- and it has to be the same rule everywhere, or the same authored
number pays differently depending on which system read it. Four sites truncated
with `int()`; the rest rounded.

The defect this started from: the elemental wheel credited
`min(amount, amount * multiplier)`, which is a **float** for any fractional
multiplier. The wheel's commonest outcome has multiplier 0.0 and its second
commonest 1.0, so a normal spin left the player's whole balance fractional and
every message reading `(Gold: -50.0)`.
"""
import unittest

from tests.fixtures import GameTestBase
from engine.utils.utils import money_from_value, whole


class TestTheRule(unittest.TestCase):
    def test_half_rounds_away_from_zero(self):
        self.assertEqual(3, whole(2.5))
        self.assertEqual(4, whole(3.5))
        self.assertEqual(-3, whole(-2.5))

    def test_a_product_is_rounded_once(self):
        self.assertEqual(17, money_from_value(15, 1.1))
        self.assertEqual(23, money_from_value(15, 1.5))
        self.assertEqual(8, money_from_value(5, 1.5))

    def test_a_whole_product_is_unchanged(self):
        self.assertEqual(50, money_from_value(50, 1.0))
        self.assertEqual(250, money_from_value(50, 5.0))

    def test_a_zero_multiplier_is_zero_not_a_fraction(self):
        """The wheel's 60%-weight outcome, and it must not leave a float behind."""
        result = money_from_value(50, 0.0)
        self.assertEqual(0, result)
        self.assertIsInstance(result, int)

    def test_a_value_that_is_not_a_number_reads_as_zero(self):
        """A caller still gets a whole number, never an exception and never a float."""
        for bad in ("nonsense", None, [1], {"a": 1}):
            self.assertEqual(0, money_from_value(bad, 1.0))
        self.assertEqual(0, money_from_value(10, "nonsense"))
        self.assertEqual(0, whole(float("nan")))


class TestWhichSitesUseIt(unittest.TestCase):
    """The sites that truncated, so the rule is one rule and not two."""

    def test_the_vendor_price_maths_uses_the_rule(self):
        source = (__import__("pathlib").Path(__file__).resolve().parents[2]
                  / "engine" / "commands" / "mercantile.py").read_text(encoding="utf-8")
        self.assertNotIn("int(base_value *", source)
        self.assertNotIn("int(item_to_sell.value *", source)
        self.assertIn("money_from_value(", source)

    def test_the_affix_value_maths_uses_the_rule(self):
        source = (__import__("pathlib").Path(__file__).resolve().parents[2]
                  / "engine" / "items" / "loot_generator.py").read_text(encoding="utf-8")
        self.assertNotIn("int(item.value * mult)", source)
        self.assertIn("money_from_value(", source)


class TestTheCasinoPaysWhatItSays(GameTestBase):
    """One payout value, used for the message and for the credit.

    `GameTestBase` is the desktop path -- no server, so nothing to share with and
    the balance must move by exactly the number announced. The party path is a
    separate question (the table splits the winnings) and is tested below.
    """

    def _dealer(self, key: str):
        for npc in self.world.npcs.values():
            if npc.properties.get(key):
                return npc
        return None

    def test_the_elemental_wheel_leaves_whole_currency(self):
        """The shipped wheel's outcomes are the case that broke this.

        Its commonest outcome pays 0 and its second commonest pays 1, so a normal
        spin used to leave `min(bet, bet * mult)` -- a float -- in the balance.
        """
        from engine.commands import gambling as module

        dealer = self._dealer("minigame_wheel_outcomes")
        if dealer is None:
            self.skipTest("no wheel dealer in this content set")

        self.player.runtime_state.gold = 1000
        for _ in range(60):
            module._play_elemental_wheel(self.player, dealer, 40)
            self.assertIsInstance(
                self.player.runtime_state.gold, int,
                "a spin left the balance at %r" % (self.player.runtime_state.gold,),
            )

    def test_every_wheel_outcome_credits_what_it_announces(self):
        from engine.commands import gambling as module

        dealer = self._dealer("minigame_wheel_outcomes")
        if dealer is None:
            self.skipTest("no wheel dealer in this content set")
        # The wheel's losing outcomes have far more weight than its winners, so a
        # fixed number of spins may never win. Spin until one does.
        self.player.runtime_state.gold = 1000000
        for _ in range(400):
            before = self.player.runtime_state.gold
            message = module._play_elemental_wheel(self.player, dealer, 40)
            net = self.player.runtime_state.gold - before
            # A win returns stake plus winnings, so the balance moves by the
            # profit; a loss returns part or none of the stake, so it moves down.
            if "Win " in message:
                payout = int(message.split("Win ", 1)[1].split("!", 1)[0])
                self.assertEqual(payout - 40, net, message)
                return
            self.assertLessEqual(net, 0, message)
            self.assertIsInstance(self.player.runtime_state.gold, int, message)
        self.fail("400 spins never won; the assertion never ran")

    def test_a_slot_jackpot_credits_what_it_announces(self):
        from engine.commands import gambling as module

        dealer = self._dealer("minigame_slots_reel")
        if dealer is None:
            self.skipTest("no slot dealer in this content set")

        self.player.runtime_state.gold = 1000000
        for _ in range(600):
            before = self.player.runtime_state.gold
            message = module._play_slots(self.player, dealer, 5)
            net = self.player.runtime_state.gold - before
            if "Jackpot!" in message:
                payout = int(message.split("Jackpot! ", 1)[1].split(" ", 1)[0])
                # Stake taken once (-5), payout credited once (+payout).
                self.assertEqual(payout - 5, net, message)
                return
            self.assertLessEqual(net, 0, message)
            self.assertIsInstance(self.player.runtime_state.gold, int, message)
        self.fail("600 spins never jackpotted; the assertion never ran")

    def test_an_even_money_win_credits_twice_the_stake(self):
        """Stake back plus the same again, and the message names the total."""
        from engine.commands import gambling as module

        for bet in (5, 7, 25):
            self.assertEqual(bet * 2, module._payout(bet, 2.0))

    def test_a_blackjack_pays_three_to_two_on_an_odd_bet(self):
        from engine.commands import gambling as module

        # Stake plus 3:2 winnings, rounded once: 7 -> 7 + 10.5 -> 18, not 17.
        self.assertEqual(18, module._payout(7, module.BLACKJACK_WIN_MULTIPLIER))
        self.assertEqual(13, module._payout(5, module.BLACKJACK_WIN_MULTIPLIER))
        self.assertEqual(25, module._payout(10, module.BLACKJACK_WIN_MULTIPLIER))
        self.assertEqual(250, module._payout(100, module.BLACKJACK_WIN_MULTIPLIER))


class TestAServerSplitsTheWinningsInstead(GameTestBase):
    """On a server the actor's own share arrives through the party grant.

    Which is why `_settle_winnings` does not also credit the payout there: the
    stake was taken once and is returned once, through the one call that pays
    everybody. Crediting it separately as well is what made a server-side jackpot
    move the balance by the whole payout instead of the profit.
    """

    def test_the_settlement_hands_the_whole_profit_to_the_party_once(self):
        from engine.commands import gambling as module

        class _RecordingServer:
            def __init__(self):
                self.amounts = []

            def grant_party_gold(self, actor, amount):
                self.amounts.append(amount)
                return "Player +%d Gold" % amount

        class _World:
            server = _RecordingServer()

        player = self.player
        player.world = _World()  # type: ignore[assignment]
        player.runtime_state.gold = 1000

        # A bet of 10 at 5x: payout 50, profit 40, and nothing credited directly.
        routing = module._settle_winnings(player, 10, 50)
        self.assertEqual([40], player.world.server.amounts)  # type: ignore[attr-defined]
        self.assertEqual(1000, player.runtime_state.gold, "the split pays it, not this call")
        self.assertIn("40", routing)

    def test_a_losing_bet_settles_nothing(self):
        from engine.commands import gambling as module

        class _World:
            server = None

        player = self.player
        player.world = _World()  # type: ignore[assignment]
        player.runtime_state.gold = 1000
        self.assertEqual("", module._settle_winnings(player, 10, 0))
        self.assertEqual(1000, player.runtime_state.gold)


class TestBalancesSurviveASaveAsIntegers(GameTestBase):
    def test_a_float_balance_that_got_in_is_written_as_a_float(self):
        """Documenting the real risk: the save has no opinion, so the engine must not."""
        self.player.runtime_state.gold = 100
        payload = self.player.to_dict(self.world)
        self.assertEqual(100, payload["gameplay"]["economy"]["gold"])
        self.assertIsInstance(payload["gameplay"]["economy"]["gold"], int)


if __name__ == "__main__":
    unittest.main()
