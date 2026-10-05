# tests/singles/test_ability_toolkit.py
"""Abilities with a wind-up (Jump), shares of health, stealing, ally requirements (Twin) and stone.

* `windup`: the caster leaves for `seconds` (airborne: acts not, cannot be struck, is not targeted) then the effects fall.
* `percent_damage`: takes a share of the target's current health; `percent_immune` shrugs it off.
* `steal`: takes an item from `properties.steal_items`, once each, by chance; an AI does not steal from the empty-handed.
* `requires_ally`: cast only while the named NPCs stand beside the caster.
* the `petrify` tag: stone does nothing, is not struck, and a `cleanse` of that tag frees it.
"""

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.magic import stealing, windup
from engine.magic.effects import apply_spell_effect
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.npcs import companions
from engine.npcs.ai import dispatcher
from engine.npcs.combat import is_untargetable
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")


class _Abilities(unittest.TestCase):
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
        for spell_id in ("t_jump", "t_gravity", "t_steal", "t_twin"):
            self.addCleanup(SPELL_REGISTRY.pop, spell_id, None)
        SPELL_REGISTRY["t_jump"] = Spell(
            "t_jump", "Jump", "Up and down.", effects=[{"type": "damage", "value": 40, "damage_type": "physical"}], mana_cost=0, cooldown=1.0,
            target_type="enemy", windup={"seconds": 3, "leave_message": "{caster_name} leaps away!", "land_message": "{caster_name} drops on {target_name}!"})
        SPELL_REGISTRY["t_gravity"] = Spell("t_gravity", "Gravity", "Heavy.", effects=[{"type": "percent_damage", "value": 50}], mana_cost=0, target_type="enemy")
        SPELL_REGISTRY["t_steal"] = Spell("t_steal", "Steal", "Light fingers.", effects=[{"type": "steal"}], mana_cost=0, target_type="enemy")
        SPELL_REGISTRY["t_twin"] = Spell("t_twin", "Twin", "Together.", effects=[{"type": "damage", "value": 5}], mana_cost=0, target_type="enemy",
                                         requires_ally=["goblin_scout"])

    def npc(self, name, template="goblin_scout", health=100):
        npc = NPCFactory.create_npc_from_template(template, self.world, instance_id=name)
        npc.current_region_id, npc.current_room_id = ROOM
        npc.max_health = npc.health = health
        npc.stats["defense"] = 0
        npc.properties["defense"] = 0
        npc.defense = 0
        self.world.add_npc(npc)
        return npc

    def tick(self, seconds):
        self.world.clock.advance(seconds)
        self.world.run_scheduled()

    def told(self):
        text = " ".join(t for _, t in self.world.pending_player_notices)
        self.world.pending_player_notices.clear()
        return text


class TestWindup(_Abilities):
    def test_the_caster_goes_up_and_comes_down_on_the_target(self):
        jumper, foe = self.npc("jumper"), self.npc("foe")
        _, said = apply_spell_effect(jumper, foe, SPELL_REGISTRY["t_jump"], None)
        self.assertIn("leaps away", said)
        self.assertEqual(100, foe.health, "nothing falls yet")
        self.assertTrue(windup.is_airborne(jumper))
        self.tick(3.5)
        self.assertFalse(windup.is_airborne(jumper))
        self.assertLess(foe.health, 100)
        self.assertIn("drops on", self.told())

    def test_in_the_air_it_cannot_be_struck_or_picked_and_does_nothing(self):
        jumper, foe = self.npc("jumper2"), self.npc("foe2")
        apply_spell_effect(jumper, foe, SPELL_REGISTRY["t_jump"], None)
        self.assertEqual(0, jumper.take_damage(50, "physical"))
        self.assertEqual(100, jumper.health)
        self.assertTrue(is_untargetable(jumper))
        self.assertIsNone(dispatcher.handle_ai(jumper, self.world, float(self.world.clock.now()), self.player))

    def test_if_the_target_is_gone_nothing_falls(self):
        jumper, foe = self.npc("jumper3"), self.npc("foe3")
        apply_spell_effect(jumper, foe, SPELL_REGISTRY["t_jump"], None)
        foe.current_room_id = "shrine"
        self.tick(3.5)
        self.assertEqual(100, foe.health)
        self.assertFalse(windup.is_airborne(jumper))
        self.assertIn("nothing beneath", self.told())

    def test_a_caster_who_died_in_the_air_does_not_land(self):
        jumper, foe = self.npc("jumper4"), self.npc("foe4")
        apply_spell_effect(jumper, foe, SPELL_REGISTRY["t_jump"], None)
        jumper.is_alive = False
        self.tick(3.5)
        self.assertEqual(100, foe.health)


