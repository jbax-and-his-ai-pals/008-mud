# tests/fixtures.py
import unittest
import sys
import os
from typing import cast, List, Any

# Get the absolute path to the project root (one level up from tests/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FANTASY_FRONTIER = os.path.abspath(os.path.join(PROJECT_ROOT, '..', 'content_sets', 'fantasy_frontier'))

# Insert root into sys.path so we can import 'engine'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.world.world import World
from engine.player.core import Player
from engine.core.game_manager import GameManager
from engine.ui.renderer import Renderer
from engine.items.inventory import Inventory
from engine.utils.logger import Logger, LogLevel


def make_test_server():
    """Factory for a deterministic HeadlessServer suitable for unit and soak tests."""
    from engine.server.headless_server import HeadlessServer
    server = HeadlessServer(
        save_file="test_save.json",
        db_path=":memory:",
        content_set_path=FANTASY_FRONTIER,
        deterministic_test_mode=True,
    )
    return server

class MockRenderer:
    """
    A dummy renderer that swallows messages so tests don't crash.
    """
    def __init__(self):
        self.message_buffer: List[str] = []
        self.layout = {
            "screen_width": 800, "screen_height": 600,
            "text_area": {"height": 400}
        }
        self.screen = None 
        # Support for visual juice testing
        self.floating_texts = []
    
    def add_message(self, message: str):
        self.message_buffer.append(message)
    
    def clear(self):
        self.message_buffer = []
        
    def scroll(self, amount):
        pass

    def draw(self):
        pass
    
    def get_zone_at_pos(self, pos):
        return None

    def add_floating_text(self, text, x, y, color):
        self.floating_texts.append(text)

class GameTestBase(unittest.TestCase):
    """Base class for all game tests."""
    
    _total_tests_run = 0

    def setUp(self):
        """Runs before EVERY test function."""
        # 1. Silence Logger
        Logger.set_level(LogLevel.CRITICAL)
        
        # 2. Create a dummy Game Manager (headless)
        self.game = GameManager(FANTASY_FRONTIER, save_file="test_save.json")
        
        # 3. Swap out the real renderer for a mock.
        self.game.renderer = MockRenderer() # type: ignore
        
        # 4. Initialize a fresh world
        self.game.world.initialize_new_world()
        self.world = self.game.world
        
        # 5. Handle Player safely
        if not self.world.player:
            self.fail("Player was not initialized in World.")
        self.player = cast(Player, self.world.player)
        
        # 6. Inject game reference
        self.world.game = self.game
        self.player.world = self.world
        
        # 7. RESET PLAYER STATE FOR TESTING
        self.player.inventory = Inventory(max_slots=20, max_weight=100.0)
        for slot in self.player.equipment:
            self.player.equipment[slot] = None

    def tearDown(self):
        if GameTestBase._total_tests_run % 50 == 0:
            sys.stderr.write(f"\n <{GameTestBase._total_tests_run}> ")
            sys.stderr.flush()
        GameTestBase._total_tests_run += 1

    def assertMessageContains(self, substring: str):
        """Custom helper to check if the game printed specific text."""
        mock = cast(MockRenderer, self.game.renderer)
        all_text = "\n".join(mock.message_buffer)
        self.assertIn(substring, all_text, f"Expected message '{substring}' not found in buffer.")
