# tests/singles/test_staged_fight_details.py
"""Three details a staged fight needs: how often a creature strikes, a death that is final, and a name that opens a sentence.

* `properties.attack_cooldown` (seconds): the pause between a creature's blows, so a fight can be read.
* `properties.respawn_cooldown: -1` keeps a friendly NPC dead as well as a hostile one.
* A conversation names a common-noun speaker ("elder of Ilmara") as "The elder of Ilmara".
"""

import re
import unittest

from engine.dialogue.manager import parse_graph
from engine.server import content_set as validator
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


class TestAttackCooldown(GameTestBase):
    def make(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="slow_goblin")
        self.assertIsNotNone(npc)
        return npc

    def test_the_default_is_the_engines_own(self):
        npc = self.make()
        self.assertEqual((3.0, 3.0), (npc.attack_cooldown, npc.combat_cooldown))

    def test_a_template_can_slow_its_blows(self):
        self.world.npc_templates["goblin"].setdefault("properties", {})["attack_cooldown"] = 6
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="slow_goblin_2")
        self.assertEqual((6.0, 6.0), (npc.attack_cooldown, npc.combat_cooldown))

    def test_the_value_must_be_a_sensible_number_of_seconds(self):
        for bad in ("slow", True, 0, 0.1, 500):
            errors = validator._npc_property_errors({"attack_cooldown": bad}, "npc", set())
            self.assertTrue([e for e in errors if "attack_cooldown must be" in e], (bad, errors))
        for good in (0.5, 3, 6.5, 120):
            self.assertFalse(validator._npc_property_errors({"attack_cooldown": good}, "npc", set()), good)


class TestAFinalDeath(GameTestBase):
    def friendly(self, never):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="mourned" if never else "returned")
        self.world.add_npc(npc)
        npc.home_region_id, npc.home_room_id = self.player.current_region_id, self.player.current_room_id
        npc.current_region_id, npc.current_room_id = npc.home_region_id, npc.home_room_id
        npc.properties.pop("essential", None)
        if never:
            npc.properties["respawn_cooldown"] = -1
        return npc

    def test_a_friendly_comes_back_unless_its_author_said_never(self):
        returning = self.friendly(never=False)
        returning.die(self.world)
        self.assertTrue([e for e in self.world.respawn_manager.respawn_queue if e["instance_id"] == "returned"], "the usual: it is queued")
        gone = self.friendly(never=True)
        gone.die(self.world)
        self.assertFalse([e for e in self.world.respawn_manager.respawn_queue if e["instance_id"] == "mourned"], "respawn_cooldown -1: it is not")


class TestTheSpeakersName(GameTestBase):
    def speaker_line(self, name):
        manager = self.world.dialogue_manager
        npc = next(iter(self.world.npcs.values()))
        npc.name = name
        graph, _ = parse_graph({"id": "p", "root": "a", "nodes": {"a": {"text": "Hello.", "choices": [{"text": "Bye.", "end": True}]}}}, "p", "p.json")
        node = manager.open(self.player, npc, graph)
        text = manager.render_node(self.player, npc, node, manager.current(self.player))
        return re.sub(r"\[\[[^\]]*\]\]", "", text).splitlines()[0]

    def test_a_common_noun_name_opens_the_sentence_with_the(self):
        self.assertTrue(self.speaker_line("elder of Ilmara").startswith("The elder of Ilmara speaks:"))

    def test_a_proper_name_is_left_alone(self):
        self.assertTrue(self.speaker_line("King Aldous").startswith("King Aldous speaks:"))
        self.assertTrue(self.speaker_line("the chancellor").startswith("The chancellor speaks:"))


if __name__ == "__main__":
    unittest.main()
