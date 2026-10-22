# tests/singles/test_zelda1.py
"""The zelda1 adaptation (`content_sets/zelda1`), told stretch by stretch as the set is built. A test about a shipped set may name it."""

import re
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
ZELDA1 = REPO_ROOT / "content_sets" / "zelda1"
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
HEART = 16


class Base(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(ZELDA1), deterministic_test_mode=True, default_presentation_mode="player")
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

    def give(self, item_id, count=1):
        for _ in range(count):
            self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, self.world))

    def foes(self, template):
        return [n for n in self.world.npcs.values() if n.is_alive and n.template_id == template]


class TestTheHero(Base):
    def test_he_starts_in_the_meadow_with_three_hearts_a_small_shield_and_no_sword(self):
        self.assertEqual("ardenmoor_south:meadow_start", self.where())
        self.assertEqual(3 * HEART, self.player.max_health)
        self.assertEqual("item_small_shield", self.player.equipment["off_hand"].obj_id)
        self.assertIsNone(self.player.equipment.get("main_hand"))
        self.assertEqual(0, self.player.runtime_state.gold)

    def test_health_is_told_in_hearts_and_a_half_heart_is_eight_points(self):
        self.assertIn("3/3 hearts", self.say("status"))
        self.player.health = 2 * HEART + HEART // 2
        self.assertIn("2½/3 hearts", self.say("status"))

    def test_the_old_man_gives_a_wooden_sword_once(self):
        self.say("go in")
        self.say("talk old man")
        self.say("reply 1")
        self.assertEqual("item_wooden_sword", self.player.equipment["main_hand"].obj_id)
        self.say("talk old man")
        self.assertEqual(0, self.player.inventory.count_item("item_wooden_sword"), "a second talk gives nothing more")

    def test_a_sword_hit_is_one_unit_of_the_fights(self):
        """A red spitter falls to one hit of the wooden sword, a bone warrior to two, a hurler to three, the drake to six."""
        from engine.core.combat_system import CombatSystem

        self.player.equipment["main_hand"] = ItemFactory.create_item_from_template("item_wooden_sword", self.world)
        blow = self.player.get_attack_power()
        self.assertIn(blow, range(7, 11))
        for template, hits in (("spitter", 1), ("blue_spitter", 2), ("bone_warrior", 2), ("hurler", 3)):
            foe, _status = self.world.spawn_npc(template, "ardenmoor_south", "meadow_start", "probe_%s" % template)
            low = 10 ** 6
            high = 0
            for _ in range(200):
                damage = CombatSystem.calculate_physical_damage(self.player, foe, blow)
                low, high = min(low, damage), max(high, damage)
            self.assertLessEqual(foe.max_health, low * hits, "%s: %d hits of at least %d kill it" % (template, hits, low))
            self.assertGreater(foe.max_health, high * (hits - 1), "%s: fewer than %d hits of at most %d do not" % (template, hits, high))
            self.world.remove_npcs(foe.obj_id)
        drake, _status = self.world.spawn_npc("aquilor", "ardenmoor_south", "meadow_start", "probe_drake")
        self.assertIn(round(drake.max_health / 8.5), (5, 6), "the drake takes about six")
        self.world.remove_npcs(drake.obj_id)


