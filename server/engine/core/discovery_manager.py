"""Content-authored player discoveries.

This deliberately knows nothing about a setting.  A package can describe
small journal entries that are unlocked by finding particular item templates
or by finding an item carrying one of its authored discovery tags.
"""

import json
import os
from typing import Any, Dict, List, TYPE_CHECKING

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET

if TYPE_CHECKING:
    from engine.items.item import Item
    from engine.player import Player


class DiscoveryManager:
    def __init__(self, world):
        self.world = world
        self.content_root = world.content_root
        self.discoveries: Dict[str, Dict[str, Any]] = {}
        self._load_discoveries()

    def _load_discoveries(self) -> None:
        path = os.path.join(self.content_root, "discoveries.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as source:
                payload = json.load(source)
            if isinstance(payload, dict):
                self.discoveries = {
                    str(discovery_id): definition
                    for discovery_id, definition in payload.items()
                    if not str(discovery_id).startswith("_") and isinstance(definition, dict)
                }
        except (OSError, json.JSONDecodeError) as error:
            print(f"Error loading discoveries: {error}")

    def _matching_ids(self, item: 'Item') -> List[str]:
        item_tags = item.get_property("discovery_tags", [])
        if not isinstance(item_tags, list):
            item_tags = []
        normalized_tags = {str(tag).strip() for tag in item_tags if str(tag).strip()}
        matches: List[str] = []
        for discovery_id, definition in self.discoveries.items():
            item_ids = definition.get("item_ids", [])
            tags = definition.get("item_tags", [])
            if not isinstance(item_ids, list):
                item_ids = []
            if not isinstance(tags, list):
                tags = []
            if item.obj_id in item_ids or normalized_tags.intersection(str(tag).strip() for tag in tags):
                matches.append(discovery_id)
        return matches

    def handle_item_discovery(self, player: 'Player', item: 'Item') -> str:
        """Unlock matching entries once and return concise first-discovery feedback."""
        unlocked: List[str] = []
        for discovery_id in self._matching_ids(item):
            if discovery_id in player.discoveries:
                continue
            player.discoveries[discovery_id] = {
                "item_id": item.obj_id,
                "day": self._day_number(),
            }
            unlocked.append(str(self.discoveries[discovery_id].get("name", discovery_id)))
        if not unlocked:
            return ""
        names = ", ".join(unlocked)
        return f"{FORMAT_HIGHLIGHT}(New discovery: {names}. Type 'discoveries' to review it.){FORMAT_RESET}"

    def _day_number(self) -> int:
        time_manager = getattr(getattr(self.world, "game", None), "time_manager", None)
        return int(getattr(time_manager, "game_time", 0) // 86400) if time_manager else 0

    def status(self, player: 'Player') -> str:
        unlocked = [
            (discovery_id, definition)
            for discovery_id, definition in sorted(self.discoveries.items())
            if discovery_id in player.discoveries
        ]
        if not unlocked:
            return "No discoveries recorded yet. Find unusual materials, goods, and curios."
        lines = ["DISCOVERIES"]
        for discovery_id, definition in unlocked:
            lines.append(f"- {definition.get('name', discovery_id)}: {definition.get('description', '')}")
        return "\n".join(lines)
