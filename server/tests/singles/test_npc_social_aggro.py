# tests/singles/test_npc_social_aggro.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCSocialAggro(GameTestBase):

    def test_attacking_neutral_provokes_combat(self):
        """Verify a neutral NPC enters combat if attacked."""
        # 1. Create Neutral NPC
        self.world.npc_templates["monk"] = {
            "name": "Quiet Monk", "faction": "neutral", "health": 50,
            "attack_power": 5
        }
        monk = NPCFactory.create_npc_from_template("monk", self.world)
        
        if monk and self.player:
            self.world.add_npc(monk)
            # Colocate
            monk.current_region_id = self.player.current_region_id
            monk.current_room_id = self.player.current_room_id
            
            self.assertFalse(monk.in_combat)
            
            # 2. Player Attacks
            self.game.process_command("attack Quiet Monk")
            
            # 3. Assertions
            self.assertTrue(self.player.runtime_state.combat.in_combat)
            
            # The Monk should now target the player
            self.assertTrue(monk.in_combat, "Monk should act in self-defense.")
            self.assertIn(self.player, monk.combat_targets)
