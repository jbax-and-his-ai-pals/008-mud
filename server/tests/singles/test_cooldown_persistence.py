# tests/singles/test_cooldown_persistence.py
import os
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestCooldownPersistence(GameTestBase):
    
    TEST_SAVE = "test_cd_save.json"

    def setUp(self):
        super().setUp()
        # FIX: Set target_type="self"
        self.test_spell = Spell(
            spell_id="long_cooldown_spell", name="Big Bang", description="...",
            mana_cost=0, cooldown=1000.0, effects=[{"type": "damage", "value": 1}], level_required=1,
            target_type="self"
        )
        register_spell(self.test_spell)
        self.player.learn_spell("long_cooldown_spell")

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_cooldown_saves(self):
        """Verify cooldown timers are preserved across save/load."""
        # 1. Cast Spell
        now = time.time()
        result = self.player.cast_spell(self.test_spell, self.player, now)
        self.assertTrue(result["success"], "Cast should succeed setup")
        
        # Verify on cooldown
        can_cast, _ = self.player.can_cast_spell(self.test_spell, now + 1.0)
        self.assertFalse(can_cast)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Clear State
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.cooldowns = {}
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded_player = self.world.player
        
        # 5. Assert still on cooldown
        if loaded_player:
            # We simulate time being roughly the same
            can_cast_loaded, msg = loaded_player.can_cast_spell(self.test_spell, now + 5.0)
            self.assertFalse(can_cast_loaded, "Spell should still be on cooldown after load.")
            self.assertIn("cooldown", msg)
