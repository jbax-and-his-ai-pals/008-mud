# tests/singles/test_player_combat.py
"""Coverage for engine/player/combat.py's PlayerCombatMixin: enter/exit_combat
guard clauses and minion notification, _add_combat_message trimming, attack()'s
full branch matrix (stun, dead target, weapon durability/breaking, loot/gold/
xp/level-up/quest-message assembly, party-reward routing), and the entirely
untested die()/respawn() lifecycle (including permadeath).

Note: exit_combat()'s summon-notification `elif not
p.runtime_state.combat.in_combat:` False arm is left untested as
unreachable -- when `target` is falsy, exit_combat() always clears every
entry from combat.targets before this loop runs, and the very next check
(`if not p.runtime_state.combat.targets:`) then always sets in_combat to
False, so this elif is guaranteed True whenever it's reached with a falsy
target."""

from unittest.mock import patch, MagicMock

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.weapon import Weapon


def _target_goblin(world, instance_id="combat_target_goblin"):
    npc = NPCFactory.create_npc_from_template("goblin", world, instance_id=instance_id)
    world.add_npc(npc)
    npc.current_region_id = world.player.current_region_id
    npc.current_room_id = world.player.current_room_id
    npc.is_alive = True
    npc.health = 10
    return npc


class TestEnterCombat(GameTestBase):
    def test_combat_disabled_is_a_no_op(self):
        original = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            self.player.enter_combat(_target_goblin(self.world))  # must not raise
        finally:
            self.player.runtime_state.combat = original

    def test_dead_player_cannot_enter_combat(self):
        self.player.is_alive = False
        target = _target_goblin(self.world)
        self.player.enter_combat(target)
        self.assertFalse(self.player.runtime_state.combat.in_combat)

    def test_dead_target_is_ignored(self):
        target = _target_goblin(self.world)
        target.is_alive = False
        self.player.enter_combat(target)
        self.assertNotIn(target, self.player.runtime_state.combat.targets)

    def test_none_target_is_ignored(self):
        self.player.enter_combat(None)  # must not raise
        self.assertFalse(self.player.runtime_state.combat.in_combat)

    def test_self_target_is_ignored(self):
        self.player.enter_combat(self.player)
        self.assertNotIn(self.player, self.player.runtime_state.combat.targets)

    def test_notifies_living_summons(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "combat_summon")
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        target = _target_goblin(self.world, "combat_target_for_summon")
        self.player.enter_combat(target)
        self.assertIn(target, summon.combat_targets)

    def test_skips_dead_summons(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "combat_dead_summon")
        summon.is_alive = False
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        target = _target_goblin(self.world, "combat_target_for_dead_summon")
        self.player.enter_combat(target)  # must not raise
        self.assertNotIn(target, summon.combat_targets)


class TestExitCombat(GameTestBase):
    def test_combat_disabled_is_a_no_op(self):
        original = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            self.player.exit_combat()  # must not raise
        finally:
            self.player.runtime_state.combat = original

    def test_target_not_currently_engaged_is_a_no_op(self):
        target = _target_goblin(self.world, "not_engaged_goblin")
        self.player.exit_combat(target)  # must not raise; target was never added
        self.assertFalse(self.player.runtime_state.combat.in_combat)

    def test_explicit_target_is_removed_and_notified(self):
        target = _target_goblin(self.world, "explicit_exit_goblin")
        self.player.enter_combat(target)
        self.player.exit_combat(target)
        self.assertNotIn(target, self.player.runtime_state.combat.targets)
        self.assertNotIn(self.player, target.combat_targets)

    def test_clear_all_skips_targets_without_exit_combat_method(self):
        class _NoExitCombatTarget:
            is_alive = True
        stub = _NoExitCombatTarget()
        self.player.runtime_state.combat.targets.add(stub)
        self.player.runtime_state.combat.in_combat = True
        self.player.exit_combat()  # must not raise despite stub lacking exit_combat
        self.assertNotIn(stub, self.player.runtime_state.combat.targets)

    def test_no_target_clears_all_and_resets_in_combat(self):
        t1 = _target_goblin(self.world, "clear_all_1")
        t2 = _target_goblin(self.world, "clear_all_2")
        self.player.enter_combat(t1)
        self.player.enter_combat(t2)
        self.player.exit_combat()
        self.assertEqual(set(), self.player.runtime_state.combat.targets)
        self.assertFalse(self.player.runtime_state.combat.in_combat)

    def test_notifies_summons_with_explicit_target(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "exit_summon")
        target = _target_goblin(self.world, "exit_target_for_summon")
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        self.player.enter_combat(target)
        summon.enter_combat(target)
        self.player.exit_combat(target)
        self.assertNotIn(target, summon.combat_targets)

    def test_notifies_summons_when_fully_out_of_combat(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "exit_summon2")
        target = _target_goblin(self.world, "exit_target_for_summon2")
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        self.player.enter_combat(target)
        summon.enter_combat(target)
        self.player.exit_combat()  # clears all -> in_combat False -> summon.exit_combat()
        self.assertEqual(set(), summon.combat_targets)

    def test_skips_dead_summons(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "exit_dead_summon")
        summon.is_alive = False
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        target = _target_goblin(self.world, "exit_target_for_dead_summon")
        self.player.enter_combat(target)
        self.player.exit_combat(target)  # must not raise