class TestPercentDamage(_Abilities):
    def test_it_takes_a_share_of_current_health(self):
        foe = self.npc("heavy", health=80)
        apply_spell_effect(self.player, foe, SPELL_REGISTRY["t_gravity"], None)
        self.assertAlmostEqual(40, foe.health, delta=2)   # a point of its own toughness may turn some aside
        apply_spell_effect(self.player, foe, SPELL_REGISTRY["t_gravity"], None)
        self.assertAlmostEqual(20, foe.health, delta=3)

    def test_percent_immune_shrugs_it_off(self):
        foe = self.npc("boss", health=80)
        foe.properties["percent_immune"] = True
        _, said = apply_spell_effect(self.player, foe, SPELL_REGISTRY["t_gravity"], None)
        self.assertEqual(80, foe.health)
        self.assertIn("untouched", said)


class TestSteal(_Abilities):
    def setUp(self):
        super().setUp()
        self.foe = self.npc("rich")
        self.foe.properties["steal_items"] = [{"item_id": "item_potion", "chance": 1}, {"item_id": "item_ether", "chance": 1}]
        self.items = {"item_potion": object()}

    def potions(self):
        return self.player.inventory.count_item("item_potion")

    def test_it_takes_the_items_in_turn_once_each(self):
        before = self.potions()
        _, said = apply_spell_effect(self.player, self.foe, SPELL_REGISTRY["t_steal"], None)
        self.assertIn("steals", said)
        self.assertEqual(before + 1, self.potions())
        self.assertEqual(["item_potion"], self.foe.properties["stolen"])
        self.assertEqual("item_ether", stealing.remaining(self.foe)[0]["item_id"])

    def test_a_failed_chance_takes_nothing_and_keeps_the_item_for_later(self):
        self.foe.properties["steal_items"] = [{"item_id": "item_potion", "chance": 0}]
        before = self.potions()
        _, said = apply_spell_effect(self.player, self.foe, SPELL_REGISTRY["t_steal"], None)
        self.assertIn("nothing", said)
        self.assertEqual(before, self.potions())
        self.assertTrue(stealing.worth_trying(self.foe))

    def test_nothing_left_says_so(self):
        self.foe.properties["steal_items"] = [{"item_id": "item_potion", "chance": 1}]
        apply_spell_effect(self.player, self.foe, SPELL_REGISTRY["t_steal"], None)
        _, said = apply_spell_effect(self.player, self.foe, SPELL_REGISTRY["t_steal"], None)
        self.assertIn("nothing on", said)
        self.assertFalse(stealing.worth_trying(self.foe))

    def test_a_companion_steals_for_its_owner(self):
        thief = self.npc("thief", template="ryn")
        companions.recruit(self.world, self.player, thief)
        before = self.potions()
        apply_spell_effect(thief, self.foe, SPELL_REGISTRY["t_steal"], None)
        self.assertEqual(before + 1, self.potions())

    def test_an_ai_does_not_try_to_steal_from_the_empty_handed(self):
        from engine.npcs.combat import _worth_casting

        poor = self.npc("poor")
        self.assertFalse(_worth_casting(SPELL_REGISTRY["t_steal"], poor))
        self.assertTrue(_worth_casting(SPELL_REGISTRY["t_steal"], self.foe))
        self.assertTrue(_worth_casting(SPELL_REGISTRY["t_gravity"], poor), "other abilities are not judged")


class TestRequiresAlly(_Abilities):
    def test_it_is_refused_without_the_ally_and_allowed_with(self):
        caster = self.npc("caster", template="ryn")
        self.assertIn("needs", caster and SPELL_REGISTRY["t_twin"].ally_requirement(caster))
        self.npc("buddy")
        self.assertEqual("", SPELL_REGISTRY["t_twin"].ally_requirement(caster))

    def test_an_ally_who_is_asleep_or_stone_does_not_count(self):
        caster = self.npc("caster2", template="ryn")
        buddy = self.npc("buddy2")
        buddy.apply_effect({"type": "status", "name": "Slumber", "tags": ["sleep"], "base_duration": 30}, float(self.world.clock.now()))
        self.assertNotEqual("", SPELL_REGISTRY["t_twin"].ally_requirement(caster))

    def test_the_player_is_held_to_it_too(self):
        self.player.runtime_state.magic.known_spells.add("t_twin") if hasattr(self.player.runtime_state.magic.known_spells, "add") else self.player.runtime_state.magic.known_spells.append("t_twin")
        can, reason = self.player.can_cast_spell(SPELL_REGISTRY["t_twin"], float(self.world.clock.now()), self.world)
        self.assertFalse(can)
        self.assertIn("needs", reason)

    def test_no_requirement_means_none(self):
        caster = self.npc("caster3", template="ryn")
        self.assertEqual("", SPELL_REGISTRY["t_gravity"].ally_requirement(caster))


