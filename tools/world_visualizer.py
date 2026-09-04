# tools/world_visualizer.py
import json
import argparse
import os
import sys
import pygame
import math
from collections import deque
from typing import Dict, Any, List, Tuple

# --- Main Appearance Configuration ---
BOX_WIDTH, BOX_HEIGHT = 200, 80
H_SPACING, V_SPACING = 70, 60
BG_COLOR = (51, 51, 51)
LINE_COLOR, TEXT_COLOR, ID_TEXT_COLOR, TITLE_COLOR = (255, 255, 255), (0, 0, 0), (102, 102, 102), (255, 255, 255)
FONT_SIZE, ID_FONT_SIZE, TITLE_FONT_SIZE, STUB_FONT_SIZE = 18, 12, 24, 11
BOX_COLOR, START_BOX_COLOR = (221, 221, 221), (144, 238, 144)

# --- Nested Layout Appearance ---
NESTED_SCALE_FACTOR = 0.6  # Interiors are 60% of the size
NESTED_LINE_COLOR = (200, 200, 0) # Yellow for in/out connections
NESTED_BG_COLOR = (70, 70, 70, 150) # Semi-transparent dark grey for interior background
EXTERNAL_LINE_COLOR = (255, 100, 100)

# --- Geometric Vectors ---
DIRECTION_VECTORS = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1)
}
NESTING_DIRECTIONS = {"in", "enter", "down"}
UNNESTING_DIRECTIONS = {"out", "exit", "up"}

