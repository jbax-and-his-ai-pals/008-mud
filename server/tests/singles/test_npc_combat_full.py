# tests/singles/test_npc_combat_full.py
"""Coverage for engine/npcs/combat.py: get_relation_to's missing-faction
guard, enter_combat's dead/falsy-target guard, exit_combat's specific-
target and clear-all branches' hasattr-false skips, attack()'s no-world
and non-player-target-shape skips plus the special-ability roll-fails
fallthrough, cast_spell's friendly/enemy target-type redirects to attack()
and the low-mana short-circuit, and try_attack's cooldown gate, cached-
target-still-valid skip, failed-retreat fallthrough, attack-on-cooldown
no-op, zero-xp skip, and no-die-method skip.

Note: try_attack's `if xp_gainer:` check is unreachable in its False arm --
xp_gainer is `owner if owner is not None else npc`, and npc is always a
real (truthy) object with no __bool__/__len__ override, so xp_gainer can
never be falsy. Left untested as dead code, consistent with this
codebase's established precedent."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.combat import get_relation_to, enter_combat, exit_combat, attack, cast_spell, try_attack
from engine.magic.spell import Spell


def _npc(world, template, instance_id, **overrides):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id, **overrides)
    world.add_npc(npc)
    return npc


class TestGetRelationTo(unittest.TestCase):
    def test_missing_faction_attribute_returns_zero(self):
        class _NoFaction:
            pass
        self.assertEqual(get_relation_to(_NoFaction(), _NoFaction()), 0)


class TestEnterCombat(GameTestBase):
    def test_dead_npc_does_not_enter_combat(self):
        npc = _npc(self.world, "goblin", "combat_dead_npc")
        npc.is_alive = False
        target = _npc(self.world, "goblin", "combat_dead_npc_target")
        enter_combat(npc, target)
        self.assertFalse(npc.in_combat)

    def test_falsy_target_is_a_noop(self):
        npc = _npc(self.world, "goblin", "combat_falsy_target_npc")
        enter_combat(npc, None)
        self.assertFalse(npc.in_combat)


class TestExitCombat(GameTestBase):
    def test_specific_target_without_exit_combat_method_is_skipped(self):
        npc = _npc(self.world, "goblin", "combat_exit_specific")
        class _StubTarget:
            pass
        stub = _StubTarget()
        npc.combat_targets.add(stub)
        npc.in_combat = True
        exit_combat(npc, stub)
        self.assertNotIn(stub, npc.combat_targets)

    def test_clear_all_skips_targets_without_exit_combat_method(self):
        npc = _npc(self.world, "goblin", "combat_exit_all")
        class _StubTarget:
            pass
        stub_a = _StubTarget()
        stub_b = _StubTarget()
        npc.combat_targets.update([stub_a, stub_b])
        npc.in_combat = True
        exit_combat(npc)
        self.assertEqual(npc.combat_targets, set())
        self.assertFalse(npc.in_combat)


class TestAttack(GameTestBase):
    def test_no_world_skips_viewer_resolution(self):
        npc = _npc(self.world, "goblin", "combat_attack_no_world")
        target = _npc(self.world, "goblin", "combat_attack_no_world_target")
        npc.world = None
        with patch("engine.npcs.combat.CombatSystem.execute_attack", return_value={"message": "hit", "target_defeated": False}) as mock_exec:
            attack(npc, target)
        self.assertIsNone(mock_exec.call_args.kwargs["viewer"])

    def test_target_missing_room_shape_skips_direct_viewer_assignment(self):
        npc = _npc(self.world, "goblin", "combat_attack_shape")
        class _MinimalTarget:
            is_alive = True
        with patch("engine.npcs.combat.CombatSystem.execute_attack", return_value={"message": "hit", "target_defeated": False}):
            attack(npc, _MinimalTarget())  # must not raise

    def test_special_ability_roll_failure_falls_through_to_normal_attack(self):
        npc = _npc(self.world, "goblin", "combat_special_fail")
        npc.properties["special_abilities"] = [{"name": "Smash", "damage_multiplier": 2.0}]
        target = _npc(self.world, "goblin", "combat_special_fail_target")
        with patch("engine.npcs.combat.random.random", return_value=0.9):
            with patch("engine.npcs.combat.CombatSystem.execute_attack", return_value={"message": "normal hit", "target_defeated": False}) as mock_exec:
                result = attack(npc, target)
        self.assertEqual(mock_exec.call_args.kwargs["weapon_name"], "attack")
        self.assertEqual(result["message"], "normal hit")


class TestCastSpell(GameTestBase):
    def _spell(self, target_type, mana_cost=5):
        return Spell(spell_id="test_npc_spell", name="Test Spell", description="x",
                     effects=[{"type": "damage", "value": 5}], target_type=target_type, mana_cost=mana_cost)

    def test_friendly_spell_against_hostile_target_redirects_to_attack(self):
        npc = _npc(self.world, "goblin", "combat_cast_friendly_redirect")
        target = _npc(self.world, "goblin", "combat_cast_friendly_target")
        npc.combat_targets.add(target)
        with patch("engine.npcs.combat.attack", return_value={"message": "attacked instead"}) as mock_attack:
            result = cast_spell(npc, self._spell("friendly"), target, time.time())
        mock_attack.assert_called_once_with(npc, target)

    def test_enemy_spell_against_non_hostile_target_redirects_to_attack(self):
        # Same faction as the caster (goblin), so is_hostile_to() is False
        # and the target isn't in npc.combat_targets either.
        npc = _npc(self.world, "goblin", "combat_cast_enemy_redirect")
        target = _npc(self.world, "goblin", "combat_cast_enemy_target")
        with patch("engine.npcs.combat.attack", return_value={"message": "attacked instead"}) as mock_attack:
            result = cast_spell(npc, self._spell("enemy"), target, time.time())
        mock_attack.assert_called_once_with(npc, target)

    def test_insufficient_mana_reports_lacking_mana(self):
        npc = _npc(self.world, "goblin", "combat_cast_low_mana")
        target = _npc(self.world, "goblin", "combat_cast_low_mana_target")
        npc.combat_targets.add(target)
        npc.mana = 0
        result = cast_spell(npc, self._spell("enemy", mana_cost=999), target, time.time())
        self.assertIn("lacks mana", result["message"])

    def test_no_world_skips_viewer_lookup(self):
        npc = _npc(self.world, "goblin", "combat_cast_no_world")
        target = _npc(self.world, "goblin", "combat_cast_no_world_target")
        npc.combat_targets.add(target)
        npc.mana = 100
        npc.world = None
        result = cast_spell(npc, self._spell("enemy"), target, time.time())
        self.assertIn("message", result)


class TestTryAttack(GameTestBase):
    def _combatant(self, instance_id="combat_try_attack_npc"):
        npc = _npc(self.world, "goblin", instance_id)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        return npc

    def test_cooldown_not_elapsed_returns_none(self):
        npc = self._combatant()
        target = self._combatant("combat_try_attack_target")
        npc.combat_targets.add(target)
        npc.combat_target = target
        npc.last_combat_action = time.time()
        npc.combat_cooldown = 1000
        self.assertIsNone(try_attack(npc, self.world, time.time()))

    def test_cached_target_still_valid_is_reused(self):
        npc = self._combatant()
        target = self._combatant("combat_try_attack_cached_target")
        npc.combat_targets.add(target)
        npc.combat_target = target
        npc.last_combat_action = 0
        npc.last_attack_time = 0
        with patch("engine.npcs.combat.attack", return_value={"message": "hit", "target_defeated": False}) as mock_attack:
            try_attack(npc, self.world, time.time())
        mock_attack.assert_called_once_with(npc, target)

    def test_failed_retreat_falls_through_to_spell_or_attack(self):
        npc = self._combatant()
        target = self._combatant("combat_try_attack_retreat_fail_target")
        npc.combat_targets.add(target)
        npc.combat_target = target
        npc.last_combat_action = 0
        npc.last_attack_time = 0
        npc.max_mana = 100
        npc.mana = 1  # below the low-mana retreat threshold
        npc.usable_spells = ["magic_missile"]
        npc.spell_cast_chance = 1.0
        with patch("engine.npcs.ai.start_retreat", return_value=None):
            with patch("engine.npcs.combat.attack", return_value={"message": "hit", "target_defeated": False}) as mock_attack:
                try_attack(npc, self.world, time.time())
        mock_attack.assert_called_once()

    def test_attack_on_cooldown_with_no_spell_takes_no_action(self):
        npc = self._combatant()
        target = self._combatant("combat_try_attack_on_cooldown_target")
        npc.combat_targets.add(target)
        npc.combat_target = target
        npc.last_combat_action = 0
        npc.last_attack_time = time.time()
        npc.attack_cooldown = 1000
        npc.usable_spells = []
        result = try_attack(npc, self.world, time.time())
        self.assertIsNone(result)

    def test_zero_xp_gain_skips_experience_call(self):
        npc = self._combatant()
        target = self._combatant("combat_try_attack_zero_xp_target")
        npc.combat_targets.add(target)
        npc.combat_target = target
        npc.last_combat_action = 0
        npc.last_attack_time = 0
        with patch("engine.npcs.combat.attack", return_value={"message": "killed", "target_defeated": True}):
            with patch("engine.npcs.combat.calculate_xp_gain", return_value=0):
                with patch.object(target, "die", return_value=[]):
                    try_attack(npc, self.world, time.time())
        # No exception, and target should have exited combat.
        self.assertNotIn(target, npc.combat_targets)

    def test_target_without_die_method_skips_loot_handling(self):
        # NPC always defines die(), so a bare stand-in object is used here
        # to exercise the "target has no die()" branch.
        npc = self._combatant()

        class _NoDieTarget:
            is_alive = True
            level = 1
            max_health = 10
            current_room_id = npc.current_room_id

        stub = _NoDieTarget()
        npc.combat_targets.add(stub)
        npc.combat_target = stub
        npc.last_combat_action = 0
        npc.last_attack_time = 0
        with patch("engine.npcs.combat.attack", return_value={"message": "killed", "target_defeated": True}):
            with patch("engine.npcs.combat.calculate_xp_gain", return_value=0):
                try_attack(npc, self.world, time.time())  # must not raise


if __name__ == "__main__":
    unittest.main()