class TestAddCombatMessage(GameTestBase):
    def test_trims_to_max_combat_messages(self):
        self.player.combat_messages = []
        self.player.max_combat_messages = 3
        for i in range(5):
            self.player._add_combat_message(f"line {i}")
        self.assertEqual(3, len(self.player.combat_messages))
        self.assertEqual(["line 2", "line 3", "line 4"], self.player.combat_messages)


class TestAttackGuards(GameTestBase):
    def test_combat_disabled_returns_message(self):
        original = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            result = self.player.attack(_target_goblin(self.world))
        finally:
            self.player.runtime_state.combat = original
        self.assertIn("Combat is not enabled", result["message"])

    def test_dead_player_cannot_attack(self):
        self.player.is_alive = False
        result = self.player.attack(_target_goblin(self.world))
        self.assertIn("cannot attack while dead", result["message"])

    def test_stunned_player_cannot_attack(self):
        target = _target_goblin(self.world)
        with patch.object(self.player, "has_effect", return_value=True):
            result = self.player.attack(target)
        self.assertIn("stunned", result["message"])

    def test_dead_target_exits_combat_and_reports(self):
        target = _target_goblin(self.world)
        target.is_alive = False
        result = self.player.attack(target)
        self.assertIn("already dead", result["message"])

    def test_none_target_reports_already_dead(self):
        result = self.player.attack(None)
        self.assertIn("already dead", result["message"])


class TestAttackWeaponDurability(GameTestBase):
    def test_weapon_breaks_when_durability_reaches_zero(self):
        from engine.config import ITEM_DURABILITY_LOSS_ON_HIT
        target = _target_goblin(self.world)
        weapon = Weapon(obj_id="test_breaking_sword", name="Rusty Sword", description="Almost broken.")
        weapon.update_property("durability", ITEM_DURABILITY_LOSS_ON_HIT)
        self.player.equipment["main_hand"] = weapon
        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Hit!", "is_hit": True, "target_defeated": False},
        ):
            result = self.player.attack(target)
        self.assertIn("breaks", result["message"])

    def test_weapon_with_zero_durability_does_not_lose_more(self):
        target = _target_goblin(self.world)
        weapon = Weapon(obj_id="test_broken_sword", name="Broken Sword", description="Already broken.")
        weapon.update_property("durability", 0)
        self.player.equipment["main_hand"] = weapon
        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Hit!", "is_hit": True, "target_defeated": False},
        ):
            result = self.player.attack(target)
        self.assertNotIn("breaks", result["message"])
        self.assertEqual(0, weapon.get_property("durability"))


