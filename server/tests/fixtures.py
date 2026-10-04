# tests/fixtures.py
import unittest
import sys
import os
import tempfile
from typing import cast, List, Any

# Get the absolute path to the project root (one level up from tests/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FANTASY_FRONTIER = os.path.abspath(os.path.join(PROJECT_ROOT, '..', 'content_sets', 'fantasy_frontier'))
# A frozen copy of the FF4 slice for tests of engine features (see tests/sets/README.md): the real set is free to change.
from pathlib import Path as _Path
STORY_FIXTURE = _Path(PROJECT_ROOT) / 'tests' / 'sets' / 'story_fixture'

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
        
        # 2. Keep every test's mutable state outside authored content and production AppData.
        self._save_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._save_directory.cleanup)
        self.game = GameManager(
            FANTASY_FRONTIER,
            save_file="test_save.json",
            save_directory=self._save_directory.name,
        )
        
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


def skip_the_ff4_opening(world, player, place=("varenholt", "throne_room")):
    """Past the opening of the real FF4 slice (the Ilmara scene, the crystal, the airship, the landing), for the story
    tests that begin at the king: the player stands in `place` with the crystal, and no scene is still being told."""
    from engine.items.item_factory import ItemFactory

    world.scheduled_actions.clear()
    for key in [k for k in player.flags if isinstance(k, str) and k.startswith("_scene.")]:
        player.flags.pop(key)
    for scene in ("ilmara_falls", "leave_ilmara", "second_wave", "landing"):
        player.flags["_scene_done." + scene] = True
    player.flags["air_second_wave"] = True
    crystal = ItemFactory.create_item_from_template("item_ilmaran_crystal", world)
    if crystal is not None and player.inventory.get_item("item_ilmaran_crystal") is None:
        player.inventory.add_item(crystal, 1)
    player.current_region_id, player.current_room_id = place
