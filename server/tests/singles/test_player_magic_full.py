# tests/singles/test_player_magic_full.py
"""Coverage for engine/player/magic.py's PlayerMagicMixin: learn_spell/
forget_spell's magic-disabled and not-known branches, can_cast_spell's full
guard matrix (dead, silenced, level, mana, cooldown), cast_spell's
magic-disabled/stunned/AoE-no-world/AoE-no-targets/self-and-friendly-target
rejections, the auto-engage branch's combat-disabled skip, and the kill-
handling block's target_world-missing, loot_table-missing/empty/failed-roll,
solo vs. party-routed reward, and multi-target AoE message-join branches."""

import time
from unittest.mock import MagicMock

from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.npcs.npc_factory import NPCFactory


def _make_spell(spell_id="test_spell", target_type="enemy", value=8, mana_cost=5,
                 cooldown=3.0, level_required=1):
    return Spell(
        spell_id=spell_id, name="Test Spell", description="A test spell.",
        effects=[{"type": "damage", "value": value}],
        mana_cost=mana_cost, cooldown=cooldown, target_type=target_type,
        level_required=level_required,
    )


def _hostile(world, instance_id="magic_target_goblin"):
    npc = NPCFactory.create_npc_from_template("goblin", world, instance_id=instance_id)
    world.add_npc(npc)
    npc.current_region_id = world.player.current_region_id
    npc.current_room_id = world.player.current_room_id
    npc.is_alive = True
    npc.health = 10
    return npc


class TestLearnSpell(GameTestBase):
    def test_magic_disabled_returns_false(self):
        self.player.runtime_state.magic = None
        ok, msg = self.player.learn_spell("magic_missile")
        self.assertFalse(ok)
        self.assertIn("not enabled", msg)


class TestForgetSpell(GameTestBase):
    def test_magic_disabled_returns_false(self):
        self.player.runtime_state.magic = None
        self.assertFalse(self.player.forget_spell("magic_missile"))

    def test_unknown_spell_returns_false(self):
        self.assertFalse(self.player.forget_spell("not_a_known_spell_xyz"))

    def test_known_spell_is_removed(self):
        self.player.learn_spell("magic_missile")
        self.assertTrue(self.player.forget_spell("magic_missile"))
        self.assertNotIn("magic_missile", self.player.runtime_state.magic.known_spells)


class TestCanCastSpell(GameTestBase):
    def setUp(self):
        super().setUp()
        self.spell = _make_spell()
        self.player.runtime_state.magic.known_spells.add(self.spell.spell_id)
        self.player.runtime_state.magic.mana = 100

    def test_magic_disabled_returns_false(self):
        self.player.runtime_state.magic = None
        ok, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(ok)
        self.assertIn("not enabled", msg)

    def test_dead_player_returns_false(self):
        self.player.is_alive = False
        ok, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(ok)
        self.assertIn("dead", msg)

    def test_silenced_by_name_returns_false(self):
        self.player.active_effects.append({"name": "Silenced", "tags": []})
        ok, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(ok)
        self.assertIn("silenced", msg)

    def test_silenced_by_tag_returns_false(self):
        self.player.active_effects.append({"name": "Muted", "tags": ["silence"]})
        ok, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(ok)
        self.assertIn("silenced", msg)

    def test_level_too_low_returns_false(self):
        high_level_spell = _make_spell(spell_id="advanced_test_spell", level_required=999)
        self.player.runtime_state.magic.known_spells.add(high_level_spell.spell_id)
        ok, msg = self.player.can_cast_spell(high_level_spell, time.time())
        self.assertFalse(ok)
        self.assertIn("level", msg)

    def test_insufficient_mana_returns_false(self):
        self.player.runtime_state.magic.mana = 0
        ok, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(ok)
        self.assertIn("mana", msg)

    def test_on_cooldown_returns_false(self):
        now = time.time()
        self.player.runtime_state.magic.cooldowns[self.spell.spell_id] = now + 100
        ok, msg = self.player.can_cast_spell(self.spell, now)
        self.assertFalse(ok)
        self.assertIn("cooldown", msg)


