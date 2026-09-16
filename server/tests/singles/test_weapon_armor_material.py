# tests/singles/test_weapon_armor_material.py
"""Coverage for the weapon-damage-type vs. armor-material mechanic
(WEAPON_VS_ARMOR_MULTIPLIERS in engine/config/config_combat.py): slashing
beats cloth/leather but loses to plate, piercing beats chain but loses to
plate, crushing beats plate/chain but is weakest against cloth. Verifies
both the raw table and that it's actually wired into take_damage for a
real equipped player and a real NPC template."""

from tests.fixtures import GameTestBase
from engine.config import WEAPON_VS_ARMOR_MULTIPLIERS
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory


class TestWeaponVsArmorMultiplierTable(GameTestBase):
    def test_slashing_favors_cloth_and_loses_to_plate(self):
        self.assertGreater(WEAPON_VS_ARMOR_MULTIPLIERS["slashing"]["cloth"], 1.0)
        self.assertLess(WEAPON_VS_ARMOR_MULTIPLIERS["slashing"]["plate"], 1.0)

    def test_piercing_favors_chain_and_loses_to_plate(self):
        self.assertGreater(WEAPON_VS_ARMOR_MULTIPLIERS["piercing"]["chain"], 1.0)
        self.assertLess(WEAPON_VS_ARMOR_MULTIPLIERS["piercing"]["plate"], 1.0)

    def test_crushing_favors_plate_and_is_weakest_against_cloth(self):
        self.assertGreater(WEAPON_VS_ARMOR_MULTIPLIERS["crushing"]["plate"], 1.0)
        weakest = min(WEAPON_VS_ARMOR_MULTIPLIERS["crushing"].values())
        self.assertEqual(WEAPON_VS_ARMOR_MULTIPLIERS["crushing"]["cloth"], weakest)

    def test_every_weapon_type_has_every_material(self):
        for weapon_type, matchups in WEAPON_VS_ARMOR_MULTIPLIERS.items():
            for material in ("cloth", "leather", "chain", "plate"):
                self.assertIn(material, matchups, f"{weapon_type} missing a {material} matchup")


class TestPlayerBodyArmorMaterial(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.stats["defense"] = 0
        if self.player.runtime_state.combat is not None:
            self.player.runtime_state.combat.defense = 0
        self.player.stats["dexterity"] = 0
        self.player.stats["resistances"] = {}
        self.player.max_health = 200
        self.player.health = 200

        self.world.item_templates["item_test_plate_cuirass"] = {
            "type": "Armor", "name": "Test Plate Cuirass", "value": 1, "weight": 1.0,
            "properties": {"defense": 0, "armor_material": "plate", "equip_slot": ["body"]},
        }

    def _equip_plate(self):
        cuirass = ItemFactory.create_item_from_template("item_test_plate_cuirass", self.world)
        self.assertIsNotNone(cuirass)
        self.player.inventory.add_item(cuirass)
        success, msg = self.player.equip_item(cuirass, "body")
        self.assertTrue(success, msg)

    def test_no_body_armor_is_neutral(self):
        damage = self.player.take_damage(20, "physical", weapon_damage_type="crushing")
        self.assertEqual(damage, 20)

    def test_no_weapon_damage_type_is_neutral_even_with_armor_worn(self):
        self._equip_plate()
        damage = self.player.take_damage(20, "physical")
        self.assertEqual(damage, 20)

    def test_slashing_vs_plate_is_reduced(self):
        self._equip_plate()
        damage = self.player.take_damage(20, "physical", weapon_damage_type="slashing")
        self.assertEqual(damage, int(20 * WEAPON_VS_ARMOR_MULTIPLIERS["slashing"]["plate"]))
        self.assertLess(damage, 20)

    def test_crushing_vs_plate_is_amplified(self):
        self._equip_plate()
        damage = self.player.take_damage(20, "physical", weapon_damage_type="crushing")
        self.assertEqual(damage, int(20 * WEAPON_VS_ARMOR_MULTIPLIERS["crushing"]["plate"]))
        self.assertGreater(damage, 20)

    def test_broken_armor_does_not_apply_material_multiplier(self):
        self._equip_plate()
        body_item = self.player.equipment["body"]
        self.assertIsNotNone(body_item)
        body_item.update_property("durability", 0)
        damage = self.player.take_damage(20, "physical", weapon_damage_type="crushing")
        self.assertEqual(damage, 20)


class TestNpcArmorMaterial(GameTestBase):
    def _chain_goblin(self, instance_id: str):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id=instance_id)
        self.assertIsNotNone(npc)
        npc.stats["defense"] = 0
        npc.stats["resistances"] = {}
        npc.max_health = 200
        npc.health = 200
        npc.properties["armor_material"] = "chain"
        return npc

    def test_piercing_vs_chain_npc_is_amplified(self):
        npc = self._chain_goblin("material_test_goblin_piercing")
        damage = npc.take_damage(20, "physical", weapon_damage_type="piercing")
        self.assertEqual(damage, int(20 * WEAPON_VS_ARMOR_MULTIPLIERS["piercing"]["chain"]))
        self.assertGreater(damage, 20)

    def test_slashing_vs_chain_npc_is_reduced(self):
        npc = self._chain_goblin("material_test_goblin_slashing")
        damage = npc.take_damage(20, "physical", weapon_damage_type="slashing")
        self.assertEqual(damage, int(20 * WEAPON_VS_ARMOR_MULTIPLIERS["slashing"]["chain"]))
        self.assertLess(damage, 20)

    def test_npc_without_authored_material_is_neutral(self):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="material_test_goblin_none")
        self.assertIsNotNone(npc)
        npc.stats["defense"] = 0
        npc.stats["resistances"] = {}
        npc.max_health = 200
        npc.health = 200
        damage = npc.take_damage(20, "physical", weapon_damage_type="crushing")
        self.assertEqual(damage, 20)
