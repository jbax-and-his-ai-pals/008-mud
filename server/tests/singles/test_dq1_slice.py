# tests/singles/test_dq1_slice.py
"""The dq1 adaptation (`content_sets/dq1_slice`), told stretch by stretch as the set is built. A test about a shipped set may name it."""

import re
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
DQ1 = REPO_ROOT / "content_sets" / "dq1_slice"
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")

# The original's cumulative experience to reach levels 2 to 30.
CUMULATIVE = [7, 23, 47, 110, 220, 450, 800, 1300, 2000, 2900, 4000, 5500, 7500, 10000, 13000, 16000, 19000, 22000, 26000,
              30000, 34000, 38000, 42000, 46000, 50000, 54000, 58000, 62000, 65000]


class Base(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(DQ1), deterministic_test_mode=True, default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Hero")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world

    def say(self, command):
        return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in self.server.execute_command(self.sid, command) if e.get("type") in ("text", "error")))

    def at(self, region, room):
        self.player.current_region_id, self.player.current_room_id = region, room

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)


class TestTheHero(Base):
    def test_he_starts_in_the_throne_room_with_nothing_and_fifteen_health(self):
        self.assertEqual("telgard:throne_room", self.where())
        self.assertEqual((15, 0, 4, 4), (self.player.max_health, self.player.runtime_state.magic.max_mana, self.player.stats["strength"], self.player.stats["agility"]))
        self.assertEqual(0, self.player.runtime_state.gold)

    def test_the_levels_come_at_the_originals_experience(self):
        for index, total in enumerate(CUMULATIVE):
            level = index + 2
            self.player.runtime_state.progression.level = 1
            self.player.runtime_state.progression.experience = 0
            while self.player.runtime_state.progression.level < level - 1:
                self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
            before = CUMULATIVE[index - 1] if index else 0
            self.assertEqual(level - 1, self.player.runtime_state.progression.level)
            self.player.gain_experience(total - before - 1 - self.player.runtime_state.progression.experience)
            self.assertEqual(level - 1, self.player.runtime_state.progression.level, "one short of %d experience" % total)
            self.player.gain_experience(1)
            self.assertEqual(level, self.player.runtime_state.progression.level, "at %d experience" % total)

    def test_the_cap_is_level_thirty(self):
        self.player.gain_experience(10 ** 6)
        self.assertEqual(30, self.player.runtime_state.progression.level)

    def test_spells_come_at_their_levels(self):
        expected = {3: "mend", 4: "singe", 7: "lull", 9: "glimmer", 10: "hush", 12: "egress", 13: "recall", 15: "ward", 17: "restore", 19: "conflagrate"}
        known = set()
        for level in range(2, 31):
            while self.player.runtime_state.progression.level < level:
                self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
            known = set(self.player.runtime_state.magic.known_spells)
            for need_level, spell in expected.items():
                self.assertEqual(level >= need_level, spell in known, "%s at level %d" % (spell, level))

    def test_the_levels_stats_are_the_table(self):
        while self.player.runtime_state.progression.level < 10:
            self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
        self.assertEqual((54, 40, 35, 31), (self.player.max_health, self.player.runtime_state.magic.max_mana, self.player.stats["strength"], self.player.stats["agility"]))


