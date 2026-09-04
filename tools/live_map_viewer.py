# tools/live_map_viewer.py
import json
import argparse
import os
import sys
import pygame
from collections import deque
from typing import Dict, Any

# --- Configuration for Map Appearance ---
BOX_WIDTH = 180
BOX_HEIGHT = 70
H_SPACING = 60
V_SPACING = 50
BG_COLOR = (51, 51, 51)  # #333333
BOX_COLOR = (221, 221, 221) # #DDDDDD
START_BOX_COLOR = (144, 238, 144) # #90EE90
LINE_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)
ID_TEXT_COLOR = (102, 102, 102) # #666666
TITLE_COLOR = (255, 255, 255)
FONT_SIZE = 18
ID_FONT_SIZE = 12
TITLE_FONT_SIZE = 30

# --- Direction Vectors for Grid Placement ---
DIRECTION_VECTORS = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1),
    "up": (0, 0), "down": (0, 0), "in": (0, 0), "out": (0, 0), "enter": (0, 0), "exit": (0, 0)
}

class MapViewer:
    def __init__(self, region_json_path: str, start_room_id: str):
        self.region_data = self._load_region_data(region_json_path)
        self.start_room_id = start_room_id
        
        self.room_to_coords: Dict[str, tuple[int, int]] = {}
        self.min_x, self.max_x, self.min_y, self.max_y = 0, 0, 0, 0
        
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
        pygame.display.set_caption(f"Live Map Viewer - {self.region_data.get('name', 'Unknown Region')}")

        self.font = pygame.font.SysFont("Arial", FONT_SIZE)
        self.id_font = pygame.font.SysFont("Arial", ID_FONT_SIZE)
        self.title_font = pygame.font.SysFont("Arial", TITLE_FONT_SIZE, bold=True)

        # Camera controls
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.panning = False
        self.pan_start_pos = (0, 0)
        
        self._calculate_layout()
        self._center_view()

    def _load_region_data(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading region file: {e}", file=sys.stderr)
            sys.exit(1)

    def _calculate_layout(self):
        rooms = self.region_data.get("rooms", {})
        if self.start_room_id not in rooms:
            print(f"Error: Start room '{self.start_room_id}' not found in region.", file=sys.stderr)
            sys.exit(1)
            
        coords_to_room: Dict[tuple[int, int], str] = {}
        queue = deque([(self.start_room_id, (0, 0))])
        visited = {self.start_room_id}

        self.room_to_coords[self.start_room_id] = (0, 0)
        coords_to_room[(0, 0)] = self.start_room_id

        while queue:
            current_id, (cx, cy) = queue.popleft()
            
            for direction, destination in rooms.get(current_id, {}).get("exits", {}).items():
                dest_room_id = destination.split(":")[-1]
                if dest_room_id in rooms and dest_room_id not in visited:
                    visited.add(dest_room_id)
                    vector = DIRECTION_VECTORS.get(direction.lower(), (0, 0))
                    nx, ny = cx + vector[0], cy + vector[1]
                    
                    if (nx, ny) in coords_to_room:
                         print(f"Warning: Spatial collision between '{dest_room_id}' and '{coords_to_room[(nx, ny)]}' at ({nx}, {ny}). Check exits.", file=sys.stderr)

                    self.room_to_coords[dest_room_id] = (nx, ny)
                    coords_to_room[(nx, ny)] = dest_room_id
                    queue.append((dest_room_id, (nx, ny)))
        
        if not self.room_to_coords: return
        self.min_x = min(x for x, y in self.room_to_coords.values())
        self.max_x = max(x for x, y in self.room_to_coords.values())
        self.min_y = min(y for x, y in self.room_to_coords.values())
        self.max_y = max(y for x, y in self.room_to_coords.values())

    def _center_view(self):
        """Calculates the initial offset to center the entire map."""
        map_pixel_width = (self.max_x - self.min_x + 1) * (BOX_WIDTH + H_SPACING)
        map_pixel_height = (self.max_y - self.min_y + 1) * (BOX_HEIGHT + V_SPACING)
        self.offset_x = (self.screen.get_width() - map_pixel_width) / 2
        self.offset_y = (self.screen.get_height() - map_pixel_height) / 2


    def world_to_screen(self, grid_x: int, grid_y: int) -> tuple[float, float]:
        """Converts grid coordinates to screen pixel coordinates with zoom and pan."""
        base_x = (grid_x - self.min_x) * (BOX_WIDTH + H_SPACING)
        base_y = (grid_y - self.min_y) * (BOX_HEIGHT + V_SPACING)
        
        screen_x = (base_x * self.zoom) + self.offset_x
        screen_y = (base_y * self.zoom) + self.offset_y
        return screen_x, screen_y

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                self.handle_input(event)

            self.draw()
            pygame.display.flip()
        
        pygame.quit()

    def handle_input(self, event):
        if event.type == pygame.MOUSEWHEEL:
            zoom_delta = event.y * 0.1
            self.zoom = max(0.1, self.zoom + zoom_delta)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Left click
                self.panning = True
                self.pan_start_pos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.panning = False
        elif event.type == pygame.MOUSEMOTION:
            if self.panning:
                dx, dy = event.pos[0] - self.pan_start_pos[0], event.pos[1] - self.pan_start_pos[1]
                self.offset_x += dx
                self.offset_y += dy
                self.pan_start_pos = event.pos

    def draw(self):
        self.screen.fill(BG_COLOR)
        rooms = self.region_data.get("rooms", {})

        # Draw connections first (so they are behind the boxes)
        for room_id, (gx, gy) in self.room_to_coords.items():
            start_pos = self.world_to_screen(gx, gy)
            start_center = (start_pos[0] + BOX_WIDTH * self.zoom / 2, start_pos[1] + BOX_HEIGHT * self.zoom / 2)
            
            for direction, destination in rooms.get(room_id, {}).get("exits", {}).items():
                dest_room_id = destination.split(":")[-1]
                if dest_room_id in self.room_to_coords:
                    ngx, ngy = self.room_to_coords[dest_room_id]
                    end_pos = self.world_to_screen(ngx, ngy)
                    end_center = (end_pos[0] + BOX_WIDTH * self.zoom / 2, end_pos[1] + BOX_HEIGHT * self.zoom / 2)
                    pygame.draw.line(self.screen, LINE_COLOR, start_center, end_center, 1)

        # Draw room boxes and text
        for room_id, (gx, gy) in self.room_to_coords.items():
            px, py = self.world_to_screen(gx, gy)
            scaled_box_w = BOX_WIDTH * self.zoom
            scaled_box_h = BOX_HEIGHT * self.zoom
            
            fill = START_BOX_COLOR if room_id == self.start_room_id else BOX_COLOR
            room_rect = pygame.Rect(px, py, scaled_box_w, scaled_box_h)
            pygame.draw.rect(self.screen, fill, room_rect)
            pygame.draw.rect(self.screen, LINE_COLOR, room_rect, 1)

            # --- Text Rendering (only if zoom is large enough) ---
            if self.zoom > 0.3:
                room_name = rooms.get(room_id, {}).get("name", "Unknown")
                
                # Room Name
                name_surf = self.font.render(room_name, True, TEXT_COLOR)
                name_rect = name_surf.get_rect(center=(room_rect.centerx, room_rect.centery - 10 * self.zoom))
                self.screen.blit(name_surf, name_rect)

                # Room ID
                id_surf = self.id_font.render(room_id, True, ID_TEXT_COLOR)
                id_rect = id_surf.get_rect(center=(room_rect.centerx, room_rect.centery + 10 * self.zoom))
                self.screen.blit(id_surf, id_rect)

def main():
    parser = argparse.ArgumentParser(description="Live, interactive map viewer for game regions.")
    parser.add_argument("input_json", help="Path to the region's JSON file (e.g., data/regions/town.json).")
    parser.add_argument("--start-room", default="town_square", help="The ID of the room to start the layout from.")
    
    args = parser.parse_args()
    
    viewer = MapViewer(args.input_json, args.start_room)
    viewer.run()

if __name__ == "__main__":
    main()