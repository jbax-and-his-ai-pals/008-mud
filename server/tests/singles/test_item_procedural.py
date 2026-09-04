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
