import pygame

from engine.player.core import Player
from engine.ui.inventory_menu import InventoryMenu
from tests.fixtures import GameTestBase


class TestUIResolvedPlayerContext(GameTestBase):
    def setUp(self):
        super().setUp()
        fallback_player = Player("Fallback UI Hero", obj_id="fallback_ui_hero", data_root=self.world.data_root)
        fallback_player.world = self.world
        fallback_player.current_region_id = self.player.current_region_id
        fallback_player.current_room_id = self.player.current_room_id
        self.world.players[fallback_player.obj_id] = fallback_player

        # Simulate a state where no legacy singleton is bound, but a resolved
        # player still exists in the world's loaded-player registry.
        self.world._legacy_player_id = None
        self.fallback_player = fallback_player

    def test_inventory_menu_uses_resolved_player_when_world_player_missing(self):
        surface = pygame.Surface((400, 300))
        rect = pygame.Rect(0, 0, 400, 300)
        menu = InventoryMenu(self.game)
        menu.render(surface, rect)

    def test_renderer_uses_resolved_player_for_panel_context(self):
        self.game.renderer.draw()