class TestKestrelKeep(Base):
    def test_the_gap_in_the_trees_leads_into_the_keep(self):
        self.at("ardenmoor_south", "as_1_0")
        self.say("go in")
        self.assertEqual("kestrel_keep:k_entrance", self.where())

    def test_the_archers_gallery_shuts_until_the_archers_are_down(self):
        self.at("kestrel_keep", "k_bow")
        self.assertEqual(3, len([n for n in self.foes("bone_warrior") if (n.current_region_id, n.current_room_id) == ("kestrel_keep", "k_bow")]), "three archers")
        self.assertIn("shut", self.say("go south").lower())
        self.assertEqual("kestrel_keep:k_bow", self.where())
        for npc in [n for n in self.foes("bone_warrior") if (n.current_region_id, n.current_room_id) == ("kestrel_keep", "k_bow")]:
            self.world.remove_npcs(npc.obj_id)
        self.say("go south")
        self.assertEqual("kestrel_keep:k_west", self.where())

    def test_the_bow_costs_a_rupee_a_shot_and_is_known_once_taken(self):
        self.at("kestrel_keep", "k_bow")
        for npc in [n for n in self.foes("bone_warrior") if (n.current_region_id, n.current_room_id) == ("kestrel_keep", "k_bow")]:
            self.world.remove_npcs(npc.obj_id)
        self.assertNotIn("fire_arrow", self.player.runtime_state.magic.known_spells)
        self.say("take bow")
        self.assertIn("fire_arrow", self.player.runtime_state.magic.known_spells)
        foe, _status = self.world.spawn_npc("hurler", "kestrel_keep", "k_bow", "target")
        self.player.runtime_state.gold = 0
        self.assertIn("Not enough", self.say("cast arrow on hurler"))
        self.player.runtime_state.gold = 3
        self.say("cast arrow on hurler")
        self.assertEqual(2, self.player.runtime_state.gold)
        self.assertLess(foe.health, foe.max_health)

    def test_a_bomb_opens_the_cracked_wall_and_only_that_wall(self):
        self.give("item_bomb", 2)
        self.at("kestrel_keep", "k_hall")
        self.say("use bomb")
        self.assertEqual(1, self.player.inventory.count_item("item_bomb"))
        self.at("kestrel_keep", "k_wall")
        room = self.world.get_region("kestrel_keep").get_room("k_wall")
        self.assertNotIn("north", room.exits)
        self.assertIn("bursts", self.say("use bomb"))
        self.assertIn("north", room.exits)

    def test_the_iron_door_wants_a_key_and_spends_it(self):
        self.at("kestrel_keep", "k_hall2")
        self.say("go north")
        self.assertEqual("kestrel_keep:k_hall2", self.where(), "locked")
        self.give("item_small_key")
        self.say("go north")
        self.assertEqual("kestrel_keep:k_ante", self.where())
        self.assertEqual(0, self.player.inventory.count_item("item_small_key"))

    def test_a_grasping_hand_carries_the_hero_back_to_the_door(self):
        self.at("kestrel_keep", "k_hall2")
        hand = self.foes("grasping_hand")[0]
        from engine.npcs import combat as npc_combat
        from engine.magic.spell_registry import get_spell

        npc_combat.cast_spell(hand, get_spell("hand_grab"), self.player, 1000.0)
        self.assertEqual("kestrel_keep:k_entrance", self.where())

    def test_the_drake_gives_the_first_shard_and_a_heart_once(self):
        self.at("kestrel_keep", "k_boss")
        drake = self.foes("aquilor")[0]
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": drake})
        self.assertEqual(1, self.player.inventory.count_item("item_shard_1"))
        self.assertEqual(4 * HEART, self.player.max_health)
        self.assertEqual(4 * HEART, self.player.health, "and the heart is full")
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": drake})
        self.assertEqual(4 * HEART, self.player.max_health, "the heart is given once")


class TestTheOpenGround(Base):
    def test_a_rock_that_rings_hollow_gives_way_to_a_bomb_and_hides_thirty_rupees(self):
        self.at("ardenmoor_south", "as_0_2")
        self.say("go in")
        self.assertEqual("ardenmoor_south:as_0_2", self.where())
        self.give("item_bomb")
        self.assertIn("blows in", self.say("use bomb"))
        self.say("go in")
        self.assertEqual("ardenmoor_south:bomb_cave", self.where())
        self.say("take 30 rupees")
        self.assertEqual(30, self.player.runtime_state.gold)

    def test_a_pack_holds_eight_bombs_and_nine_keys(self):
        self.give("item_bomb", 8)
        self.assertEqual(8, self.player.inventory.count_item("item_bomb"))
        ok, said = self.player.inventory.add_item(ItemFactory.create_item_from_template("item_bomb", self.world))
        self.assertFalse(ok)
        self.assertIn("cannot carry more than 8", said)
        self.give("item_small_key", 9)
        ok, _said = self.player.inventory.add_item(ItemFactory.create_item_from_template("item_small_key", self.world))
        self.assertFalse(ok)


