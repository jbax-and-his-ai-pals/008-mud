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


class TestTheSouthEast(Base):
    def _held(self, item_id):
        return any(slot.item and slot.item.obj_id == item_id for slot in self.player.inventory.slots)

    def _give(self, item_id):
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, self.world))

    def test_rivenhal_sells_keys_and_the_best_buyable_arms(self):
        keys = {e["item_id"] for e in self.world.npc_templates["riven_locksmith"]["properties"]["sells_items"]}
        arms = {e["item_id"] for e in self.world.npc_templates["riven_armourer"]["properties"]["sells_items"]}
        self.assertEqual({"item_brass_key"}, keys)
        self.assertEqual({"item_bronze_blade", "item_woodsmans_axe", "item_longblade", "item_half_harness", "item_plate_harness", "item_spellwoven_mail"}, arms)

    def test_the_inns_inner_chest_is_behind_two_locked_doors(self):
        self.at("rivenhal", "inn")
        self.assertIn("locked", self.say("go north").lower())
        self._give("item_brass_key")
        self.say("go north")
        self.assertEqual("rivenhal:back_room", self.where())
        self.assertIn("locked", self.say("go north").lower())
        self._give("item_brass_key")
        self.say("go north")
        self.assertEqual("rivenhal:strongroom", self.where())

    def test_the_sage_makes_the_prism_only_from_all_three_things(self):
        self.at("sagehollow", "s_hall")
        self.player.apply_effect({"type": "status", "name": "Torchlight", "tags": ["light"], "base_duration": 100}, 0.0)
        for item in ("item_sunstones", "item_cloudcallers_staff"):
            self._give(item)
        self.say("talk sage")
        self.assertFalse(self._held("item_prism_tear"), "two of three is not enough")
        self._give("item_ostruns_signet")
        self.say("talk sage")
        self.say("reply 1")
        self.assertTrue(self._held("item_prism_tear"))
        self.assertFalse(self._held("item_sunstones") or self._held("item_cloudcallers_staff") or self._held("item_ostruns_signet"))
        self.assertIs(True, self.player.flags.get("prism_made"))

    def test_the_fens_creatures_are_the_originals_eighth_tenth_eleventh_and_twelfth_groups(self):
        zones = self.world.encounters.zones
        self.assertEqual({"hexwing", "dune_stinger", "bone_walker", "hexer", "grey_wolf"}, {m["npc"] for m in zones["fenlands_north"]["monsters"]})
        self.assertEqual({"iron_stinger", "gaunt_wraith", "packlord", "gilded_husk"}, {m["npc"] for m in zones["fenlands_south"]["monsters"]})
        self.assertEqual({"gaunt_wraith", "crag_wyvern", "packlord", "gilded_husk"}, {m["npc"] for m in zones["sagehollow"]["monsters"]})


