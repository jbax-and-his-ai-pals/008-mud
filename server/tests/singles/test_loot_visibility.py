# tests/singles/test_loot_visibility.py
"""Killing something must tell the player the loot is there, and how to get it.

The defect: after a kill the game printed only

    A lone giant rat (Level 1, 0/8 HP) dropped a rat tail.

with the player's inventory unchanged. The items were correctly placed in the
room (`World.add_item_to_room`), but nothing said where they went or that they
could be picked up, so the game's main reward moment read as a bug -- the audit
recorded "inventory unchanged after a kill" as a top-five first-hour friction.

The nudge is content-authored (ruleset `loot.take_hint`) and must not appear to
a player who is merely watching someone else's fight.
"""

import unittest

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.utils.utils import format_loot_drop_message, _loot_take_hint


class TestLootVisibility(GameTestBase):

    def _item(self, template_id="item_rat_tail", name=None):
        item = ItemFactory.create_item_from_template(template_id, self.world)
        self.assertIsNotNone(item, "test needs a real item template: %s" % template_id)
        if name is not None:
            item.name = name
        return item

    def test_kill_message_says_loot_can_be_taken(self):
        """The message body must mention taking the loot, not only that it dropped."""
        item = self._item()
        message = format_loot_drop_message(self.player, self._victim(), [item])
        self.assertIn("dropped", message.lower())
        self.assertIn(
            "take", message.lower(),
            "drop message does not tell the player the loot can be picked up",
        )

    def test_hint_names_the_dropped_item(self):
        """Naming the item makes the suggested command copy-pasteable."""
        item = self._item(name="rat tail")
        message = format_loot_drop_message(self.player, self._victim(), [item])
        self.assertIn("rat tail", message)

    def test_authored_hint_wording_is_used(self):
        """Content owns the wording; the engine must not hardcode its own."""
        item = self._item()
        loot_rules = self.world.ruleset_section("loot") or {}
        authored = loot_rules.get("take_hint")
        self.assertTrue(authored, "fantasy_frontier should author loot.take_hint")

        hint = _loot_take_hint(self.player, self._victim(), [item], 1)
        self.assertEqual(hint, authored.format(items=item.name, count=1))

    def test_a_content_set_can_suppress_the_hint(self):
        """`take_hint: false` (or empty) must silence it, not fall back loudly."""
        item = self._item()
        original = (self.world.ruleset_section("loot") or {}).get("take_hint")

        class _Rules:
            def ruleset_section(self, name):
                return {"take_hint": False} if name == "loot" else {}

        # Swap in a minimal ruleset view for the call.
        real_world = self.player.world
        try:
            self.player.world = _Rules()
            self.assertEqual(_loot_take_hint(self.player, self._victim(), [item], 1), "")
        finally:
            self.player.world = real_world
        self.assertEqual((self.world.ruleset_section("loot") or {}).get("take_hint"), original)

    def test_no_drop_means_no_message(self):
        self.assertEqual(format_loot_drop_message(self.player, self._victim(), []), "")

    def test_bystander_is_not_told_to_rummage(self):
        """A viewer who is not the looter gets no pickup nudge."""
        item = self._item()
        other = _OtherPlayer()
        message = format_loot_drop_message(other, self._victim(), [item])
        self.assertIn("dropped", message.lower())
        self.assertNotIn("take", message.lower())

    def test_hint_survives_a_malformed_authored_placeholder(self):
        """An authored hint with an unknown placeholder must not break a kill."""
        item = self._item()

        class _Rules:
            def ruleset_section(self, name):
                return {"take_hint": "Type 'take' ({bogus} here)."} if name == "loot" else {}

        real_world = self.player.world
        try:
            self.player.world = _Rules()
            hint = _loot_take_hint(self.player, self._victim(), [item], 1)
        finally:
            self.player.world = real_world
        self.assertIn("take", hint.lower())

    # -- helpers ---------------------------------------------------------

    def _victim(self):
        """The killed thing. Its identity is irrelevant to the hint, which keys
        off the viewer; a stand-in keeps the test focused."""

        class _Victim:
            name = "a lone giant rat"
            obj_id = "victim"

        return _Victim()


class _OtherPlayer:
    """A viewer that is not this fixture's player, to prove the hint is
    addressed to the looter only."""

    name = "Someone Else"
    obj_id = "someone_else"
    world = None

    def __init__(self):
        self.world = None


if __name__ == "__main__":
    unittest.main()
