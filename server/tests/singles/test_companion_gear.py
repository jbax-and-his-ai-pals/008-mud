# tests/singles/test_companion_gear.py
"""A companion has a sheet, wears gear and can be cared for.

`companion <name>` shows level, health, attack, defence, stats, abilities and gear. `equip <item> on <name>` puts an
item from the player's pack on a companion (and `unequip <slot or item> from <name>` takes it back); a weapon in the main
hand and armour change their attack and defence, and a worn weapon sets the type of blow. `use <potion> on <name>` heals
them. A template may name what an NPC starts in (`equipment`); a saved NPC brings back what it wore.
"""

import re
import unittest

from engine.config import EQUIPMENT_SLOTS
from engine.items.item_factory import ItemFactory
from engine.npcs import companion_gear, companions
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set as validator
from tests.fixtures import GameTestBase

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class _WithCompanion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.companion = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="the_companion")
        self.world.add_npc(self.companion)
        self.companion.current_region_id = self.player.current_region_id
        self.companion.current_room_id = self.player.current_room_id
        self.companion.properties.pop("essential", None)
        self.companion.name = "Brannoc"   # the room's own elder shares the template's name
        joined, _ = companions.recruit(self.world, self.player, self.companion)
        self.assertTrue(joined)
        self.base_attack, self.base_defense = self.companion.attack_power, self.companion.stats["defense"]

    def give(self, item_id):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.player.inventory.add_item(item, 1)
        return item

    def say(self, command):
        return _MARKUP.sub("", self.game.process_command(command))


class TestTheSheet(_WithCompanion):
    def test_it_shows_who_they_are_and_what_they_wear(self):
        text = self.say("companion %s" % self.companion.name)
        self.assertIn(self.companion.name, text)
        self.assertIn("level %d" % self.companion.level, text)
        self.assertIn("Health: %d/%d" % (self.companion.health, self.companion.max_health), text)
        self.assertIn("Attack: %d" % self.companion.attack_power, text)
        self.assertIn("Defense:", text)
        self.assertIn("Stats:", text)
        for slot in EQUIPMENT_SLOTS:
            self.assertIn("%s: (nothing)" % companion_gear.slot_label(slot).capitalize(), text)

    def test_a_name_that_is_nobody_s_companion_is_refused(self):
        self.assertIn("None of your companions is called 'nobody'", self.say("companions nobody"))

    def test_the_list_still_works_without_a_name(self):
        self.assertIn("Travelling with you (1 of 1)", self.say("companions"))


