# tests/singles/test_minion_faction_safety.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import handle_ai

class TestMinionFactionSafety(GameTestBase):

    def test_minion_ignores_friendlies(self):
        """Verify minions do not attack friendly NPCs automatically."""
        # 1. Setup Scenario
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        
        if minion and villager and goblin:
            # Set ownership
            minion.properties["owner_id"] = self.player.obj_id
            
            # Co-locate everyone
            loc = ("town", "town_square")
            self.player.current_region_id, self.player.current_room_id = loc
            for npc in [minion, villager, goblin]:
                npc.current_region_id, npc.current_room_id = loc
                self.world.add_npc(npc)
                npc.last_moved = 0 # Reset cooldowns
            
            # 2. Act: Run Minion AI
            # Minion logic: "Proactively attack any hostile in the room"
            handle_ai(minion, self.world, time.time(), self.player)
            
            # 3. Assertions
            # Should target Goblin (Hostile)
            self.assertIn(goblin, minion.combat_targets, "Minion should target hostile goblin.")
            
            # Should NOT target Villager (Friendly)
            self.assertNotIn(villager, minion.combat_targets, "Minion should NOT target friendly villager.")