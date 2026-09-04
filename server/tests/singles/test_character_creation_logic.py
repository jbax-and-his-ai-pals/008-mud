# tests/singles/test_character_creation_logic.py
from tests.fixtures import GameTestBase
from typing import Dict, Any

class TestCharacterCreationLogic(GameTestBase):

    def setUp(self):
        super().setUp()
        # Mock class definitions
        self.game.class_definitions = {
            "warrior": {
                "name": "Warrior",
                "description": "Strong.",
                "stats": {"strength": 15, "dexterity": 10},
                "inventory": [{"item_id": "item_iron_sword", "quantity": 1}],
                "spells": []
            }
        }
        self.game.available_classes = ["warrior"]

    def test_class_template_application(self):
        """Verify selecting a class correctly sets player stats and equipment."""
        self.game.selected_class_index = 0
        self.game.creation_name_input = "Conan"
        
        # Act
        self.game.finalize_new_game()
        
        # Assert
        player = self.world.player
        self.assertIsNotNone(player)
        if player:
            self.assertEqual(player.name, "Conan")
            self.assertEqual(player.runtime_state.progression.player_class, "Warrior")
            # Effective stat includes base (15)
            self.assertEqual(player.stats["strength"], 15)
            # Should have the sword from the template
            self.assertGreater(player.inventory.count_item("item_iron_sword"), 0)

    def test_name_input_handling(self):
        """Verify name input constraints in the game manager/input handler logic."""
        self.game.creation_name_input = "   Spacey   "
        self.game.finalize_new_game()
        
        player = self.world.player
        if player:
            self.assertEqual(player.name, "Spacey", "Final name should be stripped of whitespace.")
