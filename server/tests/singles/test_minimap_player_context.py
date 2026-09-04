import unittest

import pygame

from engine.ui.minimap import draw_minimap
from engine.world.room import Room
from engine.world.region import Region


class _FakePlayer:
    def __init__(self, region_id: str, room_id: str) -> None:
        self.current_region_id = region_id
        self.current_room_id = room_id


class _FakeWorld:
    def __init__(self) -> None:
        self.player = None
        self.players = {}
        region = Region("Test Region", "desc", obj_id="r1")
        room_a = Room("A", "a", obj_id="a")
        room_b = Room("B", "b", obj_id="b")
        room_a.visited = True
        room_b.visited = True
        room_a.exits["east"] = "b"
        room_b.exits["west"] = "a"
        region.rooms["a"] = room_a
        region.rooms["b"] = room_b
        self.regions = {"r1": region}

    def get_region(self, region_id: str):
        return self.regions.get(region_id)

    def resolve_reference_player(self, player=None):
        if player is not None:
            return player
        if self.player is not None:
            return self.player
        if self.players:
            return next(iter(self.players.values()))
        return None


class TestMinimapPlayerContext(unittest.TestCase):
    def test_draw_minimap_with_explicit_player_without_world_player(self) -> None:
        pygame.init()
        try:
            surface = pygame.Surface((200, 200))
            rect = pygame.Rect(0, 0, 200, 200)
            world = _FakeWorld()
            player = _FakePlayer("r1", "a")
            draw_minimap(surface, rect, world, player=player)
        finally:
            pygame.quit()

    def test_draw_minimap_uses_resolved_player_without_world_player(self) -> None:
        pygame.init()
        try:
            surface = pygame.Surface((200, 200))
            rect = pygame.Rect(0, 0, 200, 200)
            world = _FakeWorld()
            world.players["p1"] = _FakePlayer("r1", "a")
            draw_minimap(surface, rect, world)
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
