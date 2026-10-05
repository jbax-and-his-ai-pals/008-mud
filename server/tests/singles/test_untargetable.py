# tests/singles/test_untargetable.py
"""A passenger: `properties.untargetable` on an NPC.

A child carried through a fight (with `pacifist`, she takes no part in it) is picked by no enemy and hurt by nothing: a
hostile in the room goes for the player and not for her, and damage that reaches her anyway does nothing. Without the
property a companion in the same room is a target like anyone, as it always was.
"""

import unittest

from engine.npcs import companions
from engine.npcs.ai import combat_logic
from engine.npcs.combat import is_untargetable
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE


class TestAPassengerIsNotAtarget(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "hazevale", "village_square"

    def passenger(self, untargetable):
        ryn = NPCFactory.create_npc_from_template("ryn", self.world, instance_id="passenger_%s" % untargetable)
        ryn.current_region_id, ryn.current_room_id = "hazevale", "village_square"
        ryn.properties["pacifist"] = True
        if untargetable:
            ryn.properties["untargetable"] = True
        self.world.add_npc(ryn)
        companions.recruit(self.world, self.player, ryn)
        return ryn

    def hostile(self):
        wolf = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id="goblin_probe")
        wolf.current_region_id, wolf.current_room_id = "hazevale", "village_square"
        self.world.add_npc(wolf)
        return wolf

    def test_no_hostile_picks_her_as_a_target(self):
        ryn = self.passenger(True)
        goblin = self.hostile()
        for _ in range(40):   # the scan picks at random: enough rounds that "never" is not luck
            goblin.in_combat = False
            goblin.combat_targets.clear()
            combat_logic.scan_for_targets(goblin, self.world, self.player, force_aggression=True)
            self.assertNotIn(ryn, goblin.combat_targets)
        self.assertEqual(ryn.max_health, ryn.health)

    def test_what_reaches_her_anyway_does_nothing(self):
        ryn = self.passenger(True)
        self.assertEqual(0, ryn.take_damage(500, "physical"))
        self.assertTrue(ryn.is_alive)
        self.assertEqual(ryn.max_health, ryn.health)

    def test_without_the_property_a_companion_is_a_target_and_can_be_hurt(self):
        ryn = self.passenger(False)
        self.assertFalse(is_untargetable(ryn))
        self.assertGreater(ryn.take_damage(5, "physical"), 0)
        goblin = self.hostile()
        picked = False
        for _ in range(60):
            goblin.in_combat = False
            goblin.combat_targets.clear()
            combat_logic.scan_for_targets(goblin, self.world, self.player, force_aggression=True)
            picked = picked or ryn in goblin.combat_targets
        self.assertTrue(picked, "an ordinary companion is fair game, so the property is what protects her")


if __name__ == "__main__":
    unittest.main()
