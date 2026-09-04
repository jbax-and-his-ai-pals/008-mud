# tests/singles/test_spell_target_defaults.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory

class TestSpellTargetDefaults(GameTestBase):

    def setUp(self):
        super().setUp()
        # Offensive Spell
        self.blast = Spell(
            spell_id="test_blast", 
            name="TestBlast", 
            description="Damage", 
            mana_cost=0, 
            target_type="enemy", 
            effects=[{"type": "damage", "value": 10}]
        )
        register_spell(self.blast)
        self.player.learn_spell("test_blast")
        
        # Defensive Spell
        self.heal = Spell(
            spell_id="test_heal", 
            name="TestHeal", 
            description="Heal", 
            mana_cost=0, 
            target_type="friendly", 
            effects=[{"type": "heal", "value": 10}]
        )
        register_spell(self.heal)
        self.player.learn_spell("test_heal")

    def test_offensive_default_target(self):
        """Verify offensive spell auto-targets a hostile in the room."""
        enemy = NPCFactory.create_npc_from_template("goblin", self.world)
        if enemy:
            self.world.add_npc(enemy)
            enemy.current_region_id = self.player.current_region_id
            enemy.current_room_id = self.player.current_room_id
            
            # Act: Cast without target using Name "TestBlast"
            result = self.game.process_command("cast TestBlast")
            
            # Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn(enemy.name, result)
                self.assertIn("hits", result)

    def test_defensive_default_target(self):
        """Verify defensive spell auto-targets self if no target given."""
        self.player.max_health = 100
        self.player.health = 50
        
        # Act: Cast using Name "TestHeal"
        result = self.game.process_command("cast TestHeal")
        
        # Assert
        self.assertIsNotNone(result)
        if result:
            # "You heal yourself" is the default self_heal_message in Spell class
            self.assertIn("heal yourself", result)
            self.assertGreater(self.player.health, 50)
