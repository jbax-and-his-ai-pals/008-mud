# tests/singles/test_ai.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import handle_ai

class TestAI(GameTestBase):

    def setUp(self):
        super().setUp()
        self.world.npcs = {} # Clear world
        # Ensure player is in a valid spot
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

    def test_hostile_aggression(self):
        """Verify aggressive NPCs target the player."""
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.add_npc(goblin)
            goblin.current_region_id = "town"
            goblin.current_room_id = "town_square"
            goblin.aggression = 1.0 # Force attack
            
            # Act
            handle_ai(goblin, self.world, time.time(), self.player)
            
            # Assert
            self.assertTrue(goblin.in_combat, "Goblin should be in combat")
            self.assertIn(self.player, goblin.combat_targets, "Goblin should target player")

    def test_healer_behavior(self):
        """Verify healer NPCs target wounded allies."""
        healer = NPCFactory.create_npc_from_template("wandering_priest", self.world)
        ally = NPCFactory.create_npc_from_template("town_guard", self.world)
        
        if healer and ally:
            self.world.add_npc(healer)
            self.world.add_npc(ally)
            
            # Setup Location
            healer.current_region_id = "town"; healer.current_room_id = "town_square"
            ally.current_region_id = "town"; ally.current_room_id = "town_square"
            
            # Injure Ally
            ally.health = 10
            ally.max_health = 100
            
            # Ensure healer has mana and spells
            healer.mana = 100
            healer.spell_cooldowns = {}
            
            # Act
            result_msg = handle_ai(healer, self.world, time.time(), self.player)
            
            # Assert
            self.assertIsNotNone(result_msg)
            if result_msg:
                self.assertIn("heals", result_msg.lower())
            self.assertGreater(ally.health, 10, "Ally should be healed")

    def test_wander_movement(self):
        """Verify an NPC can move rooms."""
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc:
            self.world.add_npc(npc)
            
            # Must set to a real room with exits (e.g., Town Square)
            npc.current_region_id = "town"
            npc.current_room_id = "town_square"
            
            start_room = npc.current_room_id
            
            # Force movement
            npc.wander_chance = 1.0 
            npc.last_moved = 0 # Ensure cooldown is passed
            
            # Act
            handle_ai(npc, self.world, time.time() + 1.0, self.player)
            
            # Assert
            self.assertNotEqual(npc.current_room_id, start_room, "NPC should have moved from start room")
            self.assertIsNotNone(npc.current_room_id, "NPC should not be in None room")