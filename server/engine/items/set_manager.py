# engine/items/set_manager.py
import json
import os
from typing import Dict, Any, List, TYPE_CHECKING

from engine.config import FORMAT_ERROR, FORMAT_RESET

if TYPE_CHECKING:
    from engine.world.world import World

class SetManager:
    def __init__(self, world: 'World'):
        if world is None:
            raise ValueError("SetManager requires an owning world.")
        self.content_root = world.content_root
        self.sets: Dict[str, Any] = {}
        self._load_sets()

    def _load_sets(self):
        path = os.path.join(self.content_root, "items", "sets.json")
        if not os.path.exists(path):
            return

        try:
            with open(path, 'r') as f:
                self.sets = json.load(f)
        except Exception as e:
            print(f"{FORMAT_ERROR}Error loading item sets: {e}{FORMAT_RESET}")

    def get_active_bonuses(self, equipped_item_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Given a list of item IDs (templates), returns a list of active bonus dictionaries (modifiers).
        """
        active_bonuses = []
        
        for set_id, set_data in self.sets.items():
            set_items = set(set_data.get("items", []))
            count = sum(1 for item_id in equipped_item_ids if item_id in set_items)
            
            if count > 0:
                bonuses = set_data.get("bonuses", {})
                for threshold_str, bonus_data in bonuses.items():
                    if count >= int(threshold_str):
                        active_bonuses.append(bonus_data)
                        
        return active_bonuses
