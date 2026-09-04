# tests/singles/test_scroll_learning.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestScrollLearning(GameTestBase):

    def setUp(self):
        super().setUp()
        # Setup Spell
        self.spell = Spell(spell_id="scroll_test_spell", name="Test Spell", description="x", effects=[{"type": "damage", "value": 1}], level_required=1, mana_cost=5)
        register_spell(self.spell)
        
        # Setup Scroll Template
        self.world.item_templates["scroll_test"] = {
            "type": "Consumable", "name": "Scroll of Test", "value": 10,
            "properties": {
                "effect_type": "learn_spell",
                "spell_to_learn": "scroll_test_spell",
                "uses": 1
            }
        }

    def test_learn_unknown_spell(self):
        """Verify using a scroll teaches the spell and consumes the item."""
        scroll = ItemFactory.create_item_from_template("scroll_test", self.world)
        if scroll:
            self.player.inventory.add_item(scroll)
            
            # Act
            result = scroll.use(self.player)
            
            # Assert
            self.assertIn("successfully learn", result)
            self.assertIn("scroll_test_spell", self.player.runtime_state.magic.known_spells)
            self.assertEqual(scroll.get_property("uses"), 0)

    def test_learn_known_spell_prevention(self):
        """Verify using a scroll for a known spell prevents consumption."""
        self.player.learn_spell("scroll_test_spell")
        
        scroll = ItemFactory.create_item_from_template("scroll_test", self.world)
        if scroll:
            self.player.inventory.add_item(scroll)
            
            # Act
            result = scroll.use(self.player)
            
            # Assert
            self.assertIn("already know", result.lower())
            # Item should NOT be used up
            self.assertEqual(scroll.get_property("uses"), 1)
