# tests/singles/test_npc_persists_elite_stats.py
"""A creature made stronger than its template stays stronger through a save.

The ambient spawner promotes some hostiles to elites (`npcs/elite.py`: more of every
stat, a bigger attack and defence, better loot), and an instanced boss is promoted the
same way. `NPC.to_dict` kept the boosted `stats` but not the attack, defence or loot
the factory builds from the *template* unless it is handed them, so a saved elite came
back with its stats and none of the rest: `defense` 4 became 3, `attack_power` 9 became
8, and its bigger loot was the template's. It showed as an intermittent failure of the
world-snapshot round trip (a zombie the spawner happened to roll as an elite), which is
how it was found. Only the difference from the template is saved, as with properties.
"""

import copy
import unittest

from engine.npcs.elite import compute_elite_overrides
from engine.npcs.npc_factory import NPCFactory
from engine.world import world_snapshot
from tests.fixtures import GameTestBase


class TestNpcPersistsEliteStats(GameTestBase):
    def _elite(self, instance_id="zombie_elite"):
        template = self.world.npc_templates["zombie"]
        return NPCFactory.create_npc_from_template(
            "zombie", self.world, instance_id,
            current_region_id=self.player.current_region_id, current_room_id=self.player.current_room_id,
            **compute_elite_overrides(template, self.world),
        )

    def _plain(self, instance_id="zombie_plain"):
        return NPCFactory.create_npc_from_template(
            "zombie", self.world, instance_id,
            current_region_id=self.player.current_region_id, current_room_id=self.player.current_room_id,
        )

    def _reload(self, npc, instance_id):
        state = copy.deepcopy(npc.to_dict())
        template_id = state.pop("template_id")
        return NPCFactory.create_npc_from_template(template_id, self.world, instance_id, **state)

    def test_an_elite_comes_back_as_strong_as_it_was(self):
        elite = self._elite()
        plain = self._plain()
        self.assertGreater(elite.defense, plain.defense, "the probe elite is actually stronger")
        again = self._reload(elite, "zombie_elite_again")
        self.assertEqual(elite.defense, again.defense)
        self.assertEqual(elite.stats, again.stats)
        self.assertEqual(elite.attack_power, again.attack_power)
        self.assertEqual(elite.name, again.name)

    def test_an_elites_bigger_loot_comes_back_too(self):
        elite = self._elite()
        self.assertNotEqual(self._plain().loot_table, elite.loot_table, "the probe elite has different loot")
        self.assertEqual(elite.loot_table, self._reload(elite, "zombie_elite_again").loot_table)

    def test_an_ordinary_creature_saves_none_of_it(self):
        state = self._plain().to_dict()
        for key in ("attack_power", "defense", "loot_table"):
            self.assertNotIn(key, state, "only what differs from the template is saved")
        again = self._reload(self._plain(), "zombie_plain_again")
        self.assertEqual(self._plain().attack_power, again.attack_power)
        self.assertEqual(self._plain().defense, again.defense)

    def test_a_content_edit_to_an_untouched_template_value_still_shows_through(self):
        npc = self._plain()
        state = copy.deepcopy(npc.to_dict())
        template = self.world.npc_templates["zombie"]
        original = template.get("defense")
        self.addCleanup(template.__setitem__, "defense", original)
        template["defense"] = (original or 0) + 5
        template_id = state.pop("template_id")
        again = NPCFactory.create_npc_from_template(template_id, self.world, "zombie_edited", **state)
        self.assertEqual((original or 0) + 5, again.defense)

    def test_an_elite_survives_a_snapshot_and_restore(self):
        elite = self._elite("zombie_snapshot_elite")
        self.world.add_npc(elite)
        before = copy.deepcopy(self.world.npcs["zombie_snapshot_elite"].to_dict())
        snapshot = world_snapshot.capture(self.world)
        world_snapshot.restore(self.world, copy.deepcopy(snapshot))
        after = self.world.npcs["zombie_snapshot_elite"].to_dict()
        self.assertEqual(before["stats"], after["stats"])
        self.assertEqual(self.world.npcs["zombie_snapshot_elite"].defense, elite.defense)
        self.assertEqual(self.world.npcs["zombie_snapshot_elite"].attack_power, elite.attack_power)


if __name__ == "__main__":
    unittest.main()