class TestTheEast(Base):
    def test_the_south_and_the_east_meet_on_the_lake_road(self):
        self.at("ardenmoor_south", "as_1_2")
        self.say("go east")
        self.assertEqual("ardenmoor_east:ae_1_0", self.where())
        self.say("go west")
        self.assertEqual("ardenmoor_south:as_1_2", self.where())

    def test_the_water_past_the_dock_wants_a_raft_and_the_raft_is_not_used_up(self):
        self.at("ardenmoor_east", "ae_1_1")
        self.assertIn("raft", self.say("go east").lower())
        self.assertEqual("ardenmoor_east:ae_1_1", self.where())
        self.give("item_raft")
        self.say("go east")
        self.assertEqual("ardenmoor_east:ae_island", self.where())
        self.assertEqual(1, self.player.inventory.count_item("item_raft"))

    def test_the_island_heart_is_taken_once_and_adds_a_heart(self):
        self.at("ardenmoor_east", "ae_island")
        self.say("take heart container")
        self.assertEqual(4 * HEART, self.player.max_health)
        self.assertEqual(0, self.player.inventory.count_item("item_heart_container"))

    def test_the_pale_blade_wants_five_hearts(self):
        self.at("ardenmoor_east", "waterfall_cave")
        self.player.max_health = 4 * HEART
        self.say("talk old man")
        self.assertEqual(0, self.player.inventory.count_item("item_pale_blade"))
        self.player.max_health = 5 * HEART
        self.say("talk old man")
        self.say("reply 1")
        self.assertEqual("item_pale_blade", self.player.equipment["main_hand"].obj_id)
        self.assertGreaterEqual(self.player.get_attack_power(), 2 * 8 - 1)

    def test_the_shop_sells_bombs_for_twenty_and_will_not_sell_past_a_full_pack(self):
        self.at("ardenmoor_east", "shop_cave")
        self.say("trade old man")
        self.assertIn("20", self.say("list"))
        self.player.runtime_state.gold = 100
        self.give("item_bomb", 8)
        said = self.say("buy bomb")
        self.assertIn("cannot carry", said)
        self.assertEqual(100, self.player.runtime_state.gold)


class TestTheCrescentVault(Base):
    def test_a_sword_and_an_arrow_do_nothing_to_the_stone_jaw_and_a_bomb_does(self):
        self.at("crescent_vault", "v_boss")
        jaw = self.foes("stone_jaw")[0]
        self.assertEqual(40, jaw.health)
        self.assertEqual(0, jaw.take_damage(50, "physical"))
        self.assertEqual(0, jaw.take_damage(50, "missile"))
        self.give("item_bomb", 2)
        self.say("use bomb")
        self.assertLess(jaw.health, jaw.max_health)
        self.say("use bomb")
        self.assertFalse(jaw.is_alive, "two bombs finish it")

    def test_a_great_slime_comes_apart_into_two_slimes(self):
        self.at("crescent_vault", "v_west")
        before = len(self.foes("slime"))
        slime = self.foes("great_slime")[0]
        slime.take_damage(10 ** 5, "physical")
        slime.die(self.world)
        self.assertEqual(before + 2, len(self.foes("slime")))

    def test_the_powder_store_is_behind_a_door_that_waits_for_the_slimes(self):
        self.at("crescent_vault", "v_west")
        self.assertIn("will not lift", self.say("go north"))
        for npc in self.foes("great_slime"):
            self.world.remove_npcs(npc.obj_id)
        self.say("go north")
        self.assertEqual("crescent_vault:v_powder", self.where())

    def test_the_stormwing_is_known_once_taken(self):
        self.at("crescent_vault", "v_worm")
        for npc in self.foes("great_worm"):
            self.world.remove_npcs(npc.obj_id)
        self.say("take stormwing")
        self.assertIn("throw_stormwing", self.player.runtime_state.magic.known_spells)

    def test_the_second_shard_and_a_fifth_heart(self):
        self.at("crescent_vault", "v_boss")
        jaw = self.foes("stone_jaw")[0]
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": jaw})
        self.assertEqual(1, self.player.inventory.count_item("item_shard_2"))
        self.assertEqual(4 * HEART, self.player.max_health)


