# tests/singles/test_ai_manager_validation.py
from tests.fixtures import GameTestBase
from engine.ai.ai_manager import AIManager
from engine.player.core import Player
from engine.world.region import Region
from engine.world.room import Room
from engine.npcs.npc import NPC

class TestAIManagerValidation(GameTestBase):

    def test_context_stamp_consistency(self):
        """Verify context stamps change when the player moves."""
        ai_mgr = self.game.ai_manager
        
        # 1. Capture initial stamp
        stamp_1 = ai_mgr._create_context_stamp()
        
        # 2. Change state (Move player)
        self.player.current_room_id = "new_room"
        
        # 3. Capture second stamp
        stamp_2 = ai_mgr._create_context_stamp()
        
        self.assertNotEqual(stamp_1, stamp_2, "Context stamp must reflect movement.")

    def test_stale_result_discard(self):
        """Verify AI manager rejects text if context changed during 'thinking'."""
        ai_mgr = self.game.ai_manager
        
        # 1. Create a fake context from "Room A"
        old_context = ai_mgr._create_context_stamp()
        
        # 2. Move player to "Room B"
        self.player.current_room_id = "Room B"
        
        # 3. Push a result into the queue using the OLD context
        result_package = {
            "text": "The birds are singing in Room A.",
            "context_stamp": old_context,
            "duration": 1.0
        }
        ai_mgr.result_queue.put(result_package)
        
        # 4. Update and verify the result is NOT returned (discarded)
        # We call the modified update that returns the string
        # Note: In real manager, update() adds to renderer. We check the return.
        output = ai_mgr.update2() # Calling the debug version that returns str
        
        self.assertIsNone(output, "Stale AI text should be discarded.")

    def test_context_helpers_use_resolved_player_not_deprecated_world_player(self):
        ai_mgr = self.game.ai_manager

        region = Region("AI Region", "desc", obj_id="ai_region")
        room_a = Room("AI Room A", "a", obj_id="room_a")
        room_b = Room("AI Room B", "b", obj_id="room_b")
        region.add_room("room_a", room_a)
        region.add_room("room_b", room_b)
        self.world.add_region("ai_region", region)

        self.player.current_region_id = "ai_region"
        self.player.current_room_id = "room_a"

        other_player = Player("Other", obj_id="other_ai_player", world=self.world)
        other_player.world = self.world
        other_player.current_region_id = "ai_region"
        other_player.current_room_id = "room_b"
        self.world.players[other_player.obj_id] = other_player
        self.world.player = other_player

        npc = NPC(obj_id="ai_ctx_goblin", name="AI Context Goblin", description="A goblin.", friendly=False)
        npc.faction = "hostile"
        npc.current_region_id = "ai_region"
        npc.current_room_id = "room_a"
        self.world.add_npc(npc)

        stamp = ai_mgr._create_context_stamp()
        context_text = ai_mgr._gather_context_for_llm()

        self.assertEqual(("ai_region", "room_b"), stamp["location"])
        self.assertIn("AI Room B", context_text)
        self.assertNotIn("AI Context Goblin", context_text)
