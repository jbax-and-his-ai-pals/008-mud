# tests/singles/test_p7_itemisation_tiers.py
"""Coverage for P7's itemisation-ladder expansion: the tier 2/3 weapons and
armor added to content_sets/fantasy_frontier, their crafting recipes, and
the two new affix pairs (Brutal/Adamant, of the Serpent/of Stoneskin)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.weapon import Weapon
from engine.items.armor import Armor
from engine.items.loot_generator import LootGenerator, PREFIXES, SUFFIXES


TIER_2_WEAPONS = [
    "item_war_mace", "item_battle_hammer", "item_hunting_spear",
    "item_steel_rapier", "item_broadsword", "item_waraxe",
]
TIER_3_WEAPONS = [
    "item_greatsword", "item_warhammer", "item_halberd", "item_masterwork_estoc",
]
TIER_2_ARMOR = [
    "item_chain_coif", "item_chain_hauberk", "item_chain_gauntlets",
    "item_chain_sabatons", "item_warding_torc", "item_acolytes_mantle",
]
TIER_3_ARMOR = [
    "item_plate_helm", "item_plate_cuirass", "item_plate_gauntlets",
    "item_plate_sabatons", "item_vanguards_signet",
]


class TestTierWeaponsLoad(GameTestBase):
    def test_every_tier_weapon_loads_with_a_damage_type(self):
        for item_id in TIER_2_WEAPONS + TIER_3_WEAPONS:
            with self.subTest(item_id=item_id):
                weapon = ItemFactory.create_item_from_template(item_id, self.world)
                self.assertIsInstance(weapon, Weapon, f"{item_id} did not load as a Weapon")
                damage_type = weapon.get_property("weapon_damage_type")
                self.assertIn(damage_type, ("slashing", "piercing", "crushing"))
                self.assertGreater(weapon.get_property("damage", 0), 8)  # above the old tier-1 ceiling

    def test_tier_2_weapons_are_tagged_tier_2(self):
        for item_id in TIER_2_WEAPONS:
            with self.subTest(item_id=item_id):
                weapon = ItemFactory.create_item_from_template(item_id, self.world)
                self.assertEqual(weapon.get_property("tier"), 2)

    def test_tier_3_weapons_are_tagged_tier_3(self):
        for item_id in TIER_3_WEAPONS:
            with self.subTest(item_id=item_id):
                weapon = ItemFactory.create_item_from_template(item_id, self.world)
                self.assertEqual(weapon.get_property("tier"), 3)

    def test_crushing_is_no_longer_underrepresented(self):
        crushing_weapons = [
            item_id for item_id in TIER_2_WEAPONS + TIER_3_WEAPONS
            if ItemFactory.create_item_from_template(item_id, self.world).get_property("weapon_damage_type") == "crushing"
        ]
        self.assertGreaterEqual(len(crushing_weapons), 2)


class TestTierArmorLoads(GameTestBase):
    def test_tier_2_introduces_chain_material(self):
        chain_pieces = 0
        for item_id in TIER_2_ARMOR:
            armor = ItemFactory.create_item_from_template(item_id, self.world)
            self.assertIsInstance(armor, Armor, f"{item_id} did not load as Armor")
            if armor.get_property("armor_material") == "chain":
                chain_pieces += 1
        self.assertGreaterEqual(chain_pieces, 4)

    def test_tier_3_introduces_plate_material(self):
        plate_pieces = 0
        for item_id in TIER_3_ARMOR:
            armor = ItemFactory.create_item_from_template(item_id, self.world)
            self.assertIsInstance(armor, Armor, f"{item_id} did not load as Armor")
            if armor.get_property("armor_material") == "plate":
                plate_pieces += 1
        self.assertGreaterEqual(plate_pieces, 4)

    def test_neck_slot_is_no_longer_empty(self):
        """ROADMAP.md's P7 itemisation complaint: zero neck items in the
        core ladder. item_warding_torc and item_vanguards_signet fix that."""
        for item_id in ("item_warding_torc", "item_vanguards_signet"):
            with self.subTest(item_id=item_id):
                armor = ItemFactory.create_item_from_template(item_id, self.world)
                self.assertEqual(armor.get_property("equip_slot"), ["neck"])

    def test_plate_cuirass_trades_defense_for_an_agility_penalty(self):
        cuirass = ItemFactory.create_item_from_template("item_plate_cuirass", self.world)
        self.assertGreater(cuirass.get_property("defense"), 9)
        effect = cuirass.get_property("equip_effect")
        self.assertEqual(effect["modifiers"]["agility"], -2)

    def test_acolytes_mantle_is_the_cloth_caster_tradeoff(self):
        mantle = ItemFactory.create_item_from_template("item_acolytes_mantle", self.world)
        self.assertEqual(mantle.get_property("armor_material"), "cloth")
        effect = mantle.get_property("equip_effect")
        self.assertEqual(effect["modifiers"]["spell_power"], 3)
        # Lower defense than the equivalent tier's chain hauberk -- the tradeoff.
        hauberk = ItemFactory.create_item_from_template("item_chain_hauberk", self.world)
        self.assertLess(mantle.get_property("defense"), hauberk.get_property("defense"))


class TestNewAffixes(GameTestBase):
    def test_new_affixes_are_registered(self):
        self.assertIn("Brutal", PREFIXES)
        self.assertIn("Adamant", PREFIXES)
        self.assertIn("of the Serpent", SUFFIXES)
        self.assertIn("of Stoneskin", SUFFIXES)

    def test_new_affixes_are_reachable_by_authored_npc_levels(self):
        """Unlike "of Vampirism" (level_min 10, above the level-8 NPC
        ceiling), these should actually be rollable in play."""
        for name, table in (("Brutal", PREFIXES), ("Adamant", PREFIXES),
                             ("of the Serpent", SUFFIXES), ("of Stoneskin", SUFFIXES)):
            with self.subTest(affix=name):
                self.assertLessEqual(table[name]["level_min"], 8)

    def test_brutal_prefix_boosts_weapon_damage(self):
        # _pick_affix rolls randomly among every valid affix for the type/
        # level, so pin it directly to "Brutal" (prefix) and "no suffix"
        # rather than fighting random.choice's selection among many valids.
        with patch("engine.items.loot_generator.random.random", return_value=0.0), \
             patch("engine.items.loot_generator.LootGenerator._pick_affix",
                   side_effect=[("Brutal", PREFIXES["Brutal"]), ("", {})]):
            item = LootGenerator.generate_loot("item_iron_sword", self.world, level=6, rarity_roll=1.0)
        self.assertIsNotNone(item)
        self.assertIn("Brutal", item.name)
        self.assertEqual(item.get_property("damage"), 8 + PREFIXES["Brutal"]["modifiers"]["damage"])


class TestTierCraftingRecipes(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager

    def _craft(self, recipe_id: str) -> str:
        self.game.process_command("spawnstation anvil")
        self.game.process_command(f"givemats {recipe_id}")
        with patch("engine.crafting.crafting_manager.SkillSystem.attempt_check", return_value=(True, "forced success")):
            return self.manager.craft(self.player, recipe_id)

    def test_every_new_recipe_is_registered(self):
        expected = [
            "forge_war_mace", "forge_battle_hammer", "craft_hunting_spear", "forge_steel_rapier",
            "forge_broadsword", "forge_waraxe", "forge_chain_coif", "forge_chain_hauberk",
            "forge_chain_gauntlets", "forge_chain_sabatons", "craft_warding_torc",
            "weave_acolytes_mantle", "forge_greatsword", "forge_warhammer", "forge_halberd",
            "forge_masterwork_estoc", "forge_plate_helm", "forge_plate_cuirass",
            "forge_plate_gauntlets", "forge_plate_sabatons", "forge_vanguards_signet",
        ]
        for recipe_id in expected:
            with self.subTest(recipe_id=recipe_id):
                self.assertIn(recipe_id, self.manager.recipes)

    def test_craft_tier_2_weapon(self):
        result = self._craft("forge_war_mace")
        self.assertNotIn("fail", result.lower())
        self.assertIsNotNone(self.player.inventory.find_item_by_name("war mace"))

    def test_craft_tier_3_armor_needs_rare_monster_material(self):
        recipe = self.manager.recipes["forge_plate_cuirass"]
        ingredient_ids = [ing["item_id"] for ing in recipe.ingredients]
        self.assertIn("item_chitin_plate", ingredient_ids)
        result = self._craft("forge_plate_cuirass")
        self.assertNotIn("fail", result.lower())
        self.assertIsNotNone(self.player.inventory.find_item_by_name("plate cuirass"))
