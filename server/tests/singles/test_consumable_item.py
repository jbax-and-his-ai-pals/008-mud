# tests/singles/test_consumable_item.py
"""Coverage for engine/items/consumable.py's use() effect dispatch (heal,
mana_restore, learn_spell, apply_dot), the used-up/uses-remaining messaging,
and examine()'s uses-remaining display -- previously entirely untested."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.consumable import Consumable


class TestConsumableConstructor(GameTestBase):
    def test_single_use_item_is_stackable(self):
        c = Consumable(obj_id="c1", name="Potion", uses=1)
        self.assertTrue(c.stackable)

    def test_multi_use_item_is_not_stackable(self):
        c = Consumable(obj_id="c2", name="Wand", uses=5)
        self.assertFalse(c.stackable)

    def test_explicit_stackable_false_is_honored_despite_single_use(self):
        # Bug: a template can explicitly mark a single-use item non-stackable
        # (e.g. a unique learn-spell scroll, so distinct instances don't
        # collapse into one inventory slot) -- this used to be silently
        # discarded in favor of the uses==1 heuristic.
        c = Consumable(obj_id="c1b", name="Unique Scroll", uses=1, stackable=False)
        self.assertFalse(c.stackable)
        self.assertFalse(c.get_property("stackable"))

    def test_explicit_stackable_true_is_honored_despite_multi_use(self):
        c = Consumable(obj_id="c2b", name="Bundle", uses=5, stackable=True)
        self.assertTrue(c.stackable)
        self.assertTrue(c.get_property("stackable"))


class TestConsumableUseHeal(GameTestBase):
    def test_already_used_up_reports_so(self):
        c = Consumable(obj_id="c3", name="Empty Vial", uses=0, effect_type="heal")
        result = c.use(self.player)
        self.assertIn("already been used up", result)

    def test_heal_effect_reports_amount_healed(self):
        self.player.health = 1
        c = Consumable(obj_id="c4", name="Potion", uses=1, effect_type="heal", effect_value=20)
        result = c.use(self.player)
        self.assertIn("regain", result)
        self.assertIn("used up", result)

    def test_heal_effect_at_full_health_reports_no_difference(self):
        self.player.health = self.player.max_health
        c = Consumable(obj_id="c5", name="Potion", uses=1, effect_type="heal", effect_value=20)
        result = c.use(self.player)
        self.assertIn("feel no different", result)

    def test_heal_effect_on_target_without_heal_method(self):
        class _NoHeal:
            pass
        c = Consumable(obj_id="c6", name="Potion", uses=1, effect_type="heal")
        result = c.use(_NoHeal())
        self.assertIn("no effect", result)


class TestConsumableUseManaRestore(GameTestBase):
    def test_mana_restore_reports_amount(self):
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 0
        c = Consumable(obj_id="c7", name="Mana Potion", uses=1, effect_type="mana_restore", effect_value=10)
        result = c.use(self.player)
        self.assertIn("regain", result)
        self.assertIn("mana", result)

    def test_mana_restore_at_full_mana_reports_already_full(self):
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = self.player.runtime_state.magic.max_mana
        c = Consumable(obj_id="c8", name="Mana Potion", uses=1, effect_type="mana_restore", effect_value=10)
        result = c.use(self.player)
        self.assertIn("already full", result)

    def test_mana_restore_on_target_without_method(self):
        class _NoMana:
            pass
        c = Consumable(obj_id="c9", name="Mana Potion", uses=1, effect_type="mana_restore")
        result = c.use(_NoMana())
        self.assertIn("no effect", result)


class TestConsumableUseLearnSpell(GameTestBase):
    def test_missing_spell_to_learn_reports_misconfigured(self):
        c = Consumable(obj_id="c10", name="Blank Scroll", uses=1, effect_type="learn_spell")
        result = c.use(self.player)
        self.assertIn("inert or misconfigured", result)

    def test_target_without_learn_spell_method(self):
        class _NoLearn:
            pass
        c = Consumable(obj_id="c11", name="Scroll", uses=1, effect_type="learn_spell")
        c.properties["spell_to_learn"] = "fireball"
        result = c.use(_NoLearn())
        self.assertIn("cannot", result)

    def test_successful_spell_learning_consumes_scroll(self):
        c = Consumable(obj_id="c12", name="Scroll of Fireball", uses=1, effect_type="learn_spell")
        c.properties["spell_to_learn"] = "magic_missile"
        with patch.object(self.player, "learn_spell", return_value=(True, "You learn Magic Missile!")):
            result = c.use(self.player)
        self.assertIn("You learn Magic Missile!", result)
        self.assertEqual(0, c.get_property("uses"))

    def test_failed_spell_learning_does_not_consume_scroll(self):
        c = Consumable(obj_id="c13", name="Scroll of Fireball", uses=1, effect_type="learn_spell")
        c.properties["spell_to_learn"] = "magic_missile"
        with patch.object(self.player, "learn_spell", return_value=(False, "You already know that.")):
            result = c.use(self.player)
        self.assertIn("You already know that.", result)
        self.assertEqual(1, c.get_property("uses"))

    def test_learn_spell_message_is_left_unformatted(self):
        # Bug: this branch used to wrap learn_spell()'s own message in
        # FORMAT_SUCCESS/FORMAT_ERROR, and use_handler wraps the whole
        # Consumable.use() result in FORMAT_HIGHLIGHT on top of that --
        # doubling up color tags (e.g. "[[GREEN]][[RED]]...[[/]][[/]]").
        c = Consumable(obj_id="c13b", name="Scroll of Fireball", uses=1, effect_type="learn_spell")
        c.properties["spell_to_learn"] = "magic_missile"
        with patch.object(self.player, "learn_spell", return_value=(False, "You lack the experience.")):
            result = c.use(self.player)
        self.assertEqual("You lack the experience.", result)


class TestConsumableUseApplyDot(GameTestBase):
    def _dot_consumable(self, obj_id="c14"):
        c = Consumable(obj_id=obj_id, name="Poison Vial", uses=1, effect_type="apply_dot")
        c.properties.update({
            "dot_name": "Poison", "dot_duration": 10, "dot_damage_per_tick": 2,
            "dot_tick_interval": 2, "dot_damage_type": "poison",
        })
        return c

    def test_incompletely_configured_dot_reports_misconfigured(self):
        c = Consumable(obj_id="c15", name="Bad Vial", uses=1, effect_type="apply_dot")
        result = c.use(self.player)
        self.assertIn("improperly configured", result)

    def test_target_without_apply_effect_method(self):
        class _NoEffect:
            pass
        c = self._dot_consumable()
        result = c.use(_NoEffect())
        self.assertIn("can't seem to apply", result)

    def test_successful_dot_application(self):
        c = self._dot_consumable()
        with patch.object(self.player, "apply_effect", return_value=(True, "")):
            result = c.use(self.player)
        self.assertIn("sickly sensation", result)

    def test_failed_dot_application(self):
        c = self._dot_consumable()
        with patch.object(self.player, "apply_effect", return_value=(False, "")):
            result = c.use(self.player)
        self.assertIn("nothing seems to happen", result)


class TestConsumableUsesRemainingMessaging(GameTestBase):
    def test_multi_use_item_reports_remaining_uses(self):
        c = Consumable(obj_id="c16", name="Bandages", uses=3, effect_type="heal", effect_value=1)
        self.player.health = 1
        result = c.use(self.player)
        self.assertIn("2/3 uses remaining", result)

    def test_unrecognized_effect_type_still_consumes(self):
        c = Consumable(obj_id="c17", name="Weird Item", uses=1, effect_type="totally_unknown")
        result = c.use(self.player)
        self.assertIn("used up", result)


class TestConsumableExamine(GameTestBase):
    def test_single_use_examine_has_no_uses_remaining_line(self):
        c = Consumable(obj_id="c18", name="Potion", uses=1)
        result = c.examine()
        self.assertNotIn("Uses remaining", result)

    def test_multi_use_examine_shows_uses_remaining(self):
        c = Consumable(obj_id="c19", name="Bandages", uses=5)
        result = c.examine()
        self.assertIn("Uses remaining: 5/5", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
