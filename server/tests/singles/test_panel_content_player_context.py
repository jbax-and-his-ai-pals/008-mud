import unittest
from unittest.mock import patch

import pygame

from engine.npcs.npc import NPC
from engine.player.core import Player
from engine.ui.panel_content import render_friendlies_content, render_hostiles_content
from engine.utils.text_formatter import ClickableZone
from engine.world.world import World
from engine.server.content_set import load_content_set
from tests.fixtures import FANTASY_FRONTIER


class TestPanelContentPlayerContext(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        content_set, issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(content_set, issues)
        self.world = World(content_set=content_set)
        self.world.initialize_new_world()

        self.player = Player("Panel Hero", obj_id="panel_hero", data_root=self.world.data_root)
        self.player.world = self.world
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.world.players[self.player.obj_id] = self.player

        self.other_player = Player("Other Panel Hero", obj_id="other_panel_hero", data_root=self.world.data_root)
        self.other_player.world = self.world
        self.other_player.current_region_id = "town"
        self.other_player.current_room_id = "market_square"
        self.world.players[self.other_player.obj_id] = self.other_player
        self.world.player = self.other_player

        hostile = NPC(obj_id="panel_hostile", name="Panel Goblin", description="A goblin.", friendly=False)
        hostile.faction = "hostile"
        hostile.health = 10
        hostile.max_health = 10
        hostile.current_region_id = "town"
        hostile.current_room_id = "town_square"
        self.world.add_npc(hostile)

        friendly = NPC(obj_id="panel_friendly", name="Panel Friend", description="A friend.", friendly=True)
        friendly.faction = "friendly"
        friendly.health = 10
        friendly.max_health = 10
        friendly.current_region_id = "town"
        friendly.current_room_id = "town_square"
        self.world.add_npc(friendly)

    def tearDown(self) -> None:
        pygame.quit()

    def test_render_hostiles_uses_explicit_player_room(self) -> None:
        surface = pygame.Surface((300, 200))
        hotspots: list[ClickableZone] = []
        captured_commands: list[str] = []

        def _capture(*args, **kwargs):
            captured_commands.append(args[6])
            return args[4] + 16

        with patch("engine.ui.panel_content._draw_clickable_text", side_effect=_capture):
            render_hostiles_content(surface, {"world": self.world, "player": self.player}, hotspots)

        self.assertIn("attack Panel Goblin", captured_commands)

    def test_render_friendlies_uses_explicit_player_room(self) -> None:
        surface = pygame.Surface((300, 200))
        hotspots: list[ClickableZone] = []

        render_friendlies_content(surface, {"world": self.world, "player": self.player}, hotspots)

        commands = [zone.command for zone in hotspots]
        self.assertIn("look Panel Friend", commands)


if __name__ == "__main__":
    unittest.main()
