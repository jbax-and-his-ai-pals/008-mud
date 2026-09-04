# tests/singles/test_magic.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestMagic(GameTestBase):
    def setUp(self):
        super().setUp()
        # Register a unique test spell to ensure consistent data independent of json files
        self.test_spell = Spell(
            spell_id="unit_test_fireball",
            name="Test Fireball",
            description="Goes boom.",
            mana_cost=10,
            cooldown=5.0,
            effects=[{"type": "damage", "value": 20}],
            target_type="enemy",
            level_required=1
        )
        register_spell(self.test_spell)

    def test_learn_and_forget_spell(self):
        """Verify spellbook management."""
        assert self.player.runtime_state.progression is not None
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.progression.level = 1
        
        # Learn
        success, msg = self.player.learn_spell("unit_test_fireball")
        self.assertTrue(success, f"Failed to learn spell: {msg}")
        self.assertIn("unit_test_fireball", self.player.runtime_state.magic.known_spells)

        # Duplicate Learn
        success, msg = self.player.learn_spell("unit_test_fireball")
        self.assertFalse(success, "Should not be able to learn known spell")

        # Forget
        self.assertTrue(self.player.forget_spell("unit_test_fireball"))
        self.assertNotIn("unit_test_fireball", self.player.runtime_state.magic.known_spells)

    def test_cast_requirements(self):
        """Verify mana and level checks."""
        self.player.learn_spell("unit_test_fireball")
        
        # Test Mana
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 5 # Needs 10
        can_cast, msg = self.player.can_cast_spell(self.test_spell, time.time())
        self.assertFalse(can_cast)
        self.assertIn("mana", msg.lower())

        # Success case
        self.player.runtime_state.magic.mana = 20
        can_cast, msg = self.player.can_cast_spell(self.test_spell, time.time())
        self.assertTrue(can_cast)

    def test_cooldowns(self):
        """Verify cooldown timers block casting."""
        self.player.learn_spell("unit_test_fireball")
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 50
        
        now = time.time()
        # Manually set cooldown
        self.player.runtime_state.magic.cooldowns["unit_test_fireball"] = now + 5.0
        
        # Check during cooldown
        can_cast, msg = self.player.can_cast_spell(self.test_spell, now + 1.0)
        self.assertFalse(can_cast, "Should be on cooldown")
        self.assertIn("cooldown", msg)
        
        # Check after cooldown
        can_cast, msg = self.player.can_cast_spell(self.test_spell, now + 6.0)
        self.assertTrue(can_cast, "Cooldown should have expired")