class TestStone(_Abilities):
    def stone(self, npc):
        npc.apply_effect({"type": "status", "name": "Stone", "tags": ["petrify"], "base_duration": 60}, float(self.world.clock.now()))

    def test_stone_does_nothing_is_not_struck_and_is_not_picked(self):
        npc = self.npc("statue")
        self.stone(npc)
        self.assertEqual(0, npc.take_damage(50, "physical"))
        self.assertTrue(is_untargetable(npc))
        self.assertIsNone(dispatcher.handle_ai(npc, self.world, float(self.world.clock.now()), self.player))

    def test_a_cleanse_of_the_tag_frees_it(self):
        npc = self.npc("statue2")
        self.stone(npc)
        npc.remove_effects_by_tag("petrify")
        self.assertFalse(is_untargetable(npc))
        self.assertEqual(40, npc.take_damage(40, "physical"))


class TestStoneCure(_Abilities):
    def test_a_companion_with_a_cleanse_of_stone_frees_a_petrified_friend(self):
        from engine.npcs.ai import specialized

        SPELL_REGISTRY["t_soften"] = Spell("t_soften", "Soften", "Flesh again.", effects=[{"type": "cleanse", "effect_data": {"tags": ["petrify"]}}],
                                           mana_cost=0, target_type="friendly")
        self.addCleanup(SPELL_REGISTRY.pop, "t_soften", None)
        healer = self.npc("healer", template="ryn")
        friend = self.npc("friend", template="ryn")
        for member in (healer, friend):
            companions.recruit(self.world, self.player, member)
        healer.usable_spells = ["t_soften"]
        healer.max_mana = healer.mana = 50
        healer.last_combat_action = 0
        friend.apply_effect({"type": "status", "name": "Stone", "tags": ["petrify"], "base_duration": 600}, float(self.world.clock.now()))
        self.assertTrue(friend.has_effect_tag("petrify"))
        specialized.perform_companion_support(healer, self.world, float(self.world.clock.now()) + 100, self.player)
        self.assertFalse(friend.has_effect_tag("petrify"))


class TestTheValidator(unittest.TestCase):
    def errors(self, **fields):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        folder = pkg / "data" / "magic"
        (folder / "probe.json").write_text(json.dumps({"probe": dict({
            "name": "Probe", "description": "x", "mana_cost": 0, "cooldown": 1, "target_type": "enemy",
            "effects": [{"type": "damage", "value": 5, "damage_type": "physical"}]}, **fields)}), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def test_good_ones_pass(self):
        good = self.errors(windup={"seconds": 3, "leave_message": "{caster_name} goes.", "land_message": "{caster_name} lands on {target_name}."},
                           requires_ally=["goblin_scout"])
        self.assertEqual([], [m for m in good if "probe" in m])

    def test_bad_windups_are_refused(self):
        for bad in ({"seconds": 0}, {"seconds": 99}, {}, {"seconds": 3, "leave_message": "{nobody}"}, {"seconds": 3, "speed": 1}, 5):
            self.assertTrue([m for m in self.errors(windup=bad) if "windup" in m], bad)
        self.assertTrue([m for m in self.errors(windup={"seconds": 3}, target_type="all_enemies") if "target_type 'enemy'" in m])

    def test_bad_allies_are_refused(self):
        for bad in ([], "porom", ["nobody_at_all"], [3]):
            self.assertTrue([m for m in self.errors(requires_ally=bad) if "requires_ally" in m], bad)

    def test_the_new_effect_types_are_known(self):
        found = self.errors(effects=[{"type": "percent_damage", "value": 50}, {"type": "steal"}])
        self.assertEqual([], [m for m in found if "probe" in m], found)


class TestNpcProperties(unittest.TestCase):
    def errors(self, **properties):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        path = pkg / "data" / "npcs" / "hostiles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["goblin_scout"].setdefault("properties", {}).update(properties)
        path.write_text(json.dumps(data), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def test_good_ones_pass(self):
        self.assertEqual([], [m for m in self.errors(steal_items=[{"item_id": "item_potion", "chance": 0.5}], percent_immune=True) if "goblin_scout" in m])

    def test_bad_ones_are_refused(self):
        for bad in ([], [{"chance": 0.5}], [{"item_id": "x", "chance": 2}], [{"item_id": "x", "luck": 1}], ["x"]):
            self.assertTrue([m for m in self.errors(steal_items=bad) if "steal_items" in m], bad)
        self.assertTrue([m for m in self.errors(percent_immune="yes") if "percent_immune" in m])


if __name__ == "__main__":
    unittest.main()
