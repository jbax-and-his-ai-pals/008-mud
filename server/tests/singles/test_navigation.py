# tests/singles/test_navigation.py
from tests.fixtures import GameTestBase
from engine.world.room import Room
from engine.items.key import Key

class TestNavigation(GameTestBase):
    
    def test_pathfinding_astar(self):
        """Verify A* finds the shortest path between rooms."""
        # Setup linear map: Room A -> Room B -> Room C
        region = self.world.get_region("town")
        if region:
            # Create temporary rooms
            room_a = Room("Room A", "Start", {"east": "room_b"}, obj_id="room_a")
            room_b = Room("Room B", "Middle", {"west": "room_a", "east": "room_c"}, obj_id="room_b")
            room_c = Room("Room C", "End", {"west": "room_b"}, obj_id="room_c")
            
            region.add_room("room_a", room_a)
            region.add_room("room_b", room_b)
            region.add_room("room_c", room_c)
            
            # Act: Find path A to C
            path = self.world.find_path("town", "room_a", "town", "room_c")
            
            # Assert
            self.assertIsNotNone(path)
            if path:
                self.assertEqual(path, ["east", "east"])

    def test_locked_room_entry(self):
        """Verify locked doors block movement unless key is possessed."""
        region = self.world.get_region("town")
        if region:
            # Create Locked Room
            # Note: "Vault" will be rendered as "VAULT" in titles
            room_locked = Room("Vault", "Secure", {"out": "town_square"}, obj_id="vault")
            room_locked.update_property("locked_by", "key_vault_master")
            region.add_room("vault", room_locked)
            
            # Connect Town Square to Vault
            start_room = region.get_room("town_square")
            if start_room:
                start_room.exits["enter"] = "vault"
                
                # 1. Attempt Entry (Fail)
                msg_fail = self.world.change_room("enter")
                self.assertIsNotNone(msg_fail)
                # Check for "locked" keyword case-insensitively
                self.assertIn("locked", msg_fail.lower())
                self.assertNotEqual(self.player.current_room_id, "vault")
                
                # 2. Add Key
                key = Key(obj_id="key_vault_master", name="Vault Key")
                self.player.inventory.add_item(key)
                
                # 3. Attempt Entry (Success)
                msg_success = self.world.change_room("enter")
                self.assertIsNotNone(msg_success)
                # FIX: Check for "vault" in lower case to match "VAULT" title or description
                self.assertIn("vault", msg_success.lower()) 
                self.assertEqual(self.player.current_room_id, "vault")