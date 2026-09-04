# tests/singles/test_npc_schedule_combat.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import handle_ai
from engine.world.room import Room

class TestNPCScheduleCombat(GameTestBase):

    def test_combat_overrides_schedule(self):
        """Verify an NPC stops their schedule to fight."""
        # 1. Setup Environment (Ensure rooms exist for valid pathfinding)
        region = self.world.get_region("town")
        if not region: 
            self.fail("Town region not found")
            return

        # Ensure destination rooms exist so AI *could* move if not for combat
        if "market" not in region.rooms:
            region.add_room("market", Room("Market", "A market", obj_id="market"))
        if "home" not in region.rooms:
            region.add_room("home", Room("Home", "A home", {"east": "market"}, obj_id="home"))
            # Link back
            market = region.get_room("market")
            if market: market.exits["west"] = "home"

        # 2. Setup Scheduled NPC
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        self.assertIsNotNone(npc, "Failed to create NPC")
        
        if npc:
            self.world.add_npc(npc)
            
            # Setup Location
            npc.current_region_id = "town"
            npc.current_room_id = "home"
            
            # Give schedule to move to market at 12:00
            npc.behavior_type = "scheduled"
            npc.schedule = {
                "12": {"region_id": "town", "room_id": "market", "activity": "shopping"}
            }
            
            # Set time to 12:00
            self.game.time_manager.hour = 12
            npc.last_moved = 0 # Ensure move cooldown isn't blocking
            
            # 3. Setup Enemy & Combat
            enemy = NPCFactory.create_npc_from_template("goblin", self.world)
            self.assertIsNotNone(enemy, "Failed to create enemy")
            
            if enemy:
                enemy.current_region_id = "town"
                enemy.current_room_id = "home"
                enemy.health = 1000 # Ensure it survives the hit so combat doesn't end
                enemy.is_alive = True
                self.world.add_npc(enemy)
                
                # Engage
                npc.enter_combat(enemy)
                
                # Verify Pre-conditions
                self.assertTrue(npc.in_combat, "NPC failed to enter combat state.")
                self.assertIn(enemy, npc.combat_targets, "Enemy not in combat targets.")
                self.assertTrue(enemy.is_alive, "Enemy died before AI tick.")
                self.assertEqual(enemy.current_room_id, npc.current_room_id, "Room mismatch.")
                
                # 4. Act: Run AI
                # Should choose combat logic (priority), NOT movement logic
                handle_ai(npc, self.world, time.time(), self.player)
                
                # 5. Assert
                self.assertEqual(npc.current_room_id, "home", "NPC should not move while fighting.")
                self.assertTrue(npc.in_combat, "NPC should remain in combat.")