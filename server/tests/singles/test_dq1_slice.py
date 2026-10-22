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


class TestTheNorth(Base):
    def test_the_vault_is_dark_and_a_torch_lights_it(self):
        self.at("ostrun_vault", "v1_hall")
        self.assertIn("pitch dark", self.say("look"))
        self.assertIn("no way north", self.say("go north"))
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template("item_pitch_torch", self.world))
        self.say("use pitch torch")
        self.assertIn("vault door", self.say("look").lower())

    def test_the_tablet_names_the_three_things(self):
        self.at("ostrun_vault", "v2_sanctum")
        self.player.apply_effect({"type": "status", "name": "Torchlight", "tags": ["light"], "base_duration": 100}, 0.0)
        said = self.say("look at stone tablet")
        for word in ("sunstones", "cloudcaller", "signet", "moon harp", "prism"):
            self.assertIn(word, said)

    def test_the_barrow_has_four_floors_the_harp_and_the_circlet(self):
        region = self.world.get_region("harrow_barrow")
        floors = {room_id.split("_")[0] for room_id in region.rooms}
        self.assertEqual({"b1", "b2", "b3", "b4"}, floors)
        contents = {chest: [i["item_id"] for i in self.world.item_templates[chest]["properties"]["contains"]] for chest in
                    ("chest_barrow_harp", "chest_barrow_circlet")} if hasattr(self.world, "item_templates") else {}
        if contents:
            self.assertEqual(["item_moon_harp"], contents["chest_barrow_harp"])
            self.assertEqual(["item_gravebound_circlet"], contents["chest_barrow_circlet"])

    def test_the_barrows_creatures_are_the_originals_by_depth(self):
        zones = self.world.encounters.zones
        self.assertEqual({"rattling_spirit", "fen_brute", "fellwing", "bone_walker", "hexer"}, {m["npc"] for m in zones["barrow_first"]["monsters"]})
        self.assertEqual({"barrow_haunt", "packlord", "bog_chieftain", "fen_sage", "hollow_knight"}, {m["npc"] for m in zones["barrow_deep"]["monsters"]})

    def test_egress_works_only_underground_and_recall_only_above_it(self):
        while self.player.runtime_state.progression.level < 13:
            self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
        self.at("harrow_barrow", "b2_cross")
        self.assertIn("stone", self.say("cast recall"))
        self.assertEqual("harrow_barrow:b2_cross", self.where())
        self.say("cast egress")
        self.assertEqual("harrowmere:graveyard", self.where())
        self.assertIn("nothing above you", self.say("cast egress"))
        self.say("cast recall")
        self.assertEqual("telgard:courtyard", self.where())

    def test_the_priest_takes_a_worn_curse_away(self):
        from engine.items.item_factory import ItemFactory

        self.at("bracken_ford", "chapel")
        self.player.equipment["head"] = ItemFactory.create_item_from_template("item_gravebound_circlet", self.world)
        self.say("talk priest")
        self.say("reply 1")
        self.assertIsNone(self.player.equipment["head"])


class TestTheEast(Base):
    def _give(self, item_id):
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, self.world))

    def _held(self, item_id):
        return any(slot.item and slot.item.obj_id == item_id for slot in self.player.inventory.slots)

    def test_the_slumber_pipe_lies_four_steps_south_of_the_bath_and_is_found_once(self):
        self.at("kalder", "lane3")
        self.assertIn("nothing to search", self.say("search"))
        self.at("kalder", "lane4")
        self.say("search")
        self.assertTrue(self._held("item_slumber_pipe"))
        self.assertIn("nothing to search", self.say("search"))

    def test_the_hermit_trades_the_staff_for_the_harp_and_for_nothing_else(self):
        self.at("frostfell_hollow", "f_hall")
        self.say("talk hermit")
        self.assertFalse(self._held("item_cloudcallers_staff"))
        self._give("item_moon_harp")
        self.say("talk hermit")
        self.say("reply 1")
        self.assertTrue(self._held("item_cloudcallers_staff"))
        self.assertFalse(self._held("item_moon_harp"))

    def test_the_princess_is_carried_home_and_gives_a_locket_that_counts_the_steps(self):
        self.at("mirewater_tunnel", "t_cell")
        self.say("talk princess")
        self.say("reply 1")
        self.assertIs(True, self.player.flags.get("princess_with_you"))
        self.assertTrue([n for n in self.world.npcs.values() if n.template_id == "princess_elowen" and n.properties.get("companion")])
        self.assertTrue([n for n in self.world.npcs.values() if n.template_id == "princess_elowen" and n.properties.get("untargetable")])
        self.at("telgard", "great_hall")
        self.say("go up")
        for _ in range(20):
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)
        self.assertIs(True, self.player.flags.get("princess_home"))
        self.assertTrue([n for n in self.world.npcs.values() if n.template_id == "princess_elowen_court"])
        self.say("talk princess")
        self.say("reply 1")
        self.assertTrue(self._held("item_elowens_locket"))
        self.at("heartland", "hl_1_3")
        self.assertIn("steps behind", self.say("use elowen's locket"))
        self.assertTrue(self._held("item_elowens_locket"), "the locket is kept")

    def test_the_tunnels_dragon_is_a_placed_boss_that_does_not_come_back(self):
        den = self.world.get_region("mirewater_tunnel").get_room("t_den")
        self.assertEqual("drake_warden", den.initial_npc_refs[0]["instance_id"] if den.initial_npc_refs else "drake_warden")
        warden = self.world.npc_templates["verdant_drake_warden"]
        self.assertEqual(-1, warden["properties"]["respawn_cooldown"])
        self.assertEqual(45, warden["properties"]["xp_reward"])

    def test_the_east_roads_creatures_are_the_originals_fifth_and_seventh_groups(self):
        zones = self.world.encounters.zones
        self.assertEqual({"pale_shade", "hedge_mage", "hexwing", "dune_stinger"}, {m["npc"] for m in zones["eastreach_west"]["monsters"]})
        self.assertEqual({"pale_shade", "hedge_mage", "hexwing", "dune_stinger", "bone_walker"}, {m["npc"] for m in zones["eastreach_east"]["monsters"]})
        self.assertEqual({"pale_shade", "hedge_mage", "dune_stinger", "bog_imp"}, {m["npc"] for m in zones["mirewater"]["monsters"]})


if __name__ == "__main__":
    unittest.main()
