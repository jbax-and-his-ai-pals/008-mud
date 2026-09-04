# tests/singles/test_movement_commands_full.py
"""Coverage for engine/commands/movement.py: register_movement_commands'
already-registered skip branch, the dynamically-generated direction
handlers' trading-cleanup/dead-player guards, and the entirely-untested
'go' command handler."""

from tests.fixtures import GameTestBase
from engine.commands.movement import register_movement_commands, go_handler
from engine.commands.command_system import registered_commands
from engine.npcs.npc_factory import NPCFactory


class TestRegisterMovementCommands(GameTestBase):
    def test_reregistering_skips_already_registered_directions(self):
        # Movement commands are registered once at import time; calling the
        # registration function again must not raise and must skip every
        # direction since they're all already present.
        before = dict(registered_commands)
        register_movement_commands()
        self.assertEqual(before.keys(), registered_commands.keys())


class TestDirectionHandlerGuards(GameTestBase):
    def _handler(self, name="north"):
        return registered_commands[name]["handler"]

    def test_no_player_reports_error(self):
        handler = self._handler()
        result = handler([], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)

    def test_dead_player_cannot_move(self):
        handler = self._handler()
        self.player.is_alive = False
        result = handler([], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_trading_with_vendor_clears_trade_state(self):
        vendor = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="move_vendor")
        self.world.add_npc(vendor)
        vendor.is_trading = True
        self.player.trading_with = vendor.obj_id
        handler = self._handler()
        handler([], {"world": self.world, "player": self.player})
        self.assertFalse(vendor.is_trading)
        self.assertIsNone(self.player.trading_with)

    def test_trading_with_vanished_vendor_still_clears_player_state(self):
        self.player.trading_with = "a_vendor_that_no_longer_exists"
        handler = self._handler()
        handler([], {"world": self.world, "player": self.player})  # must not raise
        self.assertIsNone(self.player.trading_with)

    def test_successful_move_delegates_to_change_room(self):
        result = self.game.process_command("north")
        self.assertIsNotNone(result)


class TestGoHandler(GameTestBase):
    def test_no_player_reports_error(self):
        result = go_handler(["north"], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)

    def test_dead_player_cannot_move(self):
        self.player.is_alive = False
        result = go_handler(["north"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_prompts_for_direction(self):
        result = go_handler([], {"world": self.world, "player": self.player})
        self.assertEqual("Go where?", result)

    def test_trading_with_vendor_clears_trade_state(self):
        vendor = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="go_vendor")
        self.world.add_npc(vendor)
        vendor.is_trading = True
        self.player.trading_with = vendor.obj_id
        go_handler(["north"], {"world": self.world, "player": self.player})
        self.assertFalse(vendor.is_trading)
        self.assertIsNone(self.player.trading_with)

    def test_successful_go_delegates_to_change_room(self):
        result = self.game.process_command("go north")
        self.assertIsNotNone(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
