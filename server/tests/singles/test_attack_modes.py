# tests/singles/test_attack_modes.py
"""A weapon with more than one way of being used: a spear thrusts or slashes, and the blow says which.

`properties.attack_modes` is a list of `{verb, text, weapon_damage_type, damage_bonus}`. Each blow, by a player or by a
creature holding the weapon (a companion in its main hand), uses one at random: its verb and sentence tell the blow, and its
`weapon_damage_type` is the type the blow deals (so thrusting can pierce and sweeping slash). Without modes a weapon reads as
it always did, except that a creature holding one now names it.
"""

import re
import unittest
from unittest.mock import patch

from engine.contracts.equipment import ATTACK_MODE_KEYS, attack_modes, choose_attack_mode
from engine.core.combat_system import CombatSystem
from engine.items.item_factory import ItemFactory
from engine.npcs import companion_gear, companions
from engine.npcs.npc_factory import NPCFactory
from tests.fixtures import GameTestBase

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")

SPEAR_MODES = [
    {"name": "thrust", "verb": "thrust", "text": "{attacker} {verb} {possessive} {weapon} at {defender}", "weapon_damage_type": "piercing"},
    {"name": "slash", "verb": "slash", "text": "{attacker} {verb} at {defender} with {possessive} {weapon}", "weapon_damage_type": "slashing", "damage_bonus": 1},
]


def plain(text):
    """Without colour markup or the "(Level 3, 52/52 HP)" a viewer sees after a name."""
    return re.sub(r" \([^)]*\)", "", _MARKUP.sub("", text))


def spear(world):
    item = ItemFactory.create_item_from_template("item_iron_sword", world)
    item.name = "iron spear"
    item.update_property("attack_modes", [dict(mode) for mode in SPEAR_MODES])
    return item


class _Holder:
    def __init__(self, modes):
        self.properties = {"attack_modes": modes}

    def get_property(self, key, default=None):
        return self.properties.get(key, default)


class _Someone:
    def __init__(self, name):
        self.name = name


class TestTheWords(unittest.TestCase):
    def test_a_verb_is_conjugated_for_you_and_for_anyone_else(self):
        for base, other in (("thrust", "thrusts"), ("slash", "slashes"), ("push", "pushes"), ("try", "tries"), ("play", "plays"), ("jab at", "jabs at")):
            self.assertEqual(base, CombatSystem._verb_for(base, True))
            self.assertEqual(other, CombatSystem._verb_for(base, False), base)

    def test_a_creature_has_its_weapon_a_person_has_their_own(self):
        self.assertTrue(CombatSystem._is_a_person(_Someone("Captain Kessa")))
        self.assertTrue(CombatSystem._is_a_person(_Someone("Red Fleet soldier")))
        self.assertFalse(CombatSystem._is_a_person(_Someone("goblin scout")))

    def test_a_template_with_a_stray_field_falls_back_to_the_plain_sentence(self):
        sentence = CombatSystem._mode_sentence({"text": "{attacker} {nonsense} {defender}"}, "You", "hit", "your", "spear", "the orc")
        self.assertEqual("You hit the orc with your spear", sentence)

    def test_the_contract_reads_modes_and_chooses_among_them(self):
        self.assertEqual([], attack_modes(None, _Holder(None)))
        self.assertIsNone(choose_attack_mode(None, _Holder([])))
        seen = {choose_attack_mode(None, _Holder(SPEAR_MODES))["name"] for _ in range(80)}
        self.assertEqual({"thrust", "slash"}, seen, "both come up")


class _Target(GameTestBase):
    def setUp(self):
        super().setUp()
        self.goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="target")
        self.world.add_npc(self.goblin)
        self.goblin.health = self.goblin.max_health = 100000
        self.goblin.current_region_id, self.goblin.current_room_id = self.player.current_region_id, self.player.current_room_id


class TestABlowWithAMode(_Target):
    def test_the_player_s_blow_is_told_in_the_modes_own_words(self):
        mode = SPEAR_MODES[0]
        with patch("engine.core.combat_system.random.random", return_value=0.0):
            hit = plain(CombatSystem.execute_attack(self.player, self.goblin, 5, "iron spear", viewer=self.player, mode=mode)["message"])
        self.assertRegex(hit, r"^You thrust your iron spear at .*goblin.* and deal \d+ damage\.$")
        with patch("engine.core.combat_system.random.random", return_value=1.0):
            miss = plain(CombatSystem.execute_attack(self.player, self.goblin, 5, "iron spear", viewer=self.player, mode=mode)["message"])
        self.assertRegex(miss, r"^You thrust your iron spear at .*goblin.*, but miss!$")

    def test_a_blow_without_a_mode_is_worded_as_before(self):
        with patch("engine.core.combat_system.random.random", return_value=0.0):
            hit = plain(CombatSystem.execute_attack(self.player, self.goblin, 5, "iron sword", viewer=self.player)["message"])
        self.assertRegex(hit, r"^You attack .*goblin.* with your iron sword and deal \d+ damage\.$")

    def test_a_player_wielding_it_strikes_each_way_and_the_message_says_which(self):
        self.player.equipment["main_hand"] = spear(self.world)
        seen, types = set(), set()
        real = CombatSystem.execute_attack

        def spy(*args, **kwargs):
            if kwargs.get("mode"):
                types.add(kwargs.get("weapon_damage_type"))
            return real(*args, **kwargs)

        with patch.object(CombatSystem, "execute_attack", staticmethod(spy)):
            for _ in range(60):
                self.player.last_attack_time = 0
                text = plain(self.player.attack(self.goblin, self.world).get("message", ""))
                seen.add("thrust" if " thrust " in text else "slash" if " slash at " in text else "other")
        self.assertIn("thrust", seen)
        self.assertIn("slash", seen)
        self.assertNotIn("other", seen)
        self.assertEqual({"piercing", "slashing"}, types, "and each deals its own type of blow")


