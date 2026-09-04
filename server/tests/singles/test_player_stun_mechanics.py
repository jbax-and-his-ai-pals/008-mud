# tests/singles/test_player_stun_mechanics.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory

class TestPlayerStunMechanics(GameTestBase):

    def setUp(self):
        super().setUp()
        # FIX: Set target_type="self"
        self.spell = Spell("test_zap", "Zap", "x", mana_cost=0, cooldown=0, 
                          effects=[{"type": "damage", "value": 1}], level_required=1,
                          target_type="self")
        register_spell(self.spell)
        self.player.learn_spell("test_zap")

    def test_stun_prevents_actions(self):
        """Verify Stun effect prevents attacking and casting."""
        # 1. Apply Stun
        stun_effect = {
            "name": "Stun",
            "type": "control",
            "base_duration": 5.0
        }
        self.player.apply_effect(stun_effect, time.time())
        self.assertTrue(self.player.has_effect("Stun"))
        
        # 2. Attempt Attack
        # Need a target
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if target:
            self.world.add_npc(target)
            target.current_region_id = self.player.current_region_id
            target.current_room_id = self.player.current_room_id
            
            # Action
            result = self.player.attack(target, self.world)
            self.assertIn("stunned", result["message"].lower())
            
        # 3. Attempt Cast
        result_cast = self.player.cast_spell(self.spell, self.player, time.time(), self.world)
        self.assertFalse(result_cast["success"])
        self.assertIn("stunned", result_cast["message"].lower())
