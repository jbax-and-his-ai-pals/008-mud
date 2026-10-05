# tests/singles/test_bard_toolkit.py
"""What a support character needs: status songs, harps that carry them, and a way to keep out of harm.

* `sleep`, `silence` and `confuse` (effect tags): a sleeper does nothing and wakes when struck; a silenced creature does not
  cast; a confused one strikes at whoever is nearest.
* An NPC can cast an `all_enemies` ability at every enemy in the room at once.
* An item's `grants_spells` gives a companion who holds it those abilities, and taking it off takes them away.
* `hides_when_hurt` on a companion: it ducks out of the fight in the room, cannot be hit, and comes out when the fight is over.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.npcs import companion_gear, companions
from engine.npcs import combat as npc_combat
from engine.npcs.ai import combat_logic, dispatcher
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE


def _song(name, tag, message):
    return {"name": name, "description": "A song.", "mana_cost": 0, "cooldown": 1, "target_type": "all_enemies",
            "cast_message": "{caster_name} sings.", "hit_message": "x", "level_required": 1,
            "effects": [{"type": "apply_effect", "base_duration": 12, "effect_data": {"name": message, "type": "status", "tags": [tag]}}]}


SONGS = {"lullaby": _song("Lullaby", "sleep", "Sleep"), "hush": _song("Hush", "silence", "Silenced"), "discord": _song("Discord", "confuse", "Confused")}
HARP = {"item_test_harp": {"type": "Weapon", "name": "test harp", "description": "A harp.", "weight": 2, "value": 10, "stackable": False,
                           "properties": {"damage": 2, "weapon_damage_type": "crushing", "durability": 50, "max_durability": 50,
                                          "equip_slot": ["main_hand"], "grants_spells": ["lullaby", "hush"]}, "item_family": "weapon"}}
BARD = {"test_bard": {"name": "Test Bard", "description": "x", "max_health": 100, "level": 3, "friendly": True, "faction": "friendly",
                      "behavior_type": "stationary", "max_mana": 100, "usable_spells": ["discord"],
                      "properties": {"wander_chance": 0, "move_cooldown": 9999, "hides_when_hurt": True, "flee_threshold": 0.4,
                                     "rejoin_health": 0.8, "spell_cast_chance": 1}}}


def make_package(extra_items=None):
    tmp = Path(tempfile.mkdtemp())
    package = tmp / "story_fixture"
    shutil.copytree(STORY_FIXTURE, package)
    (package / "data" / "magic" / "songs.json").write_text(json.dumps(SONGS), encoding="utf-8")
    items = dict(HARP)
    items.update(extra_items or {})
    (package / "data" / "items" / "harps.json").write_text(json.dumps(items), encoding="utf-8")
    (package / "data" / "npcs" / "bards.json").write_text(json.dumps(BARD), encoding="utf-8")
    return tmp, package


class _World(unittest.TestCase):
    def setUp(self):
        tmp, package = make_package()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "hazevale", "village_square"
        self.now = self.world.clock.now()

    def spawn(self, template, ident):
        npc = NPCFactory.create_npc_from_template(template, self.world, instance_id=ident)
        npc.current_region_id, npc.current_room_id = "hazevale", "village_square"
        self.world.add_npc(npc)
        return npc

    def foe(self, ident="foe"):
        foe = self.spawn("goblin_scout", ident)
        foe.max_health = foe.health = 10 ** 6
        return foe

    def bard(self):
        bard = self.spawn("test_bard", "the_bard")
        companions.recruit(self.world, self.player, bard)
        return bard


class TestStatuses(_World):
    def test_a_sleeper_does_nothing_and_wakes_when_struck(self):
        foe = self.foe()
        npc_combat.enter_combat(foe, self.player)
        foe.apply_effect({"name": "Sleep", "type": "status", "tags": ["sleep"], "base_duration": 30}, self.now)
        self.assertIsNone(dispatcher.handle_ai(foe, self.world, self.now + 10, self.player), "asleep: no action")
        self.assertTrue(foe.has_effect_tag("sleep"))
        foe.take_damage(40, "physical")
        self.assertFalse(foe.has_effect_tag("sleep"), "struck, it wakes")

    def test_a_sleeper_is_not_woken_by_nothing(self):
        foe = self.foe()
        foe.apply_effect({"name": "Sleep", "type": "status", "tags": ["sleep"], "base_duration": 30}, self.now)
        foe.take_damage(0, "physical")
        self.assertTrue(foe.has_effect_tag("sleep"))

    def test_a_silenced_creature_does_not_cast(self):
        caster = self.spawn("cave_bat", "bat")
        caster.max_health = caster.health = 10 ** 6
        caster.spell_cast_chance = 1.0
        caster.max_mana = caster.mana = 100
        npc_combat.enter_combat(caster, self.player)
        cast = lambda: any("screech" in (npc_combat.try_attack(caster, self.world, self.now + 100 * i) or "").lower() for i in range(1, 12))
        caster.apply_effect({"name": "Silenced", "type": "status", "tags": ["silence"], "base_duration": 999}, self.now)
        self.assertFalse(cast(), "silenced, it only strikes")

    def test_a_confused_creature_strikes_whoever_is_nearest_friend_or_foe(self):
        a, b = self.foe("a"), self.foe("b")
        for foe in (a, b):
            npc_combat.enter_combat(foe, self.player)
        a.apply_effect({"name": "Confused", "type": "status", "tags": ["confuse"], "base_duration": 999}, self.now)
        hit_friend = False
        for i in range(1, 60):
            a.combat_target = self.player
            a.last_combat_action = a.last_attack_time = -1e9
            npc_combat.try_attack(a, self.world, self.now + 100 * i)
            hit_friend = hit_friend or b.health < b.max_health
        self.assertTrue(hit_friend, "a confused goblin hit its own side")


class TestSongsAndHarps(_World):
    def test_an_npc_can_cast_an_all_enemies_ability_on_every_enemy_in_the_room(self):
        foes = [self.foe("f1"), self.foe("f2"), self.foe("f3")]
        bard = self.bard()
        for foe in foes:
            npc_combat.enter_combat(foe, bard)
        bard.combat_target = foes[0]
        bard.last_combat_action = -1e9
        from engine.magic.spell_registry import get_spell

        told = npc_combat.cast_spell(bard, get_spell("discord"), foes[0], self.now + 100)
        self.assertIn("sings", told["message"])
        self.assertEqual([True, True, True], [f.has_effect_tag("confuse") for f in foes])

    def test_a_harp_gives_its_songs_to_whoever_holds_it_and_takes_them_away_when_put_down(self):
        bard = self.bard()
        self.assertEqual(["discord"], bard.usable_spells)
        harp = ItemFactory.create_item_from_template("item_test_harp", self.world)
        bard.equipment["main_hand"] = harp
        companion_gear.refresh(bard)
        self.assertEqual(["discord", "lullaby", "hush"], bard.usable_spells)
        bard.equipment["main_hand"] = None
        companion_gear.refresh(bard)
        self.assertEqual(["discord"], bard.usable_spells, "the songs went with the harp; what he knew stays")

    def test_a_song_a_companion_already_knew_is_not_taken_with_the_harp(self):
        bard = self.bard()
        bard.usable_spells.append("lullaby")
        harp = ItemFactory.create_item_from_template("item_test_harp", self.world)
        bard.equipment["main_hand"] = harp
        companion_gear.refresh(bard)
        bard.equipment["main_hand"] = None
        companion_gear.refresh(bard)
        self.assertIn("lullaby", bard.usable_spells)


class TestHidingWhenHurt(_World):
    def test_a_hurt_companion_hides_in_the_room_cannot_be_hit_and_comes_out_when_it_is_over(self):
        bard = self.bard()
        foe = self.foe()
        npc_combat.enter_combat(foe, self.player)
        npc_combat.enter_combat(bard, foe)
        bard.health = int(bard.max_health * 0.3)
        told = combat_logic.try_flee(bard, self.world, self.player)
        self.assertIn("hides", told)
        self.assertTrue(companions.is_hidden(bard))
        self.assertEqual(("hazevale", "village_square"), (bard.current_region_id, bard.current_room_id), "he did not leave the room")
        self.assertEqual(0, bard.take_damage(100, "physical"))
        self.assertTrue(npc_combat.is_untargetable(bard) and npc_combat.is_pacifist(bard))
        npc_combat.exit_combat(foe)
        self.player.runtime_state.combat.in_combat = False
        stepped = dispatcher.handle_ai(bard, self.world, self.now + 10, self.player)
        self.assertIn("steps out", stepped or "")
        self.assertFalse(companions.is_hidden(bard))

    def test_he_stays_hidden_while_the_fight_goes_on_and_he_is_hurt(self):
        bard = self.bard()
        foe = self.foe()
        npc_combat.enter_combat(foe, self.player)
        bard.health = int(bard.max_health * 0.3)
        combat_logic.try_flee(bard, self.world, self.player)
        self.assertIsNone(dispatcher.handle_ai(bard, self.world, self.now + 10, self.player))
        self.assertTrue(companions.is_hidden(bard))

    def test_once_tended_he_comes_out_even_in_the_fight(self):
        bard = self.bard()
        foe = self.foe()
        npc_combat.enter_combat(foe, self.player)
        bard.health = int(bard.max_health * 0.3)
        combat_logic.try_flee(bard, self.world, self.player)
        bard.health = int(bard.max_health * 0.9)
        self.assertIn("steps out", dispatcher.handle_ai(bard, self.world, self.now + 10, self.player) or "")

    def test_the_party_list_says_he_is_hiding(self):
        bard = self.bard()
        npc_combat.enter_combat(bard, self.foe())
        bard.health = int(bard.max_health * 0.3)
        combat_logic.try_flee(bard, self.world, self.player)
        self.assertIn("hiding", "\n".join(companions.party_lines(self.world, self.player)))


class TestTheValidator(unittest.TestCase):
    def problems(self, items=None, npcs=None):
        tmp, package = make_package(items)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        if npcs:
            (package / "data" / "npcs" / "bards.json").write_text(json.dumps(npcs), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(package) if i.severity == "error"]

    def test_a_good_harp_and_bard_are_accepted(self):
        self.assertEqual([], [m for m in self.problems() if "grants_spells" in m or "hides_when_hurt" in m])

    def test_what_a_harp_may_grant_is_checked(self):
        bad = {"item_bad_harp": {"type": "Weapon", "name": "bad harp", "description": "x", "weight": 1, "value": 1, "stackable": False,
                                 "properties": {"damage": 1, "weapon_damage_type": "crushing", "equip_slot": ["main_hand"], "grants_spells": ["no_such_song"]},
                                 "item_family": "weapon"}}
        self.assertTrue([m for m in self.problems(bad) if "no_such_song" in m])
        bad["item_bad_harp"]["properties"]["grants_spells"] = "lullaby"
        self.assertTrue([m for m in self.problems(bad) if "grants_spells must be" in m])

    def test_hides_when_hurt_must_be_true_or_false(self):
        npcs = json.loads(json.dumps(BARD))
        npcs["test_bard"]["properties"]["hides_when_hurt"] = "yes"
        self.assertTrue([m for m in self.problems(npcs=npcs) if "hides_when_hurt" in m])


if __name__ == "__main__":
    unittest.main()