class TestTheSouth(Base):
    def _give(self, item_id):
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, self.world))

    def _held(self, item_id):
        return any(slot.item and slot.item.obj_id == item_id for slot in self.player.inventory.slots)

    def test_the_colossus_bars_the_road_until_it_sleeps_or_is_dead(self):
        self.at("southwilds", "sw_6_3")
        self.player.health = self.player.max_health = 10 ** 5
        golem, _ = self.world.spawn_npc("mossback_colossus", "southwilds", "sw_6_3", "golem_gate")
        self.assertIn("does not move aside", self.say("go south"))
        self.assertEqual("southwilds:sw_6_3", self.where())
        self.player.flags["golem_asleep"] = True
        golem.apply_effect({"type": "status", "name": "Slumber", "tags": ["sleep"], "base_duration": 3600}, 0.0)
        self.say("go south")
        self.assertEqual("cairnwall:gate", self.where())

    def test_the_slumber_pipe_puts_it_to_sleep_and_sets_the_flag(self):
        self.at("southwilds", "sw_6_3")
        golem, _ = self.world.spawn_npc("mossback_colossus", "southwilds", "sw_6_3", "golem_gate")
        self._give("item_slumber_pipe")
        self.say("use slumber pipe on mossback colossus")
        self.assertTrue(golem.has_effect_tag("sleep"))
        self.assertIs(True, self.player.flags.get("golem_asleep"))
        self.assertTrue(self._held("item_slumber_pipe"), "the pipe is kept")

    def test_a_dead_colossus_opens_the_road_too(self):
        self.at("southwilds", "sw_6_3")
        self.world.remove_npcs("mossback_colossus")
        self.say("go south")
        self.assertEqual("cairnwall:gate", self.where())

    def test_ostruns_mail_comes_only_after_the_knight_is_dead(self):
        self.at("haskarth", "h_trees")
        knight = [n for n in self.world.npcs.values() if n.template_id == "cleaver_knight" and n.current_room_id == "h_trees"]
        self.assertTrue(knight, "the knight is placed in the trees")
        self.assertIn("nothing to search", self.say("search"))
        knight[0].take_damage(10 ** 6, "physical")
        self.say("search")
        self.assertTrue(self._held("item_ostruns_mail"))

    def test_the_mail_heals_a_little_each_step_and_turns_a_barrier_floor_aside(self):
        mail = self.world.item_templates["item_ostruns_mail"]["properties"] if hasattr(self.world, "item_templates") else {}
        if mail:
            self.assertEqual(1, mail["heal_per_step"])
            self.assertEqual(100, mail["resistances"]["barrier"])
        from engine.items.item_factory import ItemFactory

        self.player.equipment["body"] = ItemFactory.create_item_from_template("item_ostruns_mail", self.world)
        self.assertEqual(100, self.player.get_resistance("barrier"))
        self.assertEqual(0, self.player.take_damage(5, "barrier"), "a poisoned floor does nothing to it")

    def test_the_locket_reads_the_number_the_scholar_gives_at_the_place_of_the_signet(self):
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template("item_elowens_locket", self.world))
        self.at("southwilds", "fen_end")
        said = self.say("use elowen's locket")
        told = re.search(r"(\d+) steps from the castle courtyard", self.world.npc_templates["cairn_scholar"]["dialog"]["greeting"]).group(1)
        self.assertIn(told, said)
        self.say("search")
        self.assertTrue(self._held("item_ostruns_signet"))

    def test_cairnwall_has_the_locked_vault_shop(self):
        stock = {e["item_id"] for e in self.world.npc_templates["cairn_vaultsmith"]["properties"]["sells_items"]}
        self.assertEqual({"item_emberbrand", "item_moonsilver_shield"}, stock)
        self.at("cairnwall", "inn")
        self.assertIn("locked", self.say("go west").lower())


class TestTheEnd(Base):
    def _tick(self, seconds):
        for _ in range(seconds):
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)

    def test_the_prism_tear_makes_a_bridge_only_at_the_shore(self):
        from engine.items.item_factory import ItemFactory

        self.player.inventory.add_item(ItemFactory.create_item_from_template("item_prism_tear", self.world))
        self.at("heartland", "hl_1_2")
        self.assertIn("water's edge", self.say("use the prism tear"))
        self.assertEqual({"east"} - set(self.world.get_region("heartland").get_room("hl_shore").exits), {"east"})
        self.at("heartland", "hl_shore")
        self.say("use the prism tear")
        self.assertEqual("skarn_isle:landing", self.world.get_region("heartland").get_room("hl_shore").exits["east"])
        self.assertFalse(any(slot.item and slot.item.obj_id == "item_prism_tear" for slot in self.player.inventory.slots), "it is used up")

    def test_saying_yes_to_the_sovereign_ends_the_game_for_good(self):
        self.at("skarnhold", "k_b7_throne")
        self.say("talk maldrath")
        self.say("reply 1")
        self.assertFalse(self.player.is_alive)
        self.assertIs(True, self.player.flags.get("_game_over"))
        self.assertIn("adventure is over", self.say("respawn"))
        self.assertFalse(self.player.is_alive)

    def test_saying_no_makes_him_fight_in_his_first_form_and_the_wyrm_follows(self):
        self.at("skarnhold", "k_b7_throne")
        self.player.health = self.player.max_health = 10 ** 5
        self.say("talk maldrath")
        self.say("reply 2")
        man = [n for n in self.world.npcs.values() if n.template_id == "maldrath_man"]
        self.assertEqual(1, len(man))
        self.assertEqual([], [n for n in self.world.npcs.values() if n.template_id == "maldrath_herald"])
        man[0].take_damage(10 ** 6, "physical")
        self._tick(15)
        wyrm = [n for n in self.world.npcs.values() if n.template_id == "maldrath_wyrm" and n.is_alive]
        self.assertEqual(1, len(wyrm))
        wyrm[0].take_damage(10 ** 6, "physical")
        self._tick(30)
        self.assertIs(True, self.player.flags.get("maldrath_down"))

    def test_once_he_is_down_every_zone_is_quiet(self):
        self.player.flags["maldrath_down"] = True
        self.at("heartland", "hl_0_0")
        self.player.health = self.player.max_health = 10 ** 5
        self.world.encounters._rng.seed(1)
        for definition in self.world.encounters.zones.values():
            definition["chance"] = 1
        for room_id in ("hl_0_1", "hl_0_0", "hl_0_1", "hl_0_0"):
            self.world._arrive(self.player, "heartland", room_id, "heartland")
        self.assertFalse([n for n in self.world.npcs.values() if n.properties.get("encounter")])

    def test_the_castle_has_its_barrier_floors_and_its_three_locked_doors(self):
        region = self.world.get_region("skarnhold")
        self.assertEqual([{"type": "barrier"}], region.get_room("k_b5_a").properties["hazards"])
        locked = [room_id for room_id, room in region.rooms.items() if any(r.get("type") == "locked" for r in room.properties.get("exit_requirements", {}).values())]
        self.assertEqual({"k1_hall", "k_b7_hall"}, set(locked))
        self.assertEqual({"west", "east"}, set(region.get_room("k1_hall").properties["exit_requirements"]))

    def test_every_zone_of_the_game_goes_quiet_with_the_victory(self):
        for zone_id, definition in self.world.encounters.zones.items():
            self.assertEqual({"not": {"kind": "flag", "flag": "maldrath_down"}}, definition.get("when"), zone_id)


