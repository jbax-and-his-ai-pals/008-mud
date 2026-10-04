# tests/singles/test_health_cost_abilities.py
"""An ability can cost a part of the caster's health, a set can have no ability pool at all, and an
ability can hit every enemy in the room.

Aldric's Gloom Wave in `ff4_slice` is all three: it costs an eighth of his maximum health, he starts
with 0 mana (and levelling does not give him any), and it breaks over every hostile in the room.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set as validator
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _text(events):
    return "\n".join(_MARKUP.sub("", str(e["payload"])) for e in events if e["type"] == "text")


class TestDarkWave(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="dw").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.player.current_region_id, self.player.current_room_id = "road", "castle_road"

    def goblins(self, count):
        made = []
        for index in range(count):
            goblin = NPCFactory.create_npc_from_template("goblin_scout", self.server.world, instance_id=f"dw_goblin_{index}")
            goblin.current_region_id, goblin.current_room_id = "road", "castle_road"
            goblin.health = goblin.max_health = 200
            self.server.world.add_npc(goblin)
            made.append(goblin)
        return made

    def test_aldric_starts_with_no_mana_and_levelling_does_not_give_him_any(self):
        magic = self.player.runtime_state.magic
        self.assertEqual((0, 0), (magic.mana, magic.max_mana))
        self.player.gain_experience(10_000)
        self.assertGreater(self.player.runtime_state.progression.level, 1)
        self.assertEqual(0, magic.max_mana)
        self.assertNotIn("Max Mana", _text([{"type": "text", "payload": self.player.level_up()}]))

    def test_the_cast_costs_an_eighth_of_his_health_and_no_mana(self):
        self.goblins(1)
        before = self.player.health
        said = _text(self.server.execute_command(self.sid, "cast gloom wave"))
        self.assertIn("looses a wave of shadow", said)
        self.assertEqual(before - 13, self.player.health, "an eighth of 100, rounded")
        self.assertEqual(0, self.player.runtime_state.magic.mana)

    def test_it_hits_every_enemy_in_the_room(self):
        crowd = self.goblins(3)
        self.server.execute_command(self.sid, "cast gloom wave")
        self.assertTrue(all(g.health < 200 for g in crowd), [g.health for g in crowd])

    def test_it_will_not_take_the_last_of_his_health(self):
        from engine.magic.spell_registry import get_spell

        self.goblins(1)
        self.player.health = 10
        # straight at the cast, so no round of combat can touch his health in between
        result = self.player.cast_spell(get_spell("gloom_wave"), None, self.server.world.clock.now(), self.server.world)
        self.assertFalse(result["success"])
        self.assertIn("would cost you 13 health", _MARKUP.sub("", result["message"]))
        self.assertEqual(10, self.player.health, "a refused cast costs nothing")

    def test_the_listing_and_details_say_what_it_costs(self):
        self.assertIn("Gloom Wave: 1/8 HP", _text(self.server.execute_command(self.sid, "abilities")))
        details = _text(self.server.execute_command(self.sid, "abilities gloom wave"))
        self.assertIn("Health Cost: 1/8 HP of your maximum", details)
        self.assertIn("All enemies", details)

    def test_the_character_panel_carries_the_cost_and_the_noun(self):
        events = self.server._panel_events(self.sid, force=True)
        sheet = next(e["payload"] for e in events if e["type"] == "character")
        self.assertEqual("1/8 HP", sheet["spells"][0]["cost_text"])
        self.assertEqual("Abilities", sheet["ability_noun"])
        self.assertEqual(0, sheet["ability_resource"]["max"])


class TestTheValidatorRefusesBadValues(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors(self):
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def edit_spell(self, **changes):
        path = self.package / "data" / "magic" / "slice_spells.json"
        spells = json.loads(path.read_text(encoding="utf-8"))
        spells["gloom_wave"].update(changes)
        path.write_text(json.dumps(spells, indent=4), encoding="utf-8")

    def test_the_shipped_set_is_clean(self):
        self.assertEqual([], self.errors())

    def test_a_health_cost_must_be_a_fraction_below_one(self):
        for bad in (1.0, 1.5, -0.1, "an eighth"):
            self.edit_spell(health_cost_fraction=bad)
            self.assertTrue(any("health_cost_fraction" in m for m in self.errors()), bad)

    def test_a_pool_size_must_be_a_whole_number_of_zero_or_more(self):
        path = self.package / "data" / "contracts" / "world_contracts.json"
        contracts = json.loads(path.read_text(encoding="utf-8"))
        for resource in contracts["resources"]:
            if resource["id"] == "mana":
                resource["max"] = -3
        path.write_text(json.dumps(contracts, indent=4), encoding="utf-8")
        self.assertTrue(any("max" in m for m in self.errors()))


if __name__ == "__main__":
    unittest.main()
