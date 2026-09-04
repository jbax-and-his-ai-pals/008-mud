# engine/ui/minimap.py
import pygame
from typing import Dict, Tuple, Set, Optional, TYPE_CHECKING

from engine.config import FORMAT_RESET, TEXT_COLOR, FORMAT_HIGHLIGHT

DIRECTION_VECTORS = {
    "north": (0, -1), "n": (0, -1),
    "south": (0, 1),  "s": (0, 1),
    "east": (1, 0),   "e": (1, 0),
    "west": (-1, 0),  "w": (-1, 0),
    "northeast": (1, -1), "ne": (1, -1),
    "northwest": (-1, -1), "nw": (-1, -1),
    "southeast": (1, 1), "se": (1, 1),
    "southwest": (-1, 1), "sw": (-1, 1)
}

# Colors
MAP_ROOM_COLOR = (100, 100, 120)
MAP_CURRENT_ROOM_COLOR = (200, 200, 100)
MAP_CONNECTION_COLOR = (80, 80, 80)
MAP_VISITED_COLOR = (50, 50, 60)

# Settings
ROOM_SIZE = 20
CONNECTION_LENGTH = 20
MAP_RADIUS = 3 

if TYPE_CHECKING:
    from engine.world.world import World
    from engine.player import Player

def draw_minimap(
    surface: pygame.Surface,
    rect: pygame.Rect,
    world: 'World',
    player: Optional['Player'] = None,
):
    """
    Draws a visual representation of the local area within the given rect.
    Adapted to render onto a panel surface.
    """
    resolver = getattr(world, "resolve_reference_player", None)
    if callable(resolver):
        active_player = resolver(player)
    else:
        active_player = player or getattr(world, "player", None)
    if not active_player or not active_player.current_region_id or not active_player.current_room_id:
        return

    current_region = world.get_region(active_player.current_region_id)
    if not current_region: return

    # 1. BFS to gather rooms relative to player (0,0)
    grid_map: Dict[Tuple[int, int], str] = {}
    
    # Queue: (room_id, x, y, depth)
    queue = [(active_player.current_room_id, 0, 0, 0)]
    grid_map[(0, 0)] = active_player.current_room_id
    
    rooms_to_draw = [] 
    connections_to_draw = [] 
    processed_ids = {active_player.current_room_id}

    while queue:
        curr_id, cx, cy, depth = queue.pop(0)
        curr_room = current_region.get_room(curr_id)
        if not curr_room: continue

        is_current = (curr_id == active_player.current_room_id)
        rooms_to_draw.append((cx, cy, curr_room, is_current))
        
        if depth >= MAP_RADIUS: continue

        for direction, dest_str in curr_room.exits.items():
            d_key = direction.lower()
            if d_key not in DIRECTION_VECTORS: continue

            vec = DIRECTION_VECTORS[d_key]
            if ":" in dest_str:
                dest_region_id, dest_room_id = dest_str.split(":")
                if dest_region_id != active_player.current_region_id: continue
            else:
                dest_room_id = dest_str

            nx, ny = cx + vec[0], cy + vec[1]
            connections_to_draw.append((cx, cy, nx, ny))

            if dest_room_id not in processed_ids:
                processed_ids.add(dest_room_id)
                if curr_room.visited:
                    queue.append((dest_room_id, nx, ny, depth + 1))
                    grid_map[(nx, ny)] = dest_room_id

    # 2. Calculate Center Offset
    # We center (0,0) in the middle of the provided rect
    center_x = rect.width // 2
    center_y = rect.height // 2
    
    grid_unit = ROOM_SIZE + CONNECTION_LENGTH

    # 3. Draw Connections
    for (sx, sy, ex, ey) in connections_to_draw:
        start_pos = (center_x + sx * grid_unit, center_y + sy * grid_unit)
        end_pos = (center_x + ex * grid_unit, center_y + ey * grid_unit)
        pygame.draw.line(surface, MAP_CONNECTION_COLOR, start_pos, end_pos, 2)

    # 4. Draw Rooms
    for (rx, ry, room_obj, is_current) in rooms_to_draw:
        screen_x = center_x + rx * grid_unit
        screen_y = center_y + ry * grid_unit
        
        room_rect = pygame.Rect(0, 0, ROOM_SIZE, ROOM_SIZE)
        room_rect.center = (screen_x, screen_y)
        
        if not rect.contains(room_rect): continue

        color = MAP_CURRENT_ROOM_COLOR if is_current else MAP_ROOM_COLOR
        if not room_obj.visited and not is_current:
            color = MAP_VISITED_COLOR

        pygame.draw.rect(surface, color, room_rect)
        pygame.draw.rect(surface, (0,0,0), room_rect, 1) 

        if room_obj.items:
            pygame.draw.circle(surface, (255, 215, 0), room_rect.center, 2)
