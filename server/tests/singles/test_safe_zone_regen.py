# tests/singles/test_safe_zone_regen.py
import time
from tests.fixtures import GameTestBase
from engine.config import PLAYER_REGEN_TICK_INTERVAL

class TestSafeZoneRegen(GameTestBase):

    def test_regen_in_safe_zone(self):
        """Verify stats regenerate when in a safe zone."""
        # 1. Setup Safe Zone
        region = self.world.get_region("town")
        if region:
            region.properties["safe_zone"] = True
            self.player.current_region_id = "town"
            self.player.current_room_id = "town_square"
            
            # Injure Player
            self.player.max_health = 100
            self.player.health = 50
            
            # 2. Advance Time
            now = time.time()
            self.player.last_mana_regen_time = now - PLAYER_REGEN_TICK_INTERVAL - 1
            
            self.player.update(now, 0.1)
            
            # 3. Assert
            self.assertGreater(self.player.health, 50)

    def test_no_regen_in_danger_zone(self):
        """Verify stats do not auto-regenerate in danger zones."""
        # 1. Setup Danger Zone
        region = self.world.get_region("town")
        if region:
            region.properties["safe_zone"] = False # Unsafe
            self.player.current_region_id = "town"
            
            self.player.health = 50
            self.player.max_health = 100
            
            # 2. Advance Time
            now = time.time()
            self.player.last_mana_regen_time = now - PLAYER_REGEN_TICK_INTERVAL - 1
            
            self.player.update(now, 0.1)
            
            # 3. Assert
            self.assertEqual(self.player.health, 50)