class TestThePinwheel(Base):
    def test_the_flower_cannot_be_struck_while_a_mouth_remains(self):
        self.at("pinwheel", "l_boss")
        bloom = self.foes("snapjaw_bloom")[0]
        from engine.core.combat_system import CombatSystem

        result = CombatSystem.execute_attack(self.player, bloom, 50, always_hit=True)
        self.assertEqual(bloom.max_health, bloom.health)
        self.assertIn("mouths", result["message"])
        for mouth in self.foes("snapjaw_mouth"):
            mouth.take_damage(10 ** 5, "physical")
        result = CombatSystem.execute_attack(self.player, bloom, 50, always_hit=True)
        self.assertGreater(result["damage"], 0)

    def test_the_raft_is_in_a_room_that_shuts_until_the_slimes_are_down(self):
        self.at("pinwheel", "l_raft")
        self.assertIn("shut", self.say("go south").lower())
        self.assertEqual("pinwheel:l_raft", self.where())

    def test_the_hand_here_takes_you_to_this_dungeons_own_door(self):
        self.at("pinwheel", "l_upper")
        hand = self.foes("grasping_hand")[0]
        from engine.magic.spell_registry import get_spell
        from engine.npcs import combat as npc_combat

        npc_combat.cast_spell(hand, get_spell("hand_grab"), self.player, 1000.0)
        self.assertEqual("pinwheel:l_entrance", self.where())

    def test_the_third_shard_and_a_fifth_heart(self):
        self.at("pinwheel", "l_boss")
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": self.foes("snapjaw_bloom")[0]})
        self.assertEqual(1, self.player.inventory.count_item("item_shard_3"))


class TestTheNorthAndTheLostHills(Base):
    def test_the_lost_hills_take_five_steps_up_and_turn_you_round_for_a_step_aside(self):
        self.at("lost_hills", "h0")
        for _ in range(2):
            self.say("go north")
        self.say("go east")
        self.assertEqual("lost_hills:h0", self.where())
        for _ in range(5):
            self.say("go north")
        self.assertEqual("lost_hills:h5", self.where())
        self.say("go in")
        self.assertEqual("gecko_halls:g_entrance", self.where())

    def test_a_blue_candle_burns_the_bush_away_once_and_the_heart_under_it_is_taken_once(self):
        self.give("item_blue_candle")
        self.at("ardenmoor_north", "an_1_2")
        self.say("go in")
        self.assertEqual("ardenmoor_north:an_1_2", self.where())
        self.assertIn("goes up", self.say("use blue candle"))
        self.assertIn("already burns", self.say("use blue candle"))
        self.say("go in")
        self.say("take heart container")
        self.assertEqual(4 * HEART, self.player.max_health)

    def test_the_reed_pipe_opens_the_pool_and_only_the_pool(self):
        self.give("item_reed_pipe")
        self.at("ardenmoor_north", "an_0_0")
        self.say("use reed pipe")
        self.assertNotIn("in", self.world.get_region("ardenmoor_north").get_room("an_1_1").exits)
        self.at("ardenmoor_north", "an_1_1")
        self.assertIn("stair of wet stone", self.say("use reed pipe"))
        self.say("go in")
        self.assertEqual("ardenmoor_north:fairy_pool", self.where())

    def test_the_fairy_mends_every_wound(self):
        self.at("ardenmoor_north", "fairy_pool")
        self.player.health = 3
        self.say("talk fairy")
        self.say("reply 1")
        self.assertEqual(self.player.max_health, self.player.health)

    def test_the_magical_shield_and_the_bomb_bag_cost_what_the_original_asks(self):
        self.player.runtime_state.gold = 1000
        self.at("ardenmoor_north", "shield_shop")
        self.say("trade old man")
        self.say("buy magical shield")
        self.assertEqual(1000 - 130, self.player.runtime_state.gold)
        self.at("gecko_halls", "g_shop")
        self.say("trade old man")
        self.say("buy bomb bag")
        self.assertEqual(1000 - 130 - 100, self.player.runtime_state.gold)
        self.give("item_bomb", 12)
        self.assertEqual(12, self.player.inventory.count_item("item_bomb"))


