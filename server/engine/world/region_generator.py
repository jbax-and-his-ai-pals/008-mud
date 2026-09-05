# engine/world/region_generator.py
import json
import os
import random
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.world.region import Region
from engine.world.room import Room
from engine.utils.logger import Logger

if TYPE_CHECKING:
    from engine.world.world import World

class RegionGenerator:
    def __init__(self, world: "World"):
        self.world = world
        self.themes: Dict[str, Any] = {}
        self.placeholders: Dict[str, List[str]] = {}
        self.load_themes()

    def load_themes(self):
        """Loads region generation themes and placeholders from a JSON file."""
        theme_path = os.path.join(self.world.content_root, "regions", "dynamic_themes.json")
        try:
            with open(theme_path, 'r') as f:
                data = json.load(f)
                self.themes = data.get("themes", {})
                self.placeholders = data.get("placeholders", {})
        except FileNotFoundError:
            Logger.error("RegionGenerator", f"Dynamic theme file not found at '{theme_path}'.")
        except json.JSONDecodeError:
            Logger.error("RegionGenerator", f"Could not decode JSON from '{theme_path}'.")

    def _format_with_placeholders(self, text: str) -> str:
        for key, words in self.placeholders.items():
            if f"{{{key.capitalize()}}}" in text:
                text = text.replace(f"{{{key.capitalize()}}}", random.choice(words).capitalize())
            if f"{{{key.lower()}}}" in text:
                text = text.replace(f"{{{key.lower()}}}", random.choice(words).lower())
        return text

    def generate_region(self, theme_name: str, num_rooms: int) -> Optional[Tuple[Region, str]]:
        theme = self.themes.get(theme_name)
        if not theme:
            Logger.error("RegionGenerator", f"Theme '{theme_name}' not found.")
            return None

        # ... (Rest of logic unchanged) ...
        direction_vectors = {
            "north": (0, -1, 0), "south": (0, 1, 0), "east": (1, 0, 0), "west": (-1, 0, 0),
            "northeast": (1, -1, 0), "northwest": (-1, -1, 0), "southeast": (1, 1, 0), "southwest": (-1, 1, 0),
            "up": (0, 0, 1), "down": (0, 0, -1)
        }
        opposite_direction = {
            "north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast", "northwest": "southeast", "southeast": "northwest",
            "up": "down", "down": "up"
        }
        planar_directions = ["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest"]
        vertical_directions = ["up", "down"]

        coords_to_id: Dict[Tuple[int, int, int], str] = {}
        id_to_coords: Dict[str, Tuple[int, int, int]] = {}
        rooms_data: Dict[str, Any] = {}
        
        region_id = f"dynamic_{theme_name}_{uuid.uuid4().hex[:6]}"
        region_name = self._format_with_placeholders(random.choice(theme.get("name_templates", ["A Mysterious Place"])))
        new_region = Region(name=region_name, description=theme.get("description", ""), obj_id=region_id)
        new_region.spawner_config = theme.get("spawner", {})

        entry_room_id = f"room_entry"
        coords_to_id[(0, 0, 0)] = entry_room_id
        id_to_coords[entry_room_id] = (0, 0, 0)
        rooms_data[entry_room_id] = { "name": "Entrance", "exits": {} }
        frontier = [entry_room_id]

        for i in range(1, num_rooms):
            new_room_id = f"room_{i}"
            connection_made = False
            random.shuffle(frontier)
            for current_room_id in frontier:
                cx, cy, cz = id_to_coords[current_room_id]
                
                direction_pool = planar_directions + vertical_directions if random.random() < 0.2 else vertical_directions + planar_directions
                random.shuffle(direction_pool)
                
                for direction in direction_pool:
                    dx, dy, dz = direction_vectors[direction]
                    next_coords = (cx + dx, cy + dy, cz + dz)
                    if next_coords not in coords_to_id:
                        coords_to_id[next_coords] = new_room_id
                        id_to_coords[new_room_id] = next_coords
                        rooms_data[new_room_id] = { "name": random.choice(theme.get("room_names", ["A Room"])), "exits": {} }
                        rooms_data[current_room_id]["exits"][direction] = new_room_id
                        rooms_data[new_room_id]["exits"][opposite_direction[direction]] = current_room_id
                        frontier.append(new_room_id)
                        connection_made = True
                        break
                if connection_made: break
            if not connection_made: break

        num_extra_connections = random.randint(num_rooms // 2, num_rooms)
        for _ in range(num_extra_connections):
            room_id = random.choice(list(id_to_coords.keys()))
            cx, cy, cz = id_to_coords[room_id]
            possible_connections = [d for d, (dx, dy, dz) in direction_vectors.items() if (cx + dx, cy + dy, cz + dz) in coords_to_id and d not in rooms_data[room_id]["exits"]]
            if possible_connections:
                chosen_direction = random.choice(possible_connections)
                nx, ny, nz = (cx + direction_vectors[chosen_direction][0], cy + direction_vectors[chosen_direction][1], cz + direction_vectors[chosen_direction][2])
                neighbor_id = coords_to_id[(nx, ny, nz)]
                rooms_data[room_id]["exits"][chosen_direction] = neighbor_id
                rooms_data[neighbor_id]["exits"][opposite_direction[chosen_direction]] = room_id
        
        for room_id, data in rooms_data.items():
            desc = self._format_with_placeholders(random.choice(theme.get("room_descriptions", ["An empty space."])))
            room = Room(name=data["name"], description=desc, exits=data["exits"], obj_id=room_id)
            new_region.add_room(room_id, room)

        return new_region, entry_room_id
