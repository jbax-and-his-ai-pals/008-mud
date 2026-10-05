# tests/singles/test_resistance_absorb.py
"""A resistance over 100% absorbs the blow as healing, and a fight phase can change a creature's resistances.

`stats.resistances` (and an item's) are percents: 50 halves a type of damage, -100 doubles it, 100 takes none. Past 100
the creature drinks the blow in: it takes nothing and is healed by the excess. A phase may carry `resistances`
that add to the creature's own while it lasts (a fire-master under a cloak of flame, a creature of ice until it thaws).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.magic.effects import apply_spell_effect
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.npcs import phases
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")
CLOAKED = [{"name": "cloaked", "seconds": 5, "resistances": {"fire": 200}}, {"name": "bare", "seconds": 5, "resistances": {"fire": -100}}]


class TestAbsorb(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = ROOM
        self.addCleanup(SPELL_REGISTRY.pop, "test_flame", None)
        SPELL_REGISTRY["test_flame"] = Spell(
            "test_flame", "Flame", "Fire.", effects=[{"type": "damage", "value": 30, "damage_type": "fire"}],
            mana_cost=0, cooldown=1.0, target_type="enemy")

    def creature(self, name, fire):
        npc = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id=name)
        npc.current_region_id, npc.current_room_id = ROOM
        npc.stats.setdefault("resistances", {})["fire"] = fire
        npc.health, npc.max_health = 50, 100
        self.world.add_npc(npc)
        return npc

    def burn(self, npc):
        return apply_spell_effect(self.player, npc, SPELL_REGISTRY["test_flame"], None)

    def test_a_percent_under_100_still_only_lessens_the_blow(self):
        npc = self.creature("half", 50)
        self.burn(npc)
        self.assertLess(npc.health, 50)
        self.assertGreater(npc.health, 25)

    def test_100_takes_nothing(self):
        npc = self.creature("immune", 100)
        self.burn(npc)
        self.assertEqual(50, npc.health)

    def test_over_100_turns_the_blow_into_healing_and_says_so(self):
        npc = self.creature("sponge", 200)
        _, text = self.burn(npc)
        self.assertGreater(npc.health, 50)
        self.assertIn("drinks in the fire", text)

    def test_it_never_heals_past_full(self):
        npc = self.creature("full", 200)
        npc.health = 99
        self.burn(npc)
        self.assertEqual(100, npc.health)

    def test_a_phase_adds_to_the_creatures_own_resistance_while_it_lasts(self):
        npc = self.creature("cloak", 0)
        npc.properties["phases"] = CLOAKED
        self.assertEqual(0, npc.get_resistance("fire"), "out of a fight a phase adds nothing")
        npc.in_combat, npc.phase_index, npc.phase_until = True, 0, 1e12
        self.assertEqual(200, phases.resistance(npc, "fire"))
        self.assertEqual(200, npc.get_resistance("fire"))
        self.burn(npc)
        self.assertGreater(npc.health, 50, "under the cloak the fire heals")
        npc.phase_index = 1
        before = npc.health
        self.burn(npc)
        self.assertLess(npc.health, before - 25, "and bare, it takes double")


class TestTheValidator(unittest.TestCase):
    def errors(self, resistances):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        path = pkg / "data" / "npcs" / "hostiles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["goblin_scout"].setdefault("properties", {})["phases"] = [{"seconds": 5, "resistances": resistances}]
        path.write_text(json.dumps(data), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def test_good_values_pass(self):
        self.assertEqual([], [m for m in self.errors({"fire": 200, "ice": -100}) if "resistances" in m])

    def test_bad_values_are_refused(self):
        for bad in ({"fire": 201}, {"fire": -101}, {"fire": "all"}, {}, []):
            self.assertTrue([m for m in self.errors(bad) if "resistances" in m], bad)


if __name__ == "__main__":
    unittest.main()
