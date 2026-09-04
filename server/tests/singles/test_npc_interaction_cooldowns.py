# tests/singles/test_npc_interaction_cooldowns.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCInteractionCooldowns(GameTestBase):

    def test_attack_cooldown_enforcement(self):
        """Verify attacks are rejected if the cooldown hasn't elapsed."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            self.world.add_npc(target)
            target.current_region_id = self.player.current_region_id
            target.current_room_id = self.player.current_room_id
            
            # 1. Attack successfully
            self.game.process_command(f"attack {target.name}")
            last_time = self.player.last_attack_time
            self.assertGreater(last_time, 0)
            
            # 2. Attack immediately (Fail)
            # We don't simulate time passing here
            result = self.game.process_command(f"attack {target.name}")
            
            self.assertIsNotNone(result, "Command should return cooldown feedback.")
            if result:
                self.assertIn("Wait", result)
            
            # 3. Time Passes
            # Manually reset time to simulate passage
            self.player.last_attack_time = 0
            
            result_success = self.game.process_command(f"attack {target.name}")
            self.assertIsNotNone(result_success)
            if result_success:
                self.assertNotIn("Wait", result_success)