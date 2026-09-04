# tests/singles/test_combat_commands_full.py
"""Coverage for engine/commands/combat.py: attack's guard clauses,
trading-cleanup, already-defeated-target feedback (both the live-NPC-found
and the dead-body-search paths), no-target-here error, attack-cooldown
messaging, and combat_status's no-player guard."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.commands.combat import attack_handler, combat_status_handler


def _room_npc(world, player, instance_id="combat_cmd_npc", template="goblin"):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id)
    npc.current_region_id = player.current_region_id
    npc.current_room_id = player.current_room_id
    world.add_npc(npc)
    return npc


class TestAttackHandlerGuards(GameTestBase):
    def test_no_player_reports_error(self):
        result = attack_handler(["goblin"], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)

    def test_dead_player_cannot_attack(self):
        self.player.is_alive = False
        result = attack_handler(["goblin"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_prompts(self):
        result = attack_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Attack whom?", result)


class TestAttackHandlerTradingCleanup(GameTestBase):
    def test_attacking_while_trading_clears_trade_state(self):
        vendor = _room_npc(self.world, self.player, "attack_vendor", "village_elder")
        vendor.is_trading = True
        self.player.trading_with = vendor.obj_id
        attack_handler(["nothing_here"], {"world": self.world, "player": self.player})
        self.assertFalse(vendor.is_trading)
        self.assertIsNone(self.player.trading_with)

    def test_attacking_while_trading_with_vanished_vendor(self):
        self.player.trading_with = "a_vendor_that_no_longer_exists"
        attack_handler(["nothing_here"], {"world": self.world, "player": self.player})  # must not raise
        self.assertIsNone(self.player.trading_with)


class TestAttackHandlerTargeting(GameTestBase):
    def test_no_target_here_reports_error(self):
        result = attack_handler(["nonexistent_creature_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("No 'nonexistent_creature_xyz' here to attack", result)

    def test_live_npc_found_but_already_dead_reports_defeated(self):
        npc = _room_npc(self.world, self.player)
        npc.is_alive = False
        with patch.object(self.world, "find_npc_in_room_for_player", return_value=npc):
            result = attack_handler([npc.name], {"world": self.world, "player": self.player})
        self.assertIn("already defeated", result)

    def test_dead_body_search_finds_defeated_npc_by_name(self):
        # find_npc_in_room_for_player itself excludes dead NPCs, so the
        # handler falls back to scanning all room NPCs (dead included) for
        # a better error message.
        npc = _room_npc(self.world, self.player, "dead_body_npc")
        npc.is_alive = False
        result = attack_handler([npc.name], {"world": self.world, "player": self.player})
        self.assertIn(f"{npc.name} is already defeated", result)

    def test_dead_body_search_skips_matching_but_still_alive_npc(self):
        # find_npc_in_room_for_player is forced to miss, so the dead-body
        # fallback scans the room itself -- it finds an ALIVE npc whose name
        # matches, must skip it (not report "defeated"), and fall through
        # to the generic not-here error.
        npc = _room_npc(self.world, self.player, "still_alive_match_npc")
        with patch.object(self.world, "find_npc_in_room_for_player", return_value=None):
            result = attack_handler([npc.name], {"world": self.world, "player": self.player})
        self.assertIn("No", result)
        self.assertIn("here to attack", result)

    def test_dead_body_search_skips_when_player_has_no_location(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = attack_handler(["anything"], {"world": self.world, "player": self.player})
        self.assertIn("No 'anything' here to attack", result)


class TestAttackHandlerCooldownAndSuccess(GameTestBase):
    def test_attack_on_cooldown_reports_wait_time(self):
        npc = _room_npc(self.world, self.player)
        with patch.object(self.player, "can_attack", return_value=False), \
             patch.object(self.player, "get_effective_attack_cooldown", return_value=5.0):
            self.player.last_attack_time = __import__("time").time()
            result = attack_handler([npc.name], {"world": self.world, "player": self.player})
        self.assertIn("Not ready", result)

    def test_successful_attack_returns_combat_message(self):
        npc = _room_npc(self.world, self.player)
        fake_result = {"message": "You hit the goblin!"}
        with patch.object(self.player, "attack", return_value=fake_result) as mock_attack:
            result = attack_handler([npc.name], {"world": self.world, "player": self.player})
        mock_attack.assert_called_once_with(npc, self.world)
        self.assertEqual("You hit the goblin!", result)


class TestCombatStatusHandler(GameTestBase):
    def test_no_player_reports_error(self):
        result = combat_status_handler([], {"player": None})
        self.assertIn("must start or load a game", result)

    def test_delegates_to_player_get_combat_status(self):
        with patch.object(self.player, "get_combat_status", return_value="Not in combat.") as mock_status:
            result = combat_status_handler([], {"player": self.player})
        mock_status.assert_called_once()
        self.assertEqual("Not in combat.", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
