# tests/singles/test_combat_mechanics.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestCombatMechanics(GameTestBase):
    
    def test_attack_cooldown(self):
        """Verify attacks are blocked during cooldown."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            self.world.add_npc(target)
            target.current_region_id = self.player.current_region_id
            target.current_room_id = self.player.current_room_id
            
            # 1. Attack
            self.player.attack(target, self.world)
            
            # 2. Immediate Follow-up (Should fail)
            result_fail = self.game.process_command(f"attack {target.name}")
            self.assertIsNotNone(result_fail)
            if result_fail:
                self.assertIn("Wait", result_fail)
                
            # 3. Wait for cooldown
            # Default cooldown is ~2.0s. Simulate waiting by adjusting last_attack_time.
            time_jump = self.player.get_effective_attack_cooldown() + 0.1
            self.player.last_attack_time = time.time() - time_jump
            
            result_success = self.game.process_command(f"attack {target.name}")
            self.assertIsNotNone(result_success)
            if result_success:
                self.assertNotIn("Wait", result_success)

    @patch('random.random', return_value=0.0) # Force Hit
    @patch('random.randint', return_value=10) # Force High Damage
    def test_combat_state_exit(self, mock_randint, mock_random):
        """Verify player exits combat state when target dies."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(target)
        
        if target:
            self.world.add_npc(target)
            target.current_region_id = self.player.current_region_id
            target.current_room_id = self.player.current_room_id
            
            # Weak target, Strong Player
            target.health = 1 
            self.player.runtime_state.combat.attack_power = 20 
            
            # Engage
            self.player.enter_combat(target)
            self.assertTrue(self.player.runtime_state.combat.in_combat)
            
            # Kill (Mocked RNG ensures hit and high damage)
            self.player.attack(target, self.world)
            
            # Assert
            self.assertFalse(target.is_alive, "Target should be dead after guaranteed hit.")
            self.assertFalse(self.player.runtime_state.combat.in_combat, "Player should exit combat after target death")

    def test_friendly_fire_prevention(self):
        """Verify you cannot attack friendly NPCs."""
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if villager:
            self.world.add_npc(villager)
            villager.current_region_id = self.player.current_region_id
            villager.current_room_id = self.player.current_room_id
            
            # Attempt Spell on Friendly
            self.player.learn_spell("magic_missile")
            
            result = self.game.process_command(f"cast magic missile on {villager.name}")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("hostile targets", result.lower())