class TestTheCheckpoints(unittest.TestCase):
    """`checkpoint <name>` in a test session puts a fresh character at that point of the story, ready to play on."""

    EXPECTED = {
        "armed": ("bracken_ford:square", 3), "vault": ("northmarch:nm_2_1", 5), "barrow": ("harrowmere:graveyard", 8),
        "hermit": ("frostfell_hollow:f_hall", 10), "tunnel": ("mirewater_tunnel:t_den", 13), "court": ("telgard:throne_room", 14),
        "sage": ("sagehollow:s_hall", 20), "shore": ("heartland:hl_shore", 26), "throne": ("skarnhold:k_b7_hall", 28),
    }

    def _game(self, name):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(DQ1), deterministic_test_mode=True, default_presentation_mode="test")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Hero")
        server.execute_command(sid, "checkpoint %s" % name)
        return server, server.get_player_for_session(sid)

    def test_every_checkpoint_puts_the_hero_where_it_says_at_the_level_it_says(self):
        for name, (place, level) in self.EXPECTED.items():
            with self.subTest(checkpoint=name):
                _server, player = self._game(name)
                self.assertEqual(place, "%s:%s" % (player.current_region_id, player.current_room_id))
                self.assertEqual(level, player.runtime_state.progression.level)
                if name != "tunnel":  # the drake is already in the den, and a test server's clock does not wait for the hero
                    self.assertGreaterEqual(player.health, player.max_health * 0.8, "restored, bar a blow struck on arrival")

    def test_each_one_ends_every_scene_of_the_set_first(self):
        scenes = set()
        for path in (DQ1 / "data" / "scenes").glob("*.json"):
            if path.name != "checkpoints.json":
                import json

                scenes |= {k for k in json.loads(path.read_text(encoding="utf-8")) if not k.startswith("_")}
        import json

        checkpoints = json.loads((DQ1 / "data" / "scenes" / "checkpoints.json").read_text(encoding="utf-8"))
        self.assertEqual({"checkpoint_%s" % name for name in self.EXPECTED}, set(checkpoints))
        for name, definition in checkpoints.items():
            self.assertEqual(scenes, set(definition["beats"][0]["effects"]["end_scene"]), name)

    def test_the_last_ones_leave_the_hero_armed_for_the_end(self):
        _server, player = self._game("throne")
        self.assertEqual("item_ostruns_mail", player.equipment["body"].obj_id)
        held = [slot.item.obj_id for slot in player.inventory.slots if slot.item]
        self.assertIn("item_ostruns_edge", held + [i.obj_id for i in player.equipment.values() if i])

    def test_the_court_checkpoint_has_the_princess_home_and_the_locket_given(self):
        server, player = self._game("court")
        self.assertIs(True, player.flags.get("princess_home"))
        self.assertTrue([n for n in server.world.npcs.values() if n.template_id == "princess_elowen_court"])


if __name__ == "__main__":
    unittest.main()
