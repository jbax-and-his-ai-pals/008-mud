# tests/batch/test_batch_28.py
import time
import os
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.interactive import Interactive
from engine.world.room import Room
from engine.world.region import Region
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

# Force registration of the 'pull' command for these tests
import engine.commands.interaction.environment 

class TestBatch28(GameTestBase):
    """Focus: Interactive Objects, Bosses, Visual Juice."""

    def test_lever_toggles_exit(self):
        """Verify pulling a lever opens a hidden exit."""
        # 1. Setup Region/Room
        region = Region("Test Dungeon", "x", obj_id="dungeon")
        room_a = Room("Hall", "A hall.", obj_id="hall")
        room_b = Room("Secret Room", "Secret.", obj_id="secret")
        
        # Define hidden exit logic
        room_a.properties["hidden_exits"] = {"north": "secret"}
        
        region.add_room("hall", room_a)
        region.add_room("secret", room_b)
        self.world.add_region("dungeon", region)
        
        # 2. Setup Lever
        lever = Interactive(
            obj_id="lever_1", name="rusty lever", 
            interaction_type="toggle", state="off",
            linked_target_id="dungeon:hall", 
            linked_action="toggle_exit:north",
            interaction_message="Clunk."
        )
        room_a.add_item(lever)
        
        # 3. Move Player
        self.player.current_region_id = "dungeon"
        self.player.current_room_id = "hall"
        self.world.current_region_id = "dungeon"
        self.world.current_room_id = "hall"
        
        # 4. Assert Exit Closed
        self.assertNotIn("north", room_a.exits)
        
        # 5. Act: Pull Lever
        res = self.game.process_command("pull rusty lever")
        
        # 6. Assert Exit Open
        self.assertIsNotNone(res, "Command result should not be None")
        if res:
             # FIX: Case-insensitive check for state change message
             self.assertIn("ON", res.upper()) 
             
        self.assertIn("north", room_a.exits)
        self.assertEqual(room_a.exits["north"], "secret")
        
        # 7. Act: Pull Again (Close)
        self.game.process_command("pull rusty lever")
        self.assertNotIn("north", room_a.exits)

    def test_boss_special_attack_trigger(self):
        """Verify boss uses special ability when RNG favors it."""
        boss = NPCFactory.create_npc_from_template("goblin", self.world) # Base template
        if boss:
            boss.name = "Boss Goblin"
            boss.attack_power = 10
            # Inject Special Ability
            boss.properties["special_abilities"] = [{
                "name": "Power Smash",
                "damage_multiplier": 2.0, # 20 Damage
                "message": "BOSS SMASH!"
            }]
            
            # Force RNG to trigger special ( < 0.2 )
            # We patch random.random. 
            # Note: CombatSystem.execute_attack ALSO calls random.random for hit chance.
            # So we need side_effect: [0.1 (trigger special), 0.0 (hit check success)]
            with patch('random.random', side_effect=[0.1, 0.0]):
                # Patch randint for damage variance to be 0
                with patch('random.randint', return_value=0):
                     result = boss.attack(self.player)
            
            # Assertions
            self.assertIn("BOSS SMASH!", result["message"])

    def test_visual_juice_text_added(self):
        """Verify floating text is added to renderer on damage."""
        # 1. Clear existing texts (using list directly since we know we are patching it)
        # Note: self.game.renderer is a MockRenderer in tests, so we need to ensure it handles this attribute
        self.game.renderer.floating_texts = [] # type: ignore
        
        # Monkey patch the mock for this test with correct signature
        def mock_add_text(text: str, x: int, y: int, color: tuple):
            self.game.renderer.floating_texts.append(text) # type: ignore
        
        # Apply the patch to the specific instance
        self.game.renderer.add_floating_text = mock_add_text # type: ignore
        
        # 2. Player takes damage
        self.player.take_damage(5, "physical")
        
        # 3. Assert
        # Check specific list on our mock
        floating_texts = getattr(self.game.renderer, 'floating_texts', [])
        self.assertEqual(len(floating_texts), 1)
        self.assertEqual(floating_texts[0], "-5")

    def test_interactive_state_persistence(self):
        """Verify interactive object state survives save/load."""
        TEST_SAVE = "interactive_save.json"
        
        # 1. Register Template (Critical for Save/Load to work)
        self.world.item_templates["template_lever"] = {
            "type": "Interactive", 
            "name": "Lever", 
            "value": 0,
            # FIX: Override weight to be light so it can be picked up for the test case
            "weight": 0.1, 
            "properties": {
                "interaction_type": "toggle",
                "state": "off"
            }
        }

        # 2. Create Item from Template
        lever = ItemFactory.create_item_from_template("template_lever", self.world)
        if not lever:
            self.fail("Failed to create interactive item from template")
            return

        # Explicitly set ID to match template so serialization works
        lever.obj_id = "template_lever"
        
        # FIX: Ensure it is added successfully
        success, msg = self.player.inventory.add_item(lever)
        self.assertTrue(success, f"Failed to add lever to inventory: {msg}")
        
        # 3. Interact (Turn On)
        if isinstance(lever, Interactive):
             lever.interact(None, None) 
        
        self.assertEqual(lever.get_property("state"), "on")
        
        # 4. Save
        self.world.save_game(TEST_SAVE)
        
        # 5. Clear World
        self.player.inventory.slots = []
        
        # 6. Load
        self.world.load_save_game(TEST_SAVE)
        
        # 7. Verify
        # Ensure player exists
        self.assertIsNotNone(self.world.player)
        if self.world.player:
            loaded = self.world.player.inventory.get_item("template_lever")
            self.assertIsNotNone(loaded, "Interactive item failed to persist")
            if loaded:
                self.assertEqual(loaded.get_property("state"), "on")
             
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_invalid_interaction_target(self):
        """Verify interacting with non-interactive items fails gracefully."""
        # Check player location validity
        if not self.player.current_region_id or not self.player.current_room_id:
             self.fail("Player location invalid")
             return

        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, sword)
            
            res = self.game.process_command("pull iron sword")
            self.assertIsNotNone(res)
            # The error message from environment.py is "Nothing happens when you interact..."
            if res:
                self.assertIn("Nothing happens", res)