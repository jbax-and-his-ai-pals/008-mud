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
        self.assertEqual(3, len(self.foes("bone_warrior")) - 4, "three archers here beside the guards and the chamber's")
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


if __name__ == "__main__":
    unittest.main()