class TestTheShieldEater(Base):
    def _devour(self):
        from engine.magic.spell_registry import get_spell
        from engine.npcs import combat as npc_combat

        self.at("wyvern_deep", "w_east")
        eater = self.foes("shield_eater")[0]
        return npc_combat.cast_spell(eater, get_spell("devour_shield"), self.player, 1000.0)

    def test_it_swallows_the_magical_shield_and_the_shield_is_gone(self):
        self.give("item_magic_shield")
        self.say("equip magical shield")
        self.assertEqual("item_magic_shield", self.player.equipment["off_hand"].obj_id)
        result = self._devour()
        self.assertIsNone(self.player.equipment.get("off_hand"))
        self.assertEqual(0, self.player.inventory.count_item("item_magic_shield"))
        self.assertIn("magical shield is gone", result["message"])

    def test_the_small_shield_is_not_to_its_taste_and_nothing_is_said_of_it(self):
        result = self._devour()
        self.assertEqual("item_small_shield", self.player.equipment["off_hand"].obj_id)
        self.assertNotIn("Nothing happens", result["message"])


class TestTheThreeMoreBosses(Base):
    def test_the_hydras_body_waits_for_both_heads(self):
        from engine.core.combat_system import CombatSystem

        self.at("adders_coil", "c_boss")
        body = self.foes("hydra")[0]
        self.assertIn("neck", CombatSystem.execute_attack(self.player, body, 50, always_hit=True)["message"])
        for head in self.foes("hydra_head"):
            head.take_damage(10 ** 5, "physical")
        self.assertGreater(CombatSystem.execute_attack(self.player, body, 50, always_hit=True)["damage"], 0)

    def test_nothing_hurts_the_great_eye_until_the_pipe_makes_it_small(self):
        self.at("gecko_halls", "g_boss")
        eye = self.foes("burrowing_eye_large")[0]
        for kind in ("physical", "missile", "explosive", "fire", "magical"):
            self.assertEqual(0, eye.take_damage(100, kind), kind)
        self.give("item_reed_pipe")
        self.say("use reed pipe")
        self.assertFalse(eye.is_alive)
        small = self.foes("burrowing_eye_small")
        self.assertEqual(1, len(small))
        self.assertGreater(small[0].take_damage(8, "physical"), 0)

    def test_the_small_eye_gives_the_fifth_shard(self):
        self.at("gecko_halls", "g_boss")
        self.give("item_reed_pipe")
        self.say("use reed pipe")
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": self.foes("burrowing_eye_small")[0]})
        self.assertEqual(1, self.player.inventory.count_item("item_shard_5"))

    def test_the_great_claw_takes_only_a_shaft_and_only_through_its_open_eye(self):
        self.at("wyvern_deep", "w_boss")
        claw = self.foes("great_claw")[0]
        self.assertEqual(0, claw.take_damage(100, "physical"))
        self.assertEqual(0, claw.take_damage(100, "explosive"))
        phases = [p["name"] for p in claw.properties["phases"]]
        self.assertEqual(["shut", "open"], phases)
        self.assertTrue(claw.properties["phases"][0]["untouchable"])
        self.assertGreater(claw.take_damage(16, "missile"), 0)

    def test_a_hexer_is_there_and_gone_in_turn(self):
        hexer = self.world.npc_templates["hexer"]["properties"]["phases"]
        self.assertEqual([False, True], [bool(p.get("untouchable")) for p in hexer])

    def test_a_ladder_crosses_the_gap_to_the_far_dock_and_is_not_used_up(self):
        self.at("ardenmoor_east", "ae_far_shore")
        self.assertIn("ladder", self.say("go east").lower())
        self.give("item_ladder")
        self.say("go east")
        self.assertEqual("ardenmoor_east:ae_far_dock", self.where())
        self.assertEqual(1, self.player.inventory.count_item("item_ladder"))


if __name__ == "__main__":
    unittest.main()