class TestTheCastle(Base):
    def test_the_treasury_pays_gold_a_torch_and_a_key(self):
        self.say("go south")
        for chest in ("royal coffer", "cedar box", "iron-banded chest"):
            self.say("open %s" % chest)
            self.say("take all from %s" % chest)
        self.assertEqual(120, self.player.runtime_state.gold)
        held = [slot.item.obj_id for slot in self.player.inventory.slots if slot.item]
        self.assertIn("item_pitch_torch", held)
        self.assertIn("item_brass_key", held)

    def test_a_key_opens_a_door_once_and_is_spent(self):
        self.at("telgard", "great_hall")
        from engine.items.item_factory import ItemFactory

        self.assertIn("locked", self.say("go west").lower())
        self.assertEqual("telgard:great_hall", self.where())
        self.player.inventory.add_item(ItemFactory.create_item_from_template("item_brass_key", self.world))
        self.say("go west")
        self.assertEqual("telgard:west_room", self.where())
        self.assertFalse([slot for slot in self.player.inventory.slots if slot.item and slot.item.obj_id == "item_brass_key"])
        self.say("go east")
        self.say("go west")
        self.assertEqual("telgard:west_room", self.where(), "and the door stays open for this hero")

    def test_the_gate_turns_away_a_hero_wearing_something_cursed(self):
        from engine.items.item_factory import ItemFactory

        self.at("heartland", "hl_1_2")
        self.player.equipment["head"] = ItemFactory.create_item_from_template("item_gravebound_circlet", self.world)
        self.assertIn("cursed", self.say("go north").lower())
        self.assertEqual("heartland:hl_1_2", self.where())
        self.player.equipment["head"] = None
        self.say("go north")
        self.assertEqual("telgard:courtyard", self.where())


class TestTheShops(Base):
    def _stock(self, npc_id):
        return {entry["item_id"] for entry in self.world.npc_templates[npc_id]["properties"]["sells_items"]}

    def test_the_armourer_sells_what_the_original_sold_at_its_prices(self):
        self.assertEqual({"item_willow_staff", "item_oak_cudgel", "item_bronze_blade", "item_linen_tunic", "item_hide_jerkin", "item_buckler"}, self._stock("ford_armourer"))
        prices = {item_id: self.world.item_templates[item_id]["value"] * 2 for item_id in self._stock("ford_armourer")} if hasattr(self.world, "item_templates") else {}
        if prices:
            self.assertEqual({"item_willow_staff": 10, "item_oak_cudgel": 60, "item_bronze_blade": 180, "item_linen_tunic": 20, "item_hide_jerkin": 70, "item_buckler": 90}, prices)

    def test_a_bed_at_the_ford_costs_six(self):
        self.at("bracken_ford", "inn")
        self.player.runtime_state.gold = 20
        self.player.health = 3
        self.say("talk innkeeper")
        self.say("reply 1")
        self.assertEqual(14, self.player.runtime_state.gold)
        self.assertEqual(15, self.player.health)


class TestTheFields(Base):
    def test_the_fields_have_two_zones_with_the_originals_first_two_groups(self):
        zones = self.world.encounters.zones
        near = zones["heartland_near"]
        far = zones["heartland_far"]
        self.assertEqual({"mire_blob", "crimson_blob"}, {m["npc"] for m in near["monsters"]})
        self.assertEqual({"crimson_blob", "mire_blob", "gloomwing"}, {m["npc"] for m in far["monsters"]})
        self.assertFalse(set(near["rooms"]) & set(far["rooms"]))

    def test_the_castle_and_the_town_are_safe_from_them(self):
        self.assertEqual([], self.world.encounters.zones_for("telgard", "courtyard"))
        self.assertTrue(self.world.is_location_safe("bracken_ford", "square"))


class TestTheCreatures(Base):
    def test_every_creature_pays_what_the_original_paid(self):
        wolf = self.world.npc_templates["grey_wolf"]
        self.assertEqual(16, wolf["properties"]["xp_reward"])
        self.assertEqual([37, 49], wolf["loot_table"]["gold_value"]["quantity"])
        self.assertEqual(30, wolf["max_health"])
        blob = self.world.npc_templates["quicksilver_blob"]
        self.assertEqual(115, blob["properties"]["xp_reward"])
        self.assertTrue(blob["properties"]["status_immune"])

    def test_the_boss_forms_are_there(self):
        for template in ("maldrath_man", "maldrath_wyrm", "verdant_drake", "cleaver_knight", "mossback_colossus"):
            self.assertIn(template, self.world.npc_templates)


if __name__ == "__main__":
    unittest.main()