class TestACompanionWithAWeapon(_Target):
    def setUp(self):
        super().setUp()
        self.companion = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="the_companion")
        self.world.add_npc(self.companion)
        self.companion.name = "Captain Brannoc"
        self.companion.properties.pop("essential", None)
        self.companion.current_region_id, self.companion.current_room_id = self.player.current_region_id, self.player.current_room_id
        companions.recruit(self.world, self.player, self.companion)

    def blows(self, count):
        from engine.npcs import combat as npc_combat

        with patch("engine.core.combat_system.random.random", return_value=0.0):
            return [plain(npc_combat.attack(self.companion, self.goblin)["message"]) for _ in range(count)]

    def wield(self, item):
        self.companion.equipment["main_hand"] = item
        companion_gear.refresh(self.companion)

    def test_it_names_the_weapon_it_holds_and_uses_each_way(self):
        self.wield(spear(self.world))
        texts = self.blows(60)
        self.assertTrue([t for t in texts if re.match(r"^Captain Brannoc thrusts their iron spear at .* and deals \d+ damage\.$", t)], texts[:3])
        self.assertTrue([t for t in texts if re.match(r"^Captain Brannoc slashes at .* with their iron spear and deals \d+ damage\.$", t)], texts[:3])

    def test_a_weapon_with_one_way_is_named_in_the_plain_sentence(self):
        self.wield(ItemFactory.create_item_from_template("item_iron_sword", self.world))
        self.assertRegex(self.blows(1)[0], r"^Captain Brannoc attacks .* with their iron sword and deals \d+ damage\.$")

    def test_barehanded_it_says_what_it_always_did(self):
        self.assertRegex(self.blows(1)[0], r"^Captain Brannoc attacks .* and deals \d+ damage\.$")

    def test_the_modes_damage_type_is_the_blows_type(self):
        self.wield(spear(self.world))
        seen = set()
        real = CombatSystem.execute_attack

        def spy(*args, **kwargs):
            seen.add(kwargs.get("weapon_damage_type"))
            return real(*args, **kwargs)

        with patch.object(CombatSystem, "execute_attack", staticmethod(spy)):
            self.blows(60)
        self.assertEqual({"piercing", "slashing"}, seen)


class TestTheValidator(unittest.TestCase):
    def problems(self, properties, item_type="Weapon"):
        from engine.server.content_set.contracts_items import _attack_mode_problems

        return _attack_mode_problems({"type": item_type, "properties": properties}, item_type)

    def test_good_modes_are_accepted(self):
        self.assertEqual([], self.problems({"attack_modes": SPEAR_MODES}))
        self.assertEqual([], self.problems({"attack_modes": [{}]}), "every key is optional")
        self.assertEqual([], self.problems({}), "and an item without them is untouched")

    def test_bad_modes_are_refused_with_what_to_fix(self):
        cases = (
            ("thrust", "non-empty list"), ([], "non-empty list"), (["thrust"], "must be an object"),
            ([{"verb": "Thrust"}], "lower-case words"), ([{"verb": 5}], "lower-case words"),
            ([{"weapon_damage_type": "fire"}], "must be one of slashing, piercing, crushing"),
            ([{"damage_bonus": 99}], "whole number from -5 to 50"), ([{"damage_bonus": True}], "whole number"),
            ([{"text": "{attacker} hits"}], "must name the {attacker} and the {defender}"),
            ([{"text": "{attacker} {nonsense} {defender}"}], "uses {nonsense}"),
            ([{"text": "{attacker {defender}"}], "not a valid template"),
            ([{"speed": 3}], "is not read"),
        )
        for modes, fragment in cases:
            joined = " | ".join(self.problems({"attack_modes": modes}))
            self.assertIn(fragment, joined, (modes, joined))

    def test_only_a_weapon_has_them(self):
        self.assertIn("belong on a Weapon", " ".join(self.problems({"attack_modes": SPEAR_MODES}, "Armor")))

    def test_the_vocabulary_the_editor_mirrors(self):
        self.assertEqual(("name", "verb", "text", "weapon_damage_type", "damage_bonus"), ATTACK_MODE_KEYS)


if __name__ == "__main__":
    unittest.main()
