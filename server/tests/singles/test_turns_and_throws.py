# tests/singles/test_turns_and_throws.py
"""A creature that throws, a spell that costs the caster its life, a shadow that mirrors the player, and sides that change.

* `throwing`: an NPC with a `target_damage` consumable in its pack may hurl it instead of striking (`properties.throw_chance`).
* `sacrifice`: an ability the caster does not survive (the effects fall first).
* `properties.mirrors_player`: spawned by a story, it is made the player's equal.
* `set_faction`: a companion is let go and turns on the party (or a foe is won over).
"""

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.dialogue.effects import apply_effects
from engine.items.item_factory import ItemFactory
from engine.magic.effects import apply_spell_effect
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.npcs import companions, throwing
from engine.npcs.combat import cast_spell
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from engine.world import factions
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")


class _World(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = ROOM
        self.world.pending_player_notices.clear()

    def npc(self, name, template="goblin_scout", health=100):
        npc = NPCFactory.create_npc_from_template(template, self.world, instance_id=name)
        npc.current_region_id, npc.current_room_id = ROOM
        npc.max_health = npc.health = health
        npc.stats["defense"] = 0
        npc.defense = 0
        self.world.add_npc(npc)
        return npc


class TestThrowing(_World):
    def knife(self, uses=1):
        item = ItemFactory.create_item_from_template("item_potion", self.world)
        item.update_property("effect_type", "target_damage")
        item.update_property("damage_amount", 20)
        item.update_property("damage_type", "physical")
        item.update_property("uses", uses)
        return item

    def thrower(self, name="thrower"):
        npc = self.npc(name)
        npc.inventory.add_item(self.knife())
        return npc

    def test_a_creature_with_a_throwing_item_hurls_it(self):
        npc, foe = self.thrower(), self.npc("target")
        self.assertIsNotNone(throwing.throwable(npc))
        with mock.patch("random.random", return_value=0.0):
            result = throwing.try_throw(npc, foe)
        self.assertIn("hurls", result["message"])
        self.assertLess(foe.health, 100)
        self.assertIsNone(throwing.throwable(npc), "and it is spent")

    def test_the_chance_decides_whether_it_throws_this_turn(self):
        npc, foe = self.thrower("t2"), self.npc("target2")
        npc.properties["throw_chance"] = 0.2
        with mock.patch("random.random", return_value=0.9):
            self.assertIsNone(throwing.try_throw(npc, foe))
        self.assertIsNotNone(throwing.throwable(npc), "kept for another turn")
        self.assertEqual(100, foe.health)

    def test_nothing_to_throw_means_a_plain_blow(self):
        npc, foe = self.npc("t3"), self.npc("target3")
        self.assertIsNone(throwing.try_throw(npc, foe))

    def test_a_healing_item_is_not_a_throwing_one(self):
        npc = self.npc("t4")
        npc.inventory.add_item(ItemFactory.create_item_from_template("item_potion", self.world))
        self.assertIsNone(throwing.throwable(npc))

    def test_try_attack_throws_before_it_strikes(self):
        from engine.npcs.combat import enter_combat, try_attack

        npc = self.thrower("t5")
        enter_combat(npc, self.player)
        npc.last_combat_action = npc.last_attack_time = 0
        with mock.patch("random.random", return_value=0.0):
            told = try_attack(npc, self.world, float(self.world.clock.now()) + 100)
        self.assertIn("hurls", told)


class TestSacrifice(_World):
    def setUp(self):
        super().setUp()
        self.addCleanup(SPELL_REGISTRY.pop, "t_meteor", None)
        SPELL_REGISTRY["t_meteor"] = Spell("t_meteor", "Meteor", "All of it.", effects=[{"type": "damage", "value": 60, "damage_type": "fire"}],
                                           mana_cost=0, target_type="enemy", sacrifice=True)

    def test_the_effects_fall_and_then_the_caster_does_not_survive(self):
        caster, foe = self.npc("sage"), self.npc("victim")
        caster.combat_targets.add(foe)   # at war with it, so the cast is aimed at it
        told = cast_spell(caster, SPELL_REGISTRY["t_meteor"], foe, 1000.0)["message"]
        self.assertLess(foe.health, 100)
        self.assertFalse(caster.is_alive)
        self.assertIn("gives everything", told)

    def test_an_ordinary_ability_does_not(self):
        caster, foe = self.npc("sage2"), self.npc("victim2")
        caster.combat_targets.add(foe)
        SPELL_REGISTRY["t_meteor"].sacrifice = False
        cast_spell(caster, SPELL_REGISTRY["t_meteor"], foe, 1000.0)
        self.assertTrue(caster.is_alive)


class TestMirror(_World):
    def test_a_mirror_takes_the_players_measure(self):
        self.player.max_health = 123
        self.player.health = 123
        data = {"template": "goblin_scout"}
        self.world.npc_templates["goblin_scout"].setdefault("properties", {})["mirrors_player"] = True
        self.addCleanup(self.world.npc_templates["goblin_scout"]["properties"].pop, "mirrors_player", None)
        apply_effects({"spawn_npc": {"npc": "goblin_scout", "region": "hazevale", "room": "village_square", "instance_id": "shadow"}},
                      {"player": self.player, "world": self.world})
        shadow = self.world.npcs["shadow"]
        self.assertEqual(123, shadow.max_health)
        self.assertEqual(123, shadow.health)
        self.assertEqual(self.player.get_attack_power(), shadow.attack_power)
        self.assertEqual(self.player.get_defense(), shadow.defense)

    def test_without_the_property_it_is_as_authored(self):
        apply_effects({"spawn_npc": {"npc": "goblin_scout", "region": "hazevale", "room": "village_square", "instance_id": "plain"}},
                      {"player": self.player, "world": self.world})
        self.assertNotEqual(self.player.max_health, self.world.npcs["plain"].max_health)


class TestSetFaction(_World):
    def test_a_companion_is_let_go_and_turns_hostile(self):
        friend = self.npc("friend", template="ryn")
        companions.recruit(self.world, self.player, friend)
        self.assertTrue(companions.is_companion(friend))
        apply_effects({"set_faction": {"npc": "friend", "faction": "hostile", "behavior": "aggressive"}}, {"player": self.player, "world": self.world})
        self.assertFalse(companions.is_companion(friend))
        self.assertEqual("hostile", friend.faction)
        self.assertEqual("aggressive", friend.behavior_type)
        self.assertTrue(factions.is_hostile(friend, self.world))

    def test_a_foe_is_won_over(self):
        foe = self.npc("foe")
        self.assertTrue(factions.is_hostile(foe, self.world))
        apply_effects({"set_faction": {"npc": "goblin_scout", "faction": "friendly"}}, {"player": self.player, "world": self.world})
        self.assertFalse(factions.is_hostile(foe, self.world))

    def test_an_unknown_npc_is_reported_not_raised(self):
        report = apply_effects({"set_faction": {"npc": "nobody", "faction": "hostile"}}, {"player": self.player, "world": self.world})
        self.assertTrue(report.failed)


class TestTheValidator(unittest.TestCase):
    def errors(self, mutate):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        mutate(pkg)
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def npc_props(self, **props):
        def mutate(pkg):
            path = pkg / "data" / "npcs" / "hostiles.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["goblin_scout"].setdefault("properties", {}).update(props)
            path.write_text(json.dumps(data), encoding="utf-8")
        return mutate

    def test_the_npc_properties(self):
        self.assertEqual([], [m for m in self.errors(self.npc_props(mirrors_player=True, throw_chance=0.3)) if "goblin_scout" in m])
        for bad in ({"mirrors_player": "yes"}, {"throw_chance": 2}, {"throw_chance": "often"}):
            self.assertTrue([m for m in self.errors(self.npc_props(**bad)) if "goblin_scout" in m], bad)

    def test_sacrifice_must_be_a_bool(self):
        def mutate(pkg):
            (pkg / "data" / "magic" / "probe.json").write_text(json.dumps({"probe": {
                "name": "Probe", "description": "x", "mana_cost": 0, "cooldown": 1, "target_type": "enemy", "sacrifice": "yes",
                "effects": [{"type": "damage", "value": 5, "damage_type": "physical"}]}}), encoding="utf-8")
        self.assertTrue([m for m in self.errors(mutate) if "sacrifice must be true or false" in m])

    def test_set_faction_must_name_an_npc_the_set_has(self):
        def mutate(pkg):
            folder = pkg / "data" / "scenes"
            folder.mkdir(exist_ok=True)
            (folder / "turn.json").write_text(json.dumps({"turn": {"beats": [{"text": "x", "effects": {"set_faction": {"npc": "nobody_at_all", "faction": "hostile"}}}]}}), encoding="utf-8")
        self.assertTrue([m for m in self.errors(mutate) if "set_faction names npc 'nobody_at_all'" in m])


if __name__ == "__main__":
    unittest.main()
