# tests/singles/test_spell_learning_limits.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestSpellLearningLimits(GameTestBase):
    
    def setUp(self):
        super().setUp()
        # Register a high-level test spell
        self.high_level_spell = Spell(
            spell_id="ultimate_doom",
            name="Ultimate Doom",
            description="End game.",
            mana_cost=100,
            level_required=50, # High requirement
            effects=[{"type": "damage", "value": 1000}]
        )
        register_spell(self.high_level_spell)

    def test_level_requirement_learning(self):
        """Verify players cannot learn spells above their level."""
        assert self.player.runtime_state.progression is not None
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.progression.level = 1
        
        # 1. Attempt Learn
        success, msg = self.player.learn_spell("ultimate_doom")
        
        self.assertFalse(success)
        self.assertIn("lack the experience", msg)
        self.assertNotIn("ultimate_doom", self.player.runtime_state.magic.known_spells)
        
        # 2. Level Up
        self.player.runtime_state.progression.level = 50
        
        # 3. Attempt Learn Again
        success, msg = self.player.learn_spell("ultimate_doom")
        self.assertTrue(success)
        self.assertIn("ultimate_doom", self.player.runtime_state.magic.known_spells)

    def test_mana_requirement_casting(self):
        """Verify players cannot cast spells if mana is insufficient."""
        # Setup: Learn spell, but have low mana
        assert self.player.runtime_state.progression is not None
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.progression.level = 50
        self.player.learn_spell("ultimate_doom") # Cost 100
        self.player.runtime_state.magic.mana = 10
        self.player.runtime_state.magic.max_mana = 200
        
        # Act
        can_cast, msg = self.player.can_cast_spell(self.high_level_spell, time.time())
        
        # Assert
        self.assertFalse(can_cast)
        self.assertIn("Not enough mana", msg)
        
        # Restore Mana
        self.player.runtime_state.magic.mana = 100
        can_cast, msg = self.player.can_cast_spell(self.high_level_spell, time.time())
        self.assertTrue(can_cast)
