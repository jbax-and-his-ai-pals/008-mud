# tests/singles/test_game_object_full.py
"""Coverage for engine/game_object.py: get_description, from_dict,
get_effective_stat's resist_ prefix, has_effect_tag's string-tag form,
take_damage's dead/non-positive guard and damage-reaction branches (no
action, missing tag), the floating-text world/game/renderer guards,
heal()'s base no-op, apply_effect's dead guard, remove_effects_by_tag's
string-tag form, and process_active_effects' already-dead-with-effects
clear, error-parsing print, DoT/HoT cooldown-not-elapsed and zero-effect
skips, an NPC HoT message, a Player death-mid-loop message, a failed
removal skip, and an NPC "wears off" message.

Note: process_active_effects' `for name in expired_effect_names: if
name:` False arm is unreachable -- expired_effect_names is only ever
populated inside the `if effect_name:` branch a few lines earlier (the
`else` for a missing name takes `continue` instead of appending), so
every entry in the list is already guaranteed truthy. Left untested as
dead code, consistent with this codebase's established precedent."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.game_object import GameObject
from engine.npcs.npc import NPC


class TestBasics(unittest.TestCase):
    def test_get_description(self):
        obj = GameObject(name="Rock", description="A plain rock.")
        self.assertEqual(obj.get_description(), "Rock\n\nA plain rock.")

    def test_from_dict_restores_fields(self):
        data = {"obj_id": "rock_1", "name": "Rock", "description": "A rock.",
                "properties": {"foo": "bar"}, "is_alive": False}
        obj = GameObject.from_dict(data)
        self.assertEqual(obj.obj_id, "rock_1")
        self.assertEqual(obj.properties, {"foo": "bar"})
        self.assertFalse(obj.is_alive)

    def test_get_effective_stat_with_resist_prefix_delegates_to_resistance(self):
        obj = GameObject(name="Test")
        obj.stats["resistances"] = {"fire": 25}
        self.assertEqual(obj.get_effective_stat("resist_fire"), 25)

    def test_has_effect_tag_string_form_matches(self):
        obj = GameObject(name="Test")
        obj.active_effects.append({"name": "Poison", "tags": "poison"})
        self.assertTrue(obj.has_effect_tag("poison"))

    def test_has_effect_tag_loops_past_non_matching_effects(self):
        obj = GameObject(name="Test")
        obj.active_effects.append({"name": "Malformed", "tags": None})  # neither list nor str
        obj.active_effects.append({"name": "Debuff", "tags": "curse"})  # str, doesn't match
        obj.active_effects.append({"name": "Poison", "tags": ["poison"]})
        self.assertTrue(obj.has_effect_tag("poison"))

    def test_heal_base_implementation_is_a_noop(self):
        obj = GameObject(name="Test")
        self.assertEqual(obj.heal(50), 0)

    def test_remove_effects_by_tag_string_form_matches(self):
        obj = GameObject(name="Test")
        obj.active_effects.append({"name": "Malformed", "tags": None})  # neither list nor str
        obj.active_effects.append({"name": "Buff", "tags": "strength"})
        obj.active_effects.append({"name": "Curse", "tags": "curse"})
        removed = obj.remove_effects_by_tag("curse")
        self.assertEqual(removed, ["Curse"])
        remaining_names = [e["name"] for e in obj.active_effects]
        self.assertIn("Buff", remaining_names)
        self.assertIn("Malformed", remaining_names)


class TestTakeDamageGuardsAndReactions(unittest.TestCase):
    def test_dead_object_takes_no_damage(self):
        obj = GameObject(name="Test")
        obj.is_alive = False
        self.assertEqual(obj.take_damage(10, "physical"), 0)

    def test_non_positive_amount_takes_no_damage(self):
        obj = GameObject(name="Test")
        self.assertEqual(obj.take_damage(0, "physical"), 0)

    def test_damage_reaction_with_no_action_is_a_noop(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.properties["damage_reactions"] = {"fire": {}}
        obj.take_damage(5, "fire")  # must not raise despite no "action" key

    def test_damage_reaction_remove_tag_with_no_tag_is_a_noop(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.properties["damage_reactions"] = {"fire": {"action": "remove_effect_tag"}}
        obj.take_damage(5, "fire")  # must not raise despite no "tag" key


class TestTakeDamageFloatingText(GameTestBase):
    def test_no_world_attribute_skips_floating_text(self):
        obj = GameObject(name="Test")
        obj.health = 100
        # No .world attribute at all -- getattr(self, 'world', None) is None.
        obj.take_damage(10, "physical")  # must not raise

    def test_world_without_game_skips_floating_text(self):
        npc = NPC(name="Test NPC")
        npc.health = 100
        npc.world = object()  # has no `.game` attribute
        npc.take_damage(10, "physical")  # must not raise

    def test_world_with_game_but_no_renderer_skips_floating_text(self):
        npc = NPC(name="Test NPC")
        npc.health = 100

        class _GameNoRenderer:
            pass

        class _WorldStub:
            game = _GameNoRenderer()

        npc.world = _WorldStub()
        npc.take_damage(10, "physical")  # must not raise


class TestApplyEffectGuard(unittest.TestCase):
    def test_dead_object_cannot_be_affected(self):
        obj = GameObject(name="Test")
        obj.is_alive = False
        success, msg = obj.apply_effect({"name": "Poison"}, time.time())
        self.assertFalse(success)
        self.assertIn("cannot be affected", msg)


class TestProcessActiveEffects(unittest.TestCase):
    def test_already_dead_object_clears_effects_and_returns_nothing(self):
        obj = GameObject(name="Test")
        obj.is_alive = False
        obj.active_effects.append({"name": "Stale Effect"})
        messages = obj.process_active_effects(time.time(), 1.0)
        self.assertEqual(messages, [])
        self.assertEqual(obj.active_effects, [])

    def test_expired_effect_with_no_name_logs_parse_error(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.active_effects.append({"duration_remaining": -1})  # no "name" key
        with patch("builtins.print") as mock_print:
            obj.process_active_effects(time.time(), 1.0)
        self.assertTrue(any("error parsing effect_name" in str(c) for c in mock_print.call_args_list))

    def test_dot_before_tick_interval_deals_no_damage(self):
        obj = GameObject(name="Test")
        obj.health = 100
        now = time.time()
        obj.active_effects.append({
            "name": "Poison", "type": "dot", "tick_interval": 100.0,
            "last_tick_time": now, "damage_per_tick": 10, "damage_type": "physical",
        })
        messages = obj.process_active_effects(now + 1.0, 1.0)
        self.assertEqual(messages, [])
        self.assertEqual(obj.health, 100)

    def test_dot_with_zero_damage_produces_no_message(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.stats["defense"] = 9999
        now = time.time()
        obj.active_effects.append({
            "name": "Weak Poison", "type": "dot", "tick_interval": 0,
            "last_tick_time": 0, "damage_per_tick": 1, "damage_type": "physical",
        })
        messages = obj.process_active_effects(now, 1.0)
        self.assertEqual(messages, [])

    def test_hot_before_tick_interval_heals_nothing(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.heal = lambda amount: amount  # simple pass-through for this test
        now = time.time()
        obj.active_effects.append({
            "name": "Regen", "type": "hot", "tick_interval": 100.0,
            "last_tick_time": now, "heal_per_tick": 10,
        })
        messages = obj.process_active_effects(now + 1.0, 1.0)
        self.assertEqual(messages, [])

    def test_hot_with_zero_heal_produces_no_message(self):
        obj = GameObject(name="Test")
        obj.health = 100
        # Base heal() always returns 0, so healed_for > 0 is never true here.
        obj.active_effects.append({
            "name": "Weak Regen", "type": "hot", "tick_interval": 0,
            "last_tick_time": 0, "heal_per_tick": 10,
        })
        messages = obj.process_active_effects(time.time(), 1.0)
        self.assertEqual(messages, [])

    def test_npc_hot_message_names_the_npc(self):
        npc = NPC(name="Healable NPC")
        npc.health = 50
        npc.heal = lambda amount: amount
        npc.active_effects.append({
            "name": "Regen", "type": "hot", "tick_interval": 0,
            "last_tick_time": 0, "heal_per_tick": 10,
        })
        messages = npc.process_active_effects(time.time(), 1.0)
        self.assertTrue(any("Healable NPC is healed" in m for m in messages))

    def test_npc_wears_off_message_names_the_npc(self):
        npc = NPC(name="Cursed NPC")
        npc.health = 100
        npc.active_effects.append({
            "name": "Curse", "duration_remaining": 0.01,
        })
        messages = npc.process_active_effects(time.time(), 1.0)
        self.assertTrue(any("Curse" in m and "Cursed NPC" in m for m in messages))

    def test_failed_effect_removal_appends_no_wears_off_message(self):
        obj = GameObject(name="Test")
        obj.health = 100
        obj.active_effects.append({"name": "Fading Effect", "duration_remaining": 0.01})
        with patch.object(obj, "remove_effect", return_value=False):
            messages = obj.process_active_effects(time.time(), 1.0)
        self.assertEqual(messages, [])


class TestPlayerDeathMidLoop(GameTestBase):
    def test_death_mid_loop_appends_succumb_message_for_player(self):
        self.player.health = 1
        self.player.max_health = 100
        self.player.active_effects.append({
            "name": "Lethal Poison", "type": "dot", "tick_interval": 0,
            "last_tick_time": 0, "damage_per_tick": 9999, "damage_type": "physical",
        })
        messages = self.player.process_active_effects(time.time(), 1.0)
        self.assertTrue(any("succumb" in m for m in messages))
        self.assertFalse(self.player.is_alive)
        self.assertEqual(self.player.active_effects, [])
        self.assertEqual(self.player.stat_modifiers, {})


if __name__ == "__main__":
    unittest.main()
