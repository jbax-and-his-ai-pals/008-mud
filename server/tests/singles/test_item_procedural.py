# tests/singles/test_item_procedural.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.magic.spell_registry import register_spell
from engine.magic.spell import Spell

class TestItemProcedural(GameTestBase):
    
    def test_random_scroll_generation(self):
        """Verify procedural scrolls transmute into concrete spell scrolls."""
        # 1. Ensure there's at least one valid spell to pick
        test_spell = Spell(spell_id="proc_test", name="Proc Test", description="test", effects=[{"type": "damage", "value": 1}], level_required=1, mana_cost=5)
        register_spell(test_spell)
        
        # 2. Inject the procedural template
        self.world.item_templates["item_scroll_random"] = {
            "type": "Consumable",
            "name": "Random Scroll",
            "description": "Unidentified.",
            "properties": {
                "is_procedural": True,
                "procedural_type": "random_spell_scroll"
            }
        }
        
        # 3. Create the item
        scroll = ItemFactory.create_item_from_template("item_scroll_random", self.world)
        
        self.assertIsNotNone(scroll)
        if scroll:
            # Check if it was transformed
            self.assertFalse(scroll.get_property("is_procedural"), "Procedural flag should be cleared.")
            self.assertIsNotNone(scroll.get_property("spell_to_learn"), "Should have a spell assigned.")
            self.assertIn("Scroll of", scroll.name)
            self.assertGreater(scroll.value, 0)

    def test_distinct_random_scrolls_do_not_collapse_into_one_inventory_stack(self):
        """Bug repro: two procedurally-generated scrolls teaching different
        spells share the same template obj_id (item_scroll_random). If the
        template's explicit stackable=False is ignored, picking both up
        merges them into a single stack and silently discards all but the
        first scroll's spell_to_learn."""
        spell_a = Spell(spell_id="proc_a", name="Proc A", description="x", effects=[{"type": "damage", "value": 1}], level_required=1, mana_cost=5)
        spell_b = Spell(spell_id="proc_b", name="Proc B", description="x", effects=[{"type": "damage", "value": 1}], level_required=1, mana_cost=5)
        register_spell(spell_a)
        register_spell(spell_b)

        # Mirror the real fantasy_frontier item_scroll_random template,
        # including its top-level "stackable": False.
        self.world.item_templates["item_scroll_random"] = {
            "type": "Consumable",
            "name": "Scroll of {spell_name}",
            "description": "A scroll.",
            "stackable": False,
            "properties": {
                "uses": 1,
                "effect_type": "learn_spell",
                "is_procedural": True,
                "procedural_type": "random_spell_scroll",
            },
        }

        scroll_1 = ItemFactory.create_item_from_template(
            "item_scroll_random", self.world, spell_to_learn="proc_a", name="Scroll of Proc A",
        )
        scroll_2 = ItemFactory.create_item_from_template(
            "item_scroll_random", self.world, spell_to_learn="proc_b", name="Scroll of Proc B",
        )
        self.assertFalse(scroll_1.stackable)
        self.assertFalse(scroll_2.stackable)

        self.player.inventory.add_item(scroll_1)
        self.player.inventory.add_item(scroll_2)

        held_spells = {
            slot.item.get_property("spell_to_learn")
            for slot in self.player.inventory.slots
            if slot.item is not None
        }
        self.assertIn("proc_a", held_spells)
        self.assertIn("proc_b", held_spells)
