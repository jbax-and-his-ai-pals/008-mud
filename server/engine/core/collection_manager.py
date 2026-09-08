# engine/core/collection_manager.py
import json
import os
from typing import Dict, Any, List, Set, TYPE_CHECKING
from engine.config import FORMAT_SUCCESS, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE, FORMAT_ERROR
from engine.config.config_display import FORMAT_GRAY

if TYPE_CHECKING:
    from engine.player import Player
    from engine.items.item import Item
    from engine.npcs.npc import NPC

class CollectionManager:
    def __init__(self, world):
        self.world = world
        self.content_root = world.content_root
        self.collections: Dict[str, Any] = {}
        self._load_collections()

    def _load_collections(self):
        path = os.path.join(self.content_root, "collections.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    self.collections = json.load(f)
            except Exception as e:
                print(f"Error loading collections: {e}")
                self.collections = {}

    def handle_collection_discovery(self, player: 'Player', item: 'Item') -> str:
        """
        Called on pickup. 
        1. Adds the collection to the player's list (if new).
        2. Returns a hint string.
        """
        collection_ids = self._collection_ids_for_item(item)
        if not collection_ids:
            return ""
        col_id = collection_ids[0]
        
        # --- NEW: Unlock the collection in the UI immediately ---
        if col_id not in player.collections_progress:
            player.collections_progress[col_id] = [] # Initialize with empty list (0 turned in)
        
        col_name = self.collections[col_id].get("name", "Unknown")
        return f"{FORMAT_HIGHLIGHT}(This item belongs to the '{col_name}' collection. You should take it to the Museum.){FORMAT_RESET}"

    def _collection_ids_for_item(self, item: 'Item') -> List[str]:
        """Resolve content membership from an item annotation or collection list.

        Item annotations keep a compact authoring path for broad item families,
        while explicit ``collections.json`` item lists make one-off or external
        item types collectible without an engine subtype knowing a collection.
        """
        found: List[str] = []
        declared = item.get_property("collection_id")
        declared_ids = declared if isinstance(declared, list) else [declared]
        for collection_id in declared_ids:
            normalized = str(collection_id).strip()
            if normalized and normalized in self.collections:
                found.append(normalized)
        for collection_id, definition in self.collections.items():
            items = definition.get("items", []) if isinstance(definition, dict) else []
            if item.obj_id in items and collection_id not in found:
                found.append(collection_id)
        return found

    def turn_in_items(self, player: 'Player', collector_npc: 'NPC') -> str:
        """
        Scans player inventory for collection items.
        Removes them, updates progress, and grants rewards.
        """
        if not collector_npc.properties.get("is_collector", False):
            return f"{collector_npc.name} is not interested in artifacts."

        items_to_remove = []
        
        # 1. Scan Inventory
        for slot in player.inventory.slots:
            if not slot.item: continue
            
            item = slot.item
            collection_ids = self._collection_ids_for_item(item)
            col_id = collection_ids[0] if collection_ids else None
            
            if col_id and col_id in self.collections:
                # Initialize progress list if needed
                if col_id not in player.collections_progress:
                    player.collections_progress[col_id] = []
                
                # Check if already collected (Turned In)
                if item.obj_id not in player.collections_progress[col_id]:
                    # Check if we already marked it for removal in this loop
                    already_queued = any(x[0] == item.obj_id for x in items_to_remove)
                    if not already_queued:
                        items_to_remove.append((item.obj_id, 1, item.name, col_id))

        if not items_to_remove:
            return f"\"You don't have any new artifacts for our collections,\" says {collector_npc.name}."

        # 2. Process Turn-ins
        messages = []
        for obj_id, qty, name, col_id in items_to_remove:
            # Remove from inventory
            removed_item, count, _ = player.inventory.remove_item(obj_id, qty)
            
            if removed_item:
                # Update Progress
                player.collections_progress[col_id].append(obj_id)
                col_name = self.collections[col_id].get("name", col_id)
                messages.append(f"Donated {name} to {col_name}.")
                
                # Check Completion
                self._check_completion(player, col_id, messages)

        return f"{FORMAT_SUCCESS}{' '.join(messages)}{FORMAT_RESET}"

    def _check_completion(self, player: 'Player', col_id: str, messages: List[str]):
        if player.collections_completed.get(col_id, False): return

        col_def = self.collections[col_id]
        required_items = col_def.get("items", [])
        found_items = player.collections_progress[col_id]
        
        if set(found_items) >= set(required_items):
            player.collections_completed[col_id] = True
            rewards_msg = self._grant_rewards(player, col_def)
            messages.append(f"\n{FORMAT_TITLE}COLLECTION COMPLETE: {col_def.get('name')}{FORMAT_RESET}\n{rewards_msg}")

    def _grant_rewards(self, player: 'Player', col_def: Dict) -> str:
        rewards = col_def.get("rewards", {})
        server = getattr(self.world, "server", None)
        if server is not None and hasattr(server, "grant_party_rewards"):
            return server.grant_party_rewards(player, rewards)

        msgs = []
        
        if "xp" in rewards and player.runtime_state.progression is not None:
            amt = rewards["xp"]
            player.gain_experience(amt)
            msgs.append(f"Gained {amt} XP")
            
        if "gold" in rewards and player.runtime_state.gold is not None:
            amt = rewards["gold"]
            player.runtime_state.gold += amt
            msgs.append(f"Gained {amt} {self.world.currency_name().capitalize()}")
            
        if "items" in rewards:
            from engine.items.item_factory import ItemFactory
            for item_data in rewards["items"]:
                item_id = item_data.get("item_id")
                qty = item_data.get("quantity", 1)
                item = ItemFactory.create_item_from_template(item_id, self.world)
                if item:
                    player.inventory.add_item(item, qty)
                    msgs.append(f"Received {item.name} (x{qty})")

        return ", ".join(msgs) + "!"
    
    def get_collection_status(self, player: 'Player', col_id: str) -> str:
        col_def = self.collections.get(col_id)
        if not col_def: return "Unknown collection."
        
        name = col_def.get("name", col_id)
        desc = col_def.get("description", "")
        req_items = col_def.get("items", [])
        found_items = player.collections_progress.get(col_id, [])
        is_complete = player.collections_completed.get(col_id, False)
        
        from engine.items.item_factory import ItemFactory
        
        status = f"{FORMAT_TITLE}Collection: {name}{FORMAT_RESET}\n{desc}\n"
        status += f"Status: {FORMAT_SUCCESS}Complete{FORMAT_RESET}" if is_complete else "Status: In Progress"
        status += "\n\nItems:\n"
        
        for item_id in req_items:
            template = ItemFactory.get_template(item_id, self.world)
            item_name = template.get("name", item_id) if template else item_id
            
            is_found = item_id in found_items
            in_inventory = player.inventory.count_item(item_id) > 0
            
            if is_found:
                mark = "[x]"
                color = FORMAT_SUCCESS
                suffix = " (Turned In)"
            elif in_inventory:
                mark = "[+]"
                color = FORMAT_HIGHLIGHT
                suffix = " (In Inventory)"
            else:
                mark = "[ ]"
                color = FORMAT_GRAY
                suffix = ""
            
            status += f"  {mark} {color}{item_name}{FORMAT_RESET}{suffix}\n"
            
        return status