def draw_dashed_line(surface, color, start_pos, end_pos, width=1, dash_length=5):
    """Simple function to draw a dashed line in Pygame."""
    x1, y1 = start_pos
    x2, y2 = end_pos
    dl = dash_length
    if (x1 == x2 and y1 == y2): return

    dx, dy = x2 - x1, y2 - y1
    distance = math.hypot(dx, dy)
    if distance == 0: return
    dashes = int(distance / dl)

    for i in range(dashes // 2 + 1):
        start = (x1 + (dx * i * 2 * dl) / distance, y1 + (dy * i * 2 * dl) / distance)
        end = (x1 + (dx * (i * 2 + 1) * dl) / distance, y1 + (dy * (i * 2 + 1) * dl) / distance)
        pygame.draw.line(surface, color, start, end, width)

class WorldVisualizer:
    def __init__(self, regions_dir: str):
        pygame.init()
        self.screen = pygame.display.set_mode((1800, 1000), pygame.RESIZABLE)
        pygame.display.set_caption("Interactive World Map Visualizer")
        
        self.font = pygame.font.SysFont("Arial", FONT_SIZE)
        self.id_font = pygame.font.SysFont("Arial", ID_FONT_SIZE)
        self.title_font = pygame.font.SysFont("Arial", TITLE_FONT_SIZE, bold=True)
        self.stub_font = pygame.font.SysFont("Arial", STUB_FONT_SIZE)

        self.regions_data = self._load_all_regions(regions_dir)
        
        self.region_layouts: Dict[str, Dict[str, Any]] = {}
        self.region_offsets: Dict[str, List[float]] = {}
        self.region_bounding_boxes: Dict[str, pygame.Rect] = {}
        
        self.zoom = 0.5
        self.offset_x, self.offset_y = 0.0, 0.0
        self.panning, self.dragging_region_id = False, None
        
        self._calculate_all_layouts()
        self._initial_region_placement()
        self._center_view()

    def _load_all_regions(self, path: str) -> Dict[str, Any]:
        regions = {}
        if not os.path.isdir(path):
            print(f"Error: Directory not found at '{path}'", file=sys.stderr)
            sys.exit(1)
        for filename in os.listdir(path):
            if filename.endswith(".json"):
                region_id = filename[:-5]
                file_path = os.path.join(path, filename)
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        if "rooms" in data and isinstance(data["rooms"], dict):
                            regions[region_id] = data
                        else:
                            print(f"Info: Skipping non-region JSON file: {filename}")
                except Exception as e:
                    print(f"Warning: Could not load or parse {filename}: {e}", file=sys.stderr)
        return regions

    def _calculate_all_layouts(self):
        for region_id, region_data in self.regions_data.items():
            rooms = region_data.get("rooms", {})
            start_room_id = next(iter(rooms), None)
            if not start_room_id: continue

            main_rooms: Dict[str, Tuple[float, float]] = {}
            portals_to_process: List[Tuple[str, str, str]] = []
            
            queue: deque[Tuple[str, Tuple[float, float]]] = deque([(start_room_id, (0, 0))])
            visited = {start_room_id}
            main_rooms[start_room_id] = (0, 0)
            
            while queue:
                current_id, (cx, cy) = queue.popleft()
                for direction, dest in rooms.get(current_id, {}).get("exits", {}).items():
                    if direction.lower() in DIRECTION_VECTORS:
                        dest_id = dest.split(":")[-1]
                        if dest.startswith(region_id) or ":" not in dest:
                            if dest_id in rooms and dest_id not in visited:
                                visited.add(dest_id)
                                vec = DIRECTION_VECTORS[direction.lower()]
                                nx, ny = cx + vec[0], cy + vec[1]
                                main_rooms[dest_id] = (nx, ny)
                                queue.append((dest_id, (nx, ny)))
                    elif direction.lower() in NESTING_DIRECTIONS:
                        portals_to_process.append((current_id, direction, dest))

            nested_groups: Dict[str, Any] = {}
            all_placed_rooms = set(main_rooms.keys())

            for parent_id, direction, dest in portals_to_process:
                dest_id = dest.split(":")[-1]
                if (dest.startswith(region_id) or ":" not in dest) and dest_id in rooms and dest_id not in all_placed_rooms:
                    nested_layout = {"parent_id": parent_id, "entry_direction": direction, "rooms": {}}
                    nested_queue: deque[Tuple[str, Tuple[float, float]]] = deque([(dest_id, (0, 0))])
                    visited_nested = {dest_id}
                    nested_layout["rooms"][dest_id] = (0, 0)
                    all_placed_rooms.add(dest_id)

                    while nested_queue:
                        curr_nested_id, (ncx, ncy) = nested_queue.popleft()
                        for nested_dir, nested_dest in rooms.get(curr_nested_id, {}).get("exits", {}).items():
                            if nested_dir.lower() in DIRECTION_VECTORS:
                                nested_dest_id = nested_dest.split(":")[-1]
                                if (nested_dest.startswith(region_id) or ":" not in nested_dest) and nested_dest_id in rooms and nested_dest_id not in visited_nested:
                                    visited_nested.add(nested_dest_id)
                                    all_placed_rooms.add(nested_dest_id)
                                    vec = DIRECTION_VECTORS[nested_dir.lower()]
                                    nnx, nny = ncx + vec[0], ncy + vec[1]
                                    nested_layout["rooms"][nested_dest_id] = (nnx, nny)
                                    nested_queue.append((nested_dest_id, (nnx, nny)))
                    nested_groups[dest_id] = nested_layout

            min_gx = min((r[0] for r in main_rooms.values()), default=0)
            max_gx = max((r[0] for r in main_rooms.values()), default=0)
            min_gy = min((r[1] for r in main_rooms.values()), default=0)
            max_gy = max((r[1] for r in main_rooms.values()), default=0)

            self.region_layouts[region_id] = {
                "main_rooms": main_rooms, "nested_groups": nested_groups,
                "bounds": (min_gx, max_gx, min_gy, max_gy)
            }

    def _initial_region_placement(self):
        sorted_regions = sorted(self.region_layouts.keys())
        cols = int(math.sqrt(len(sorted_regions))) + 1
        current_x_offset, current_y_offset = 0.0, 0.0
        max_height_in_row = 0.0

        for i, region_id in enumerate(sorted_regions):
            layout = self.region_layouts[region_id]
            min_gx, max_gx, min_gy, max_gy = layout["bounds"]
            width = (max_gx - min_gx + 2) * (BOX_WIDTH + H_SPACING)
            height = (max_gy - min_gy + 2) * (BOX_HEIGHT + V_SPACING)

            self.region_offsets[region_id] = [current_x_offset, current_y_offset]
            max_height_in_row = max(max_height_in_row, height)
            current_x_offset += width

            if (i + 1) % cols == 0:
                current_x_offset = 0
                current_y_offset += max_height_in_row
                max_height_in_row = 0

    def _center_view(self):
        self.offset_x = self.screen.get_width() / 4
        self.offset_y = self.screen.get_height() / 4

    def _update_bounding_boxes(self):
        self.region_bounding_boxes.clear()
        for region_id, layout in self.region_layouts.items():
            min_gx, max_gx, min_gy, max_gy = layout["bounds"]
            start_px, start_py = self.world_to_screen_main(region_id, min_gx, min_gy)
            end_px, end_py = self.world_to_screen_main(region_id, max_gx, max_gy)
            width = (end_px - start_px) + BOX_WIDTH * self.zoom
            height = (end_py - start_py) + BOX_HEIGHT * self.zoom
            padding = 20 * self.zoom
            self.region_bounding_boxes[region_id] = pygame.Rect(
                start_px - padding, start_py - padding,
                width + padding * 2, height + padding * 2
            )

    def world_to_screen_main(self, region_id: str, grid_x: float, grid_y: float) -> tuple[float, float]:
        layout = self.region_layouts[region_id]
        min_gx, _, min_gy, _ = layout["bounds"]
        region_offset_x, region_offset_y = self.region_offsets[region_id]
        base_x = (grid_x - min_gx) * (BOX_WIDTH + H_SPACING) + region_offset_x
        base_y = (grid_y - min_gy) * (BOX_HEIGHT + V_SPACING) + region_offset_y
        return (base_x * self.zoom) + self.offset_x, (base_y * self.zoom) + self.offset_y

    def get_screen_pos(self, region_id: str, room_id: str) -> Tuple[float, float] | None:
        layout = self.region_layouts.get(region_id)
        if not layout: return None

        if room_id in layout["main_rooms"]:
            gx, gy = layout["main_rooms"][room_id]
            return self.world_to_screen_main(region_id, gx, gy)
        
        for group_data in layout["nested_groups"].values():
            if room_id in group_data["rooms"]:
                parent_pos = self.get_screen_pos(region_id, group_data["parent_id"])
                if not parent_pos: return None
                
                parent_center_x = parent_pos[0] + (BOX_WIDTH * self.zoom / 2)
                parent_center_y = parent_pos[1] + (BOX_HEIGHT * self.zoom / 2)
                
                lgx, lgy = group_data["rooms"][room_id]
                scaled_h_spacing = (BOX_WIDTH + H_SPACING) * NESTED_SCALE_FACTOR * self.zoom
                scaled_v_spacing = (BOX_HEIGHT + V_SPACING) * NESTED_SCALE_FACTOR * self.zoom

                # The group's (0,0) point (entry room) is centered on the parent
                final_x = parent_center_x + (lgx * scaled_h_spacing)
                final_y = parent_center_y + (lgy * scaled_v_spacing)
                return final_x, final_y
        return None

    def run(self):
        running = True
        clock = pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                self.handle_input(event)
            self._update_bounding_boxes()
            self.draw()
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()

    def handle_input(self, event):
        if event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            zoom_delta = event.y * 0.1
            old_zoom = self.zoom
            self.zoom = max(0.1, self.zoom + zoom_delta)
            self.offset_x = mouse_pos[0] - (mouse_pos[0] - self.offset_x) * (self.zoom / old_zoom)
            self.offset_y = mouse_pos[1] - (mouse_pos[1] - self.offset_y) * (self.zoom / old_zoom)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for region_id, rect in self.region_bounding_boxes.items():
                if rect.collidepoint(event.pos):
                    self.dragging_region_id = region_id
                    break
            else:
                self.panning = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.panning = False
            self.dragging_region_id = None
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_region_id:
                dx, dy = event.rel
                self.region_offsets[self.dragging_region_id][0] += dx / self.zoom
                self.region_offsets[self.dragging_region_id][1] += dy / self.zoom
            elif self.panning:
                dx, dy = event.rel
                self.offset_x += dx
                self.offset_y += dy

    def draw(self):
        self.screen.fill(BG_COLOR)
        for region_id, region_data in self.regions_data.items():
            layout = self.region_layouts[region_id]
            rooms = region_data.get("rooms", {})

            all_rooms_in_region = list(layout["main_rooms"].keys())
            for group in layout["nested_groups"].values(): all_rooms_in_region.extend(group["rooms"].keys())
            
            # Draw Connections first
            for room_id in all_rooms_in_region:
                start_pos = self.get_screen_pos(region_id, room_id)
                if not start_pos: continue
                is_nested = room_id not in layout["main_rooms"]
                scale = NESTED_SCALE_FACTOR if is_nested else 1.0
                start_center = (start_pos[0] + BOX_WIDTH * self.zoom * scale / 2, start_pos[1] + BOX_HEIGHT * self.zoom * scale / 2)

                for direction, dest in rooms.get(room_id, {}).get("exits", {}).items():
                    dest_region, dest_room = dest.split(":") if ":" in dest else (region_id, dest)
                    if dest_region != region_id: # External stub
                        vec = DIRECTION_VECTORS.get(direction.lower(), (1, 0))
                        stub_end = (start_center[0] + 50 * self.zoom * vec[0], start_center[1] + 50 * self.zoom * vec[1])
                        pygame.draw.line(self.screen, EXTERNAL_LINE_COLOR, start_center, stub_end, 2)
                        if self.zoom > 0.4:
                            text_surf = self.stub_font.render(f"to: {dest}", True, EXTERNAL_LINE_COLOR)
                            self.screen.blit(text_surf, (stub_end[0] + 5, stub_end[1] - 5))
                    elif dest_room in all_rooms_in_region:
                        end_pos = self.get_screen_pos(region_id, dest_room)
                        if not end_pos: continue
                        end_is_nested = dest_room not in layout["main_rooms"]
                        end_scale = NESTED_SCALE_FACTOR if end_is_nested else 1.0
                        end_center = (end_pos[0] + BOX_WIDTH*self.zoom*end_scale/2, end_pos[1] + BOX_HEIGHT*self.zoom*end_scale/2)
                        
                        if direction.lower() in NESTING_DIRECTIONS or direction.lower() in UNNESTING_DIRECTIONS:
                            draw_dashed_line(self.screen, NESTED_LINE_COLOR, start_center, end_center, width=2)
                        else:
                            pygame.draw.line(self.screen, LINE_COLOR, start_center, end_center, 1)
            
            # Draw Nested Group Backgrounds
            for group_data in layout["nested_groups"].values():
                room_positions = [self.get_screen_pos(region_id, rid) for rid in group_data["rooms"]]
                valid_pos = [p for p in room_positions if p]
                if not valid_pos: continue
                
                scale = NESTED_SCALE_FACTOR * self.zoom
                min_px = min(p[0] for p in valid_pos)
                max_px = max(p[0] for p in valid_pos) + BOX_WIDTH * scale
                min_py = min(p[1] for p in valid_pos)
                max_py = max(p[1] for p in valid_pos) + BOX_HEIGHT * scale
                
                padding = 15 * self.zoom
                bg_rect = pygame.Rect(min_px - padding, min_py - padding, (max_px - min_px) + padding * 2, (max_py - min_py) + padding * 2)
                bg_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
                bg_surf.fill(NESTED_BG_COLOR)
                self.screen.blit(bg_surf, bg_rect.topleft)

            # Draw Region Title
            if self.zoom > 0.2:
                title_surf = self.title_font.render(region_data.get("name"), True, TITLE_COLOR)
                title_pos = self.world_to_screen_main(region_id, layout["bounds"][0], layout["bounds"][2] - 1)
                self.screen.blit(title_surf, title_pos)

            # Draw Room Boxes and Text
            for room_id in all_rooms_in_region:
                pos = self.get_screen_pos(region_id, room_id)
                if not pos: continue
                is_nested = room_id not in layout["main_rooms"]
                scale = NESTED_SCALE_FACTOR if is_nested else 1.0
                
                rect = pygame.Rect(pos[0], pos[1], BOX_WIDTH * self.zoom * scale, BOX_HEIGHT * self.zoom * scale)
                fill = START_BOX_COLOR if room_id == "town_square" else BOX_COLOR
                pygame.draw.rect(self.screen, fill, rect)
                pygame.draw.rect(self.screen, LINE_COLOR, rect, 1)

                if self.zoom * scale > 0.3:
                    room_name = rooms.get(room_id, {}).get("name", "Unknown")
                    font = self.font if not is_nested else pygame.font.SysFont("Arial", int(FONT_SIZE * 0.9))
                    id_font = self.id_font if not is_nested else pygame.font.SysFont("Arial", int(ID_FONT_SIZE * 0.9))
                    name_surf = font.render(room_name, True, TEXT_COLOR)
                    self.screen.blit(name_surf, (pos[0] + 5 * scale, pos[1] + 5 * scale))
                    id_surf = id_font.render(room_id, True, ID_TEXT_COLOR)
                    self.screen.blit(id_surf, (pos[0] + 5 * scale, pos[1] + 25 * scale))

def main():
    parser = argparse.ArgumentParser(description="Live, interactive world map viewer for all game regions.")
    parser.add_argument("regions_dir", help="Path to the directory containing all region JSON files (e.g., data/regions).")
    args = parser.parse_args()
    viewer = WorldVisualizer(args.regions_dir)
    viewer.run()

if __name__ == "__main__":
    main()