class TestWearingGear(_WithCompanion):
    def test_a_weapon_adds_its_damage_and_taking_it_off_takes_it_away_exactly(self):
        sword = self.give("item_iron_sword")
        said = self.say("equip iron sword on %s" % self.companion.name)
        self.assertIn("equips", said)
        self.assertIsNone(self.player.inventory.get_item(sword.obj_id), "it left the pack")
        self.assertIs(self.companion.equipment["main_hand"], sword)
        self.assertEqual(self.base_attack + 8, self.companion.attack_power)
        self.assertEqual("slashing", companion_gear.weapon_type_of(self.companion), "and sets the type of blow")
        self.assertIn("Main hand: iron sword", self.say("companion %s" % self.companion.name))
        said = self.say("unequip main hand from %s" % self.companion.name)
        self.assertIn("hands you", said)
        self.assertIsNotNone(self.player.inventory.get_item(sword.obj_id), "it came back to the pack")
        self.assertEqual(self.base_attack, self.companion.attack_power, "and the number is exactly what it was")
        self.assertIsNone(companion_gear.weapon_type_of(self.companion))

    def test_armour_adds_defence_where_damage_reads_it(self):
        tunic = self.give("item_leather_tunic")
        self.say("equip leather tunic on %s" % self.companion.name)
        added = self.companion.stats["defense"] - self.base_defense
        self.assertGreater(added, 0)
        self.assertEqual(self.base_defense + added, self.companion.defense)
        self.say("unequip leather tunic from %s" % self.companion.name)
        self.assertEqual(self.base_defense, self.companion.stats["defense"])
        self.assertIsNotNone(self.player.inventory.get_item(tunic.obj_id))

    def test_wearing_in_an_occupied_slot_hands_the_old_item_back(self):
        first = self.give("item_iron_sword")
        self.say("equip iron sword on %s" % self.companion.name)
        second = self.give("item_rusty_sword")
        said = self.say("equip rusty sword on %s" % self.companion.name)
        self.assertIn("returns", said)
        self.assertIs(self.companion.equipment["main_hand"], second)
        self.assertIsNotNone(self.player.inventory.get_item(first.obj_id))

    def test_a_slot_the_item_does_not_fit_is_refused_and_nothing_moves(self):
        sword = self.give("item_iron_sword")
        said = self.say("equip iron sword on %s to head" % self.companion.name)
        self.assertIn("cannot go in", said)
        self.assertIsNotNone(self.player.inventory.get_item(sword.obj_id))
        self.assertEqual(self.base_attack, self.companion.attack_power)

    def test_gear_is_for_your_own_companions_in_the_room(self):
        self.give("item_iron_sword")
        stranger = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="stranger")
        self.world.add_npc(stranger)
        stranger.current_region_id, stranger.current_room_id = self.player.current_region_id, self.player.current_room_id
        self.assertNotIn("equips", self.say("equip iron sword on goblin"), "not a companion")
        self.companion.current_room_id = next(r for r in self.world.get_region(self.player.current_region_id).rooms if r != self.player.current_room_id)
        self.assertIn("is not here", self.say("equip iron sword on %s" % self.companion.name))

    def test_an_item_with_on_in_its_name_is_still_equipped_normally(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        item.name = "stone on a stick"
        self.player.inventory.add_item(item, 1)
        self.assertIn("You equip", self.say("equip stone on a stick"))


class TestCareAndPersistence(_WithCompanion):
    def test_a_potion_heals_a_companion_and_is_used_up(self):
        potion = self.give("item_healing_potion_small")
        self.companion.health = 1
        said = self.say("use healing potion on %s" % self.companion.name)
        self.assertIn("who regains", said)
        self.assertGreater(self.companion.health, 1)
        self.assertIsNone(self.player.inventory.get_item(potion.obj_id))

    def test_a_potion_is_kept_when_the_companion_is_already_well(self):
        potion = self.give("item_healing_potion_small")
        said = self.say("use healing potion on %s" % self.companion.name)
        self.assertIn("no difference", said)
        self.assertIsNotNone(self.player.inventory.get_item(potion.obj_id))

    def test_what_they_wear_is_saved_and_comes_back_without_doubling(self):
        self.give("item_iron_sword")
        self.give("item_leather_tunic")
        self.say("equip iron sword on %s" % self.companion.name)
        self.say("equip leather tunic on %s" % self.companion.name)
        attack, defense = self.companion.attack_power, self.companion.stats["defense"]
        saved = self.companion.to_dict()
        self.assertEqual({"main_hand", "body"}, set(saved["equipment"]))
        again = NPCFactory.create_npc_from_template(
            "village_elder", self.world, instance_id="restored", **{k: v for k, v in saved.items() if k not in ("template_id", "obj_id")})
        self.assertEqual({"main_hand", "body"}, {slot for slot, item in again.equipment.items() if item})
        self.assertEqual((attack, defense), (again.attack_power, again.stats["defense"]), "the same totals, not the gear counted twice")
        self.assertEqual(saved["equipment"], again.to_dict()["equipment"])
        self.assertNotIn("defense", again.to_dict(), "and the saved base is the base, not the geared total")


class TestStartingGear(GameTestBase):
    def test_a_template_can_say_what_an_npc_starts_in(self):
        template = self.world.npc_templates["village_elder"]
        template["equipment"] = {"main_hand": "item_iron_sword", "body": "item_leather_tunic"}
        plain = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="plain_goblin")
        dressed = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="dressed")
        self.assertEqual("iron sword", dressed.equipment["main_hand"].name)
        self.assertEqual("leather tunic", dressed.equipment["body"].name)
        self.assertGreater(dressed.attack_power, NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="x").base_attack_power)
        self.assertFalse([item for item in plain.equipment.values() if item], "and others wear nothing")

    def test_taking_it_all_off_sticks_across_a_save(self):
        self.world.npc_templates["village_elder"]["equipment"] = {"main_hand": "item_iron_sword"}
        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="stripped")
        elder.equipment["main_hand"] = None
        companion_gear.refresh(elder)
        saved = elder.to_dict()
        self.assertEqual({}, saved["equipment"], "an empty save is a saved fact, not 'use the template'")
        again = NPCFactory.create_npc_from_template(
            "village_elder", self.world, instance_id="stripped_again", **{k: v for k, v in saved.items() if k not in ("template_id", "obj_id")})
        self.assertIsNone(again.equipment["main_hand"])


class TestTheValidator(unittest.TestCase):
    def issues(self, equipment):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from tests.fixtures import STORY_FIXTURE

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package)
        path = package / "data" / "npcs" / "people.json"
        people = json.loads(path.read_text(encoding="utf-8"))
        people[next(iter(people))]["equipment"] = equipment
        path.write_text(json.dumps(people), encoding="utf-8")
        _definition, found = validator.load_content_set(package)
        return [issue.message for issue in found if issue.severity == "error"]

    def test_good_gear_is_accepted(self):
        self.assertEqual([], [m for m in self.issues({"main_hand": "item_dark_blade"}) if "equipment" in m])

    def test_bad_gear_is_refused(self):
        text = "\n".join(self.issues({"tail": "item_dark_blade", "main_hand": "item_nope", "body": "item_dark_blade"}))
        self.assertIn("is not a slot", text)
        self.assertIn("references a missing item template", text)
        self.assertIn("cannot be worn there", text)
        self.assertIn("must be an object", "\n".join(self.issues("a sword")))


if __name__ == "__main__":
    unittest.main()
