# tests/singles/test_item_factory_resilience.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestItemFactoryResilience(GameTestBase):

    def test_invalid_template_id(self):
        """Verify factory returns None for non-existent templates."""
        item = ItemFactory.create_item_from_template("non_existent_item_id_999", self.world)
        self.assertIsNone(item)

    def test_missing_type_in_template(self):
        """Verify factory handles templates with missing 'type' definition."""
        # Inject broken template
        self.world.item_templates["broken_item"] = {
            "name": "Broken",
            "value": 1
            # Missing "type"
        }
        
        # Factory logic defaults to "Item" base class if type is missing or invalid mapping
        # But create_item_from_template relies on 'type' key.
        # Current implementation: item_type_name = template.get("type", "Item")
        # So it should default to Item.
        
        item = ItemFactory.create_item_from_template("broken_item", self.world)
        self.assertIsNotNone(item)
        if item:
            self.assertEqual(item.name, "Broken")
            self.assertEqual(item.__class__.__name__, "Item")