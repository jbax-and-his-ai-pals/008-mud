# tests/batch/test_batch_mechanics_deep.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.weapon import Weapon
from engine.items.armor import Armor
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory
from engine.core.combat_system import CombatSystem

class TestBatchMechanicsDeep(GameTestBase):
    """
    Stress tests for advanced mechanics: Curses, Requirements, Status Flags, and Complex Spells.
    """

    def setUp(self):
        super().setUp()
        self.world.item_templates["cursed_ring"] = {
            "type": "Armor", "name": "Ring of Burden", "value": 500,
            "properties": {
                "equip_slot": ["hands"], "defense": 5, "cursed": True,
                "equip_effect": {"type": "stat_mod", "name": "Burden", "modifiers": {"agility": -5}}
            }
        }
        self.world.item_templates["heavy_plate"] = {
            "type": "Armor", "name": "Titan Plate", "value": 1000,
            "properties": {"equip_slot": ["body"], "defense": 10, "requirements": {"strength": 100}}
        }
        self.world.item_templates["glass_dagger"] = {
            "type": "Weapon", "name": "Glass Dagger", "value": 200,
            "properties": {"equip_slot": ["main_hand"], "damage": 50, "durability": 2, "max_durability": 2}
        }
        self.silence_spell = Spell("silence_ray", "Silence Ray", "Shhh.", effects=[{"type": "apply_effect", "effect_data": {"type": "debuff", "name": "Silenced", "tags": ["curse"], "base_duration": 10.0}}], target_type="enemy")
        self.cleanse_spell = Spell("cleanse", "Cleanse", "Cures.", effects=[{"type": "cleanse", "effect_data": {"tags": ["curse", "poison"]}}], target_type="friendly")
        self.remove_curse_spell = Spell("remove_curse", "Remove Curse", "Unbinds.", effects=[{"type": "remove_curse"}], target_type="friendly")
        self.life_tap = Spell("life_tap", "Life Tap", "Drain.", effects=[{"type": "life_tap", "value": 20, "damage_type": "magical"}], target_type="enemy")
        
        for s in [self.silence_spell, self.cleanse_spell, self.remove_curse_spell, self.life_tap]:
            register_spell(s)
            self.player.runtime_state.magic.known_spells.add(s.spell_id)

    def test_stat_requirements_block_equip(self):
        plate = ItemFactory.create_item_from_template("heavy_plate", self.world)
        if plate:
            self.player.inventory.add_item(plate)
            self.player.stats["strength"] = 10
            success, msg = self.player.equip_item(plate)
            self.assertFalse(success)
            self.assertIn("need 100 Strength", msg)
            self.player.stats["strength"] = 100
            success, msg = self.player.equip_item(plate)
            self.assertTrue(success)

    def test_cursed_item_lock(self):
        ring = ItemFactory.create_item_from_template("cursed_ring", self.world)
        if ring:
            self.player.inventory.add_item(ring)
            self.player.equip_item(ring)
            success, msg = self.player.unequip_item("hands")
            self.assertFalse(success)
            self.assertIn("binds to your flesh", msg)
            
            res = self.player.cast_spell(self.remove_curse_spell, self.player, time.time(), self.world)
            self.assertTrue(res["success"])
            self.assertIn("removed", res["message"])
            self.assertFalse(ring.get_property("cursed"))
            
            success, msg = self.player.unequip_item("hands")
            self.assertTrue(success)

    def test_silence_prevents_casting(self):
        self.player.apply_effect({"name": "Silenced", "type": "debuff"}, time.time())
        res = self.player.cast_spell(self.cleanse_spell, self.player, time.time(), self.world)
        self.assertFalse(res["success"])
        self.assertIn("silenced", res["message"].lower())

    def test_blind_hit_chance_cap(self):
        self.player.apply_effect({"name": "Blind", "type": "debuff"}, time.time())
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            target.stats["agility"] = 1 
            self.player.stats["agility"] = 100 
            chance = CombatSystem.calculate_hit_chance(self.player, target)
            self.assertEqual(chance, 0.20)

    def test_life_tap_mechanic(self):
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            target.health = 100; target.stats["magic_resist"] = 0
            self.player.max_health = 100; self.player.health = 50
            with patch('random.uniform', return_value=0.0):
                res = self.player.cast_spell(self.life_tap, target, time.time(), self.world)
            self.assertTrue(res["success"])
            self.assertLess(target.health, 100)
            self.assertGreater(self.player.health, 50)
            self.assertIn("heals", res["message"])

    def test_cleanse_specific_tags(self):
        self.player.apply_effect({"name": "Venom", "type": "dot", "tags": ["poison"]}, time.time())
        self.player.apply_effect({"name": "Might", "type": "buff", "tags": ["magic"]}, time.time())
        self.assertTrue(self.player.has_effect("Venom"))
        self.assertTrue(self.player.has_effect("Might"))
        self.player.cast_spell(self.cleanse_spell, self.player, time.time(), self.world)
        self.assertFalse(self.player.has_effect("Venom"))
        self.assertTrue(self.player.has_effect("Might"))

    def test_glass_dagger_breaking(self):
        dagger = ItemFactory.create_item_from_template("glass_dagger", self.world)
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if dagger and target:
            self.player.inventory.add_item(dagger)
            self.player.equip_item(dagger, "main_hand")
            target.health = 1000
            with patch('random.random', return_value=0.0):
                self.player.attack(target, self.world)
                self.assertEqual(dagger.get_property("durability"), 1)
                res = self.player.attack(target, self.world)
                self.assertEqual(dagger.get_property("durability"), 0)
                self.assertIn("breaks", res["message"])