class TestAttackKillRewards(GameTestBase):
    def _kill(self, target, world=None):
        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Fatal blow!", "is_hit": True, "target_defeated": True},
        ):
            return self.player.attack(target, world)

    def test_kill_without_world_arg_uses_player_world_and_no_quest_message(self):
        target = _target_goblin(self.world)
        target.health = 0
        result = self._kill(target, world=None)
        self.assertIn("Fatal blow!", result["message"])

    def test_kill_target_without_loot_table_skips_gold_roll(self):
        class _NoLootTableTarget:
            is_alive = True
            faction = "hostile"
            template_id = "no_loot_table"
            level = 1
            max_health = 10
        stub = _NoLootTableTarget()
        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Fatal blow!", "is_hit": True, "target_defeated": True},
        ):
            result = self.player.attack(stub, self.world)
        self.assertIsNotNone(result["message"])

    def test_kill_with_non_dict_gold_value_skips_gold_roll(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": "not_a_dict"}
        result = self._kill(target, self.world)
        self.assertIsNotNone(result["message"])

    @patch("engine.player.combat.random.random", return_value=0.99)
    def test_kill_with_missed_gold_chance_grants_no_gold(self, _mock_random):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.1, "quantity": [5, 5]}}
        before_gold = self.player.runtime_state.gold
        result = self._kill(target, self.world)
        self.assertEqual(before_gold, self.player.runtime_state.gold)

    def test_kill_with_player_gold_none_grants_nothing(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}
        self.player.runtime_state.gold = None
        with patch("engine.player.combat.random.random", return_value=0.0):
            result = self._kill(target, self.world)
        self.assertNotIn("gold", result["message"].lower())

    @patch("engine.player.combat.calculate_xp_gain", return_value=0)
    @patch("engine.player.combat.random.random", return_value=0.99)
    def test_kill_with_zero_xp_and_zero_gold_grants_nothing_extra(self, _mock_random, _mock_xp):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        result = self._kill(target, self.world)
        self.assertNotIn("gold", result["message"].lower())
        self.assertNotIn("experience", result["message"].lower())

    @patch("engine.player.combat.calculate_xp_gain", return_value=100000)
    @patch("engine.player.combat.random.random", return_value=0.99)
    def test_kill_with_level_up_appends_level_up_message(self, _mock_random, _mock_xp):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        result = self._kill(target, self.world)
        self.assertIn("experience", result["message"].lower())

    def test_kill_target_without_die_method_skips_loot(self):
        # Use a plain object without a die() method entirely.
        class _NoDieTarget:
            is_alive = True
            faction = "hostile"
            template_id = "no_die"
            level = 1
            max_health = 10
        stub = _NoDieTarget()
        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Fatal blow!", "is_hit": True, "target_defeated": True},
        ):
            result = self.player.attack(stub, self.world)
        self.assertIsNotNone(result["message"])

    def test_kill_uses_party_reward_routing_when_active(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        fake_server = MagicMock()
        fake_server.party_reward_routing_active.return_value = True
        fake_server.grant_party_rewards.return_value = "Party gets rewards!"
        self.world.server = fake_server
        try:
            with patch("engine.player.combat.calculate_xp_gain", return_value=10):
                result = self._kill(target, self.world)
        finally:
            del self.world.server
        self.assertIn("Party gets rewards!", result["message"])

    def test_kill_party_routing_with_empty_reward_text_appends_nothing_extra(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        fake_server = MagicMock()
        fake_server.party_reward_routing_active.return_value = True
        fake_server.grant_party_rewards.return_value = ""
        self.world.server = fake_server
        try:
            with patch("engine.player.combat.calculate_xp_gain", return_value=10):
                result = self._kill(target, self.world)
        finally:
            del self.world.server
        self.assertIn("Fatal blow!", result["message"])

    def test_kill_uses_party_reward_routing_but_skips_when_no_rewards(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        fake_server = MagicMock()
        fake_server.party_reward_routing_active.return_value = True
        self.world.server = fake_server
        try:
            with patch("engine.player.combat.calculate_xp_gain", return_value=0):
                result = self._kill(target, self.world)
        finally:
            del self.world.server
        fake_server.grant_party_rewards.assert_not_called()

    def test_quest_update_message_is_appended(self):
        target = _target_goblin(self.world)
        target.loot_table = {"gold_value": {"chance": 0.0, "quantity": [1, 1]}}
        with patch.object(self.world, "dispatch_event", return_value="[Quest Update] Something happened."):
            result = self._kill(target, self.world)
        self.assertIn("Something happened", result["message"])


class TestDie(GameTestBase):
    def test_already_dead_is_a_no_op(self):
        self.player.is_alive = False
        self.player.health = 0
        self.player.die()  # must not raise
        self.assertEqual(0, self.player.health)

    def test_sets_health_zero_and_not_alive(self):
        self.player.die()
        self.assertEqual(0, self.player.health)
        self.assertFalse(self.player.is_alive)

    def test_combat_disabled_still_completes_death(self):
        original = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            self.player.die()  # must not raise
        finally:
            self.player.runtime_state.combat = original
        self.assertFalse(self.player.is_alive)

    def test_world_without_npcs_attribute_is_a_no_op_for_disengage(self):
        class _BareWorld:
            pass
        original_world = self.player.world
        self.player.world = _BareWorld()
        try:
            self.player.die()  # must not raise
        finally:
            self.player.world = original_world
        self.assertFalse(self.player.is_alive)

    def test_permadeath_with_no_progression_skips_level_reset(self):
        original_progression = self.player.runtime_state.progression
        self.player.runtime_state.progression = None
        fake_feature_profile = MagicMock()
        fake_feature_profile.permadeath_enabled.return_value = True
        fake_game = MagicMock()
        fake_game.feature_profile = fake_feature_profile
        original_game = self.world.game
        self.world.game = fake_game
        try:
            self.player.die()  # must not raise
        finally:
            self.world.game = original_game
            self.player.runtime_state.progression = original_progression
        self.assertEqual([], self.player.inventory.slots)

    def test_permadeath_with_no_gold_skips_gold_reset(self):
        original_gold = self.player.runtime_state.gold
        self.player.runtime_state.gold = None
        fake_feature_profile = MagicMock()
        fake_feature_profile.permadeath_enabled.return_value = True
        fake_game = MagicMock()
        fake_game.feature_profile = fake_feature_profile
        original_game = self.world.game
        self.world.game = fake_game
        try:
            self.player.die()  # must not raise
        finally:
            self.world.game = original_game
            self.player.runtime_state.gold = original_gold
        self.assertEqual([], self.player.inventory.slots)

    def test_disengages_npcs_targeting_the_player(self):
        npc = _target_goblin(self.world)
        npc.enter_combat(self.player)
        self.player.enter_combat(npc)
        self.player.die()
        self.assertNotIn(self.player, npc.combat_targets)

    def test_clears_active_effects_and_combat_targets(self):
        target = _target_goblin(self.world)
        self.player.enter_combat(target)
        self.player.active_effects.append({"name": "Poison"})
        self.player.die()
        self.assertEqual([], self.player.active_effects)
        self.assertEqual(set(), self.player.runtime_state.combat.targets)

    def test_despawns_summons_on_death(self):
        assert self.player.runtime_state.magic is not None
        summon = _target_goblin(self.world, "die_summon")
        self.player.runtime_state.magic.summons["fire_elemental"] = [summon.obj_id]
        with patch.object(summon, "despawn") as mock_despawn:
            self.player.die()
        mock_despawn.assert_called_once()
        self.assertEqual({}, self.player.runtime_state.magic.summons)

    def test_permadeath_wipes_inventory_and_progression(self):
        from engine.items.item_factory import ItemFactory
        item = ItemFactory.create_item_from_template("item_starter_dagger", self.world)
        if item:
            self.player.inventory.add_item(item)
        self.player.runtime_state.progression.level = 5
        self.player.runtime_state.progression.experience = 500
        self.player.runtime_state.gold = 100

        fake_feature_profile = MagicMock()
        fake_feature_profile.permadeath_enabled.return_value = True
        fake_game = MagicMock()
        fake_game.feature_profile = fake_feature_profile
        original_game = self.world.game
        self.world.game = fake_game
        try:
            self.player.die()
        finally:
            self.world.game = original_game

        self.assertEqual([], self.player.inventory.slots)
        self.assertTrue(all(v is None for v in self.player.equipment.values()))
        self.assertEqual(1, self.player.runtime_state.progression.level)
        self.assertEqual(0, self.player.runtime_state.progression.experience)
        self.assertEqual(0, self.player.runtime_state.gold)

    def test_no_permadeath_when_disabled(self):
        self.player.runtime_state.gold = 100
        fake_feature_profile = MagicMock()
        fake_feature_profile.permadeath_enabled.return_value = False
        fake_game = MagicMock()
        fake_game.feature_profile = fake_feature_profile
        original_game = self.world.game
        self.world.game = fake_game
        try:
            self.player.die()
        finally:
            self.world.game = original_game
        self.assertEqual(100, self.player.runtime_state.gold)

    def test_no_game_attribute_skips_permadeath_check(self):
        original_game = self.world.game
        self.world.game = None
        try:
            self.player.die()  # must not raise
        finally:
            self.world.game = original_game


class TestRespawn(GameTestBase):
    def test_restores_health_and_alive_state(self):
        self.player.health = 0
        self.player.is_alive = False
        self.player.respawn()
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertTrue(self.player.is_alive)

    def test_restores_mana_and_clears_cooldowns_and_summons(self):
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 0
        self.player.runtime_state.magic.cooldowns["fireball"] = 5.0
        self.player.runtime_state.magic.summons["fire_elemental"] = ["ghost_id"]
        self.player.respawn()
        self.assertEqual(self.player.runtime_state.magic.max_mana, self.player.runtime_state.magic.mana)
        self.assertEqual({}, self.player.runtime_state.magic.cooldowns)
        self.assertEqual({}, self.player.runtime_state.magic.summons)

    def test_resets_combat_state(self):
        target = _target_goblin(self.world)
        self.player.enter_combat(target)
        self.player.respawn()
        self.assertFalse(self.player.runtime_state.combat.in_combat)
        self.assertEqual(set(), self.player.runtime_state.combat.targets)

    def test_combat_disabled_still_respawns(self):
        self.player.health = 0
        self.player.is_alive = False
        original = self.player.runtime_state.combat
        self.player.runtime_state.combat = None
        try:
            self.player.respawn()  # must not raise
        finally:
            self.player.runtime_state.combat = original
        self.assertTrue(self.player.is_alive)

    def test_moves_player_to_respawn_location(self):
        self.player.respawn_region_id = "town"
        self.player.respawn_room_id = "town_square"
        self.player.current_region_id = "somewhere_else"
        self.player.current_room_id = "somewhere_else_room"
        self.player.respawn()
        self.assertEqual("town", self.player.current_region_id)
        self.assertEqual("town_square", self.player.current_room_id)


if __name__ == "__main__":
    import unittest
    unittest.main()
