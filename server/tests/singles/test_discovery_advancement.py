"""A discovery pays the ruleset's discovery grant.

`DiscoveryManager.handle_item_discovery` (and the dialogue `discover` effect)
wrote `player.discoveries` but never recorded the advancement ledger's
`discovery` kind, so a ruleset grant matching it (fantasy_frontier's
`discovery_made`, 15 XP) could never pay; loading a save only folded past
discoveries into the ledger, paying nothing.
"""
import unittest

from engine.core import advancement
from engine.items.item_factory import ItemFactory
from tests.fixtures import make_test_server


class TestDiscoveryAdvancement(unittest.TestCase):
    def setUp(self):
        self.server = make_test_server()
        self.session = self.server.create_session(player_id="discovery")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)
        self.room = self.server.world.get_region(self.player.current_region_id).get_room(self.player.current_room_id)

    def tearDown(self):
        self.server.shutdown()

    def _xp(self) -> int:
        progression = self.player.runtime_state.progression
        return int(self.server.world.advancement_manager.xp_to_reach_level(progression.level)) + int(progression.experience)

    def test_picking_up_a_discovery_pays_the_discovery_grant_once_per_discovery(self):
        self.room.add_item(ItemFactory.create_item_from_template("item_rose_quartz", self.server.world))
        before = self._xp()
        self.server.execute_command(self.session.session_id, "get rose quartz")
        # Two discoveries (fieldcraft_basics, rose_quartz) at 15 each, plus the
        # gem grant (15).
        self.assertEqual({"fieldcraft_basics", "rose_quartz"}, set(self.player.discoveries))
        self.assertEqual(45, self._xp() - before)
        ledger = self.server.world.advancement_manager.ledger(self.player)
        self.assertIn(advancement.entry_key(advancement.KIND_DISCOVERY, "rose_quartz"), ledger)

        self.room.add_item(ItemFactory.create_item_from_template("item_rose_quartz", self.server.world))
        again = self._xp()
        self.server.execute_command(self.session.session_id, "get rose quartz")
        self.assertEqual(0, self._xp() - again, "a second stone discovers nothing new and pays nothing")

    def test_a_discovery_made_in_conversation_pays_too(self):
        from engine.dialogue.effects import _record_discovery

        before = self._xp()
        self.assertTrue(_record_discovery(self.player, "sunken_lake"))
        self.assertEqual(15, self._xp() - before)


if __name__ == "__main__":
    unittest.main()