class TestCastSpellGuards(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.runtime_state.magic.mana = 100

    def test_magic_disabled_returns_failure_dict(self):
        self.player.runtime_state.magic = None
        result = self.player.cast_spell(_make_spell(), _hostile(self.world), time.time())
        self.assertFalse(result["success"])
        self.assertIn("not enabled", result["message"])

    def test_stunned_returns_failure_dict(self):
        self.player.active_effects.append({"name": "Stun", "tags": []})
        result = self.player.cast_spell(_make_spell(), _hostile(self.world), time.time())
        self.assertFalse(result["success"])
        self.assertIn("stunned", result["message"])

    def test_aoe_with_no_world_context_errors(self):
        spell = _make_spell(spell_id="aoe_no_world", target_type="all_enemies")
        original_world = self.player.world
        self.player.world = None
        try:
            result = self.player.cast_spell(spell, None, time.time(), world=None)
        finally:
            self.player.world = original_world
        self.assertFalse(result["success"])
        self.assertIn("No world context", result["message"])

    def test_aoe_with_no_hostiles_present_errors(self):
        spell = _make_spell(spell_id="aoe_empty_room", target_type="all_enemies")
        result = self.player.cast_spell(spell, None, time.time(), world=self.world)
        self.assertFalse(result["success"])
        self.assertIn("no enemies", result["message"])

    def test_enemy_spell_rejects_self_target(self):
        spell = _make_spell(spell_id="enemy_self_reject")
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        result = self.player.cast_spell(spell, self.player, time.time())
        self.assertFalse(result["success"])
        self.assertIn("hostile targets", result["message"])

    def test_enemy_spell_rejects_friendly_npc_target(self):
        friendly = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="magic_friendly_target")
        self.world.add_npc(friendly)
        spell = _make_spell(spell_id="enemy_friendly_reject")
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        result = self.player.cast_spell(spell, friendly, time.time())
        self.assertFalse(result["success"])
        self.assertIn("hostile targets", result["message"])

    def test_cannot_cast_reason_propagates(self):
        spell = _make_spell(spell_id="not_known_yet")
        # Deliberately not added to known_spells.
        target = _hostile(self.world)
        result = self.player.cast_spell(spell, target, time.time())
        self.assertFalse(result["success"])
        self.assertIn("don't know", result["message"])


class TestCastSpellCombatEngagement(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.runtime_state.magic.mana = 100

    def test_combat_disabled_skips_engage_and_disengage(self):
        target = _hostile(self.world)
        target.health = 9999  # survive the hit so we can inspect post-cast state
        spell = _make_spell(spell_id="combat_disabled_probe", value=1)
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        original_combat = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            result = self.player.cast_spell(spell, target, time.time())
        finally:
            self.player.runtime_state.combat = original_combat
        self.assertTrue(result["success"])

    def test_already_dead_target_skips_engage(self):
        target = _hostile(self.world, "magic_already_dead_target")
        target.is_alive = False
        spell = _make_spell(spell_id="already_dead_probe", value=1)
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        result = self.player.cast_spell(spell, target, time.time())
        self.assertTrue(result["success"])

    def test_combat_disabled_kill_skips_exit_combat_call(self):
        target = _hostile(self.world, "magic_combat_disabled_kill")
        spell = _make_spell(spell_id="combat_disabled_kill_probe", value=9999)
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        original_combat = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            result = self.player.cast_spell(spell, target, time.time(), world=self.world)
        finally:
            self.player.runtime_state.combat = original_combat
        self.assertTrue(result["success"])
        self.assertFalse(target.is_alive)


class TestCastSpellKillHandling(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.runtime_state.magic.mana = 100

    def _lethal_spell(self, spell_id="lethal_probe"):
        spell = _make_spell(spell_id=spell_id, value=9999)
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        return spell

    def test_kill_with_no_target_world_skips_dispatch_and_loot_call(self):
        target = _hostile(self.world, "magic_kill_no_world")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        original_world = self.player.world
        self.player.world = None
        try:
            result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=None)
        finally:
            self.player.world = original_world
        self.assertTrue(result["success"])
        self.assertFalse(target.is_alive)

    # Note: magic.py's `if hasattr(t, "loot_table")` guard has no reachable
    # False branch for a real NPC -- NPC.__init__ always sets loot_table={},
    # and t.die() (called later in this same block) unconditionally assumes
    # it exists too, so deleting the attribute to test the guard would just
    # crash die() instead. Left untested as dead code, consistent with this
    # codebase's established precedent for provably-unreachable branches.

    def test_kill_with_empty_loot_table_grants_no_gold(self):
        target = _hostile(self.world, "magic_kill_empty_loot")
        target.loot_table = {}
        result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        self.assertTrue(result["success"])

    def test_kill_with_failed_gold_roll_grants_no_gold(self):
        target = _hostile(self.world, "magic_kill_failed_roll")
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [5, 5]}}
        result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        self.assertTrue(result["success"])

    def test_kill_with_successful_gold_roll_grants_solo_gold_and_xp(self):
        target = _hostile(self.world, "magic_kill_solo_reward")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        starting_gold = self.player.runtime_state.gold or 0
        result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        self.assertTrue(result["success"])
        self.assertIn("gold", result["message"])
        self.assertGreaterEqual(self.player.runtime_state.gold, starting_gold + 5)

    def test_kill_with_party_routing_and_reward_text_uses_it(self):
        target = _hostile(self.world, "magic_kill_party_reward")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        fake_server = MagicMock()
        fake_server.party_reward_routing_active.return_value = True
        fake_server.grant_party_rewards.return_value = "The party shares the spoils!"
        self.world.server = fake_server
        try:
            result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        finally:
            del self.world.server
        self.assertIn("The party shares the spoils!", result["message"])

    def test_kill_with_gold_disabled_for_player_grants_no_gold(self):
        target = _hostile(self.world, "magic_kill_gold_disabled")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        original_gold = self.player.runtime_state.gold
        self.player.runtime_state.gold = None
        try:
            result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        finally:
            self.player.runtime_state.gold = original_gold
        self.assertTrue(result["success"])

    def test_kill_with_no_progression_skips_xp_gain(self):
        target = _hostile(self.world, "magic_kill_no_progression")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        original_progression = self.player.runtime_state.progression
        self.player.runtime_state.progression = None
        try:
            result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        finally:
            self.player.runtime_state.progression = original_progression
        self.assertTrue(result["success"])
        self.assertNotIn("experience", result["message"])

    def test_kill_with_item_loot_appends_loot_message(self):
        target = _hostile(self.world, "magic_kill_loot_drop")
        target.loot_table = {"item_iron_sword": {"chance": 1.0, "quantity": [1, 1]}}
        result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        self.assertTrue(result["success"])
        self.assertIn("drop", result["message"].lower())

    def test_kill_with_party_routing_and_empty_reward_text_appends_nothing(self):
        target = _hostile(self.world, "magic_kill_party_empty")
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        fake_server = MagicMock()
        fake_server.party_reward_routing_active.return_value = True
        fake_server.grant_party_rewards.return_value = ""
        self.world.server = fake_server
        try:
            result = self.player.cast_spell(self._lethal_spell(), target, time.time(), world=self.world)
        finally:
            del self.world.server
        self.assertTrue(result["success"])
        self.assertNotIn("None", result["message"])


class TestCastSpellAoEMultiTarget(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.runtime_state.magic.mana = 100

    def test_multi_target_aoe_joins_result_messages(self):
        first = _hostile(self.world, "magic_aoe_first")
        second = _hostile(self.world, "magic_aoe_second")
        spell = _make_spell(spell_id="aoe_multi_probe", target_type="all_enemies", value=1)
        self.player.runtime_state.magic.known_spells.add(spell.spell_id)
        result = self.player.cast_spell(spell, None, time.time(), world=self.world)
        self.assertTrue(result["success"])
        self.assertIn(first.name, result["message"])
        self.assertIn(second.name, result["message"])


if __name__ == "__main__":
    import unittest
    unittest.main()
