# engine/items/resource_node.py
from typing import Optional
import random
from engine.items.item import Item
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET

class ResourceNode(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Resource",
                 description: str = "A resource node.", 
                 resource_item_id: str = "item_stone",
                 tool_required: str = "pickaxe",
                 charges: int = 3,
                 **kwargs):
        
        if 'stackable' in kwargs:
            kwargs.pop('stackable')
            
        if 'weight' in kwargs:
            kwargs.pop('weight')

        super().__init__(obj_id, name, description, weight=9999, stackable=False, **kwargs)
        
        self.update_property("can_take", False)
        self.update_property("resource_item_id", resource_item_id)
        self.update_property("tool_required", tool_required)
        self.update_property("charges", charges)
        self.update_property("max_charges", charges)

    def gather(self, player, world) -> str:
        charges = self.available_charges(world)
        if charges <= 0:
            return f"The {self.name} has been depleted."

        time_manager = getattr(getattr(world, "game", None), "time_manager", None)
        day_number = self._day_number(world)
        respawn_days = int(self.get_property("respawn_days", 0))

        allowed_seasons = self.get_property("seasons", [])
        current_season = str(getattr(time_manager, "time_data", {}).get("season", "")) if time_manager else ""
        if allowed_seasons and current_season not in allowed_seasons:
            return f"The {self.name} offers nothing during this season."
            
        tool_req = self.get_property("tool_required")
        
        has_tool = False
        for item in player.equipment.values():
            if item and item.get_property("tool_type") == tool_req:
                has_tool = True
                break
        if not has_tool:
            for slot in player.inventory.slots:
                if slot.item and slot.item.get_property("tool_type") == tool_req:
                    has_tool = True; break
        
        if not has_tool:
            return f"{FORMAT_ERROR}You need a {tool_req} to gather from this.{FORMAT_RESET}"
            
        from engine.items.item_factory import ItemFactory
        resource_id = self.get_property("resource_item_id")
        selected_yield = None
        yield_table = self.get_property("yield_table", [])
        if isinstance(yield_table, list):
            for candidate in yield_table:
                if isinstance(candidate, dict) and random.random() <= float(candidate.get("chance", 0.0)):
                    resource_id = candidate.get("item_id", resource_id)
                    selected_yield = candidate
                    break
        resource = ItemFactory.create_item_from_template(resource_id, world)
        
        if resource:
            # A node can provide a dependable regional grade while an
            # authored yield-table entry can replace it with a rarer grade.
            # This remains useful for any setting's materials without the
            # engine knowing their genre or lore.
            quality = (
                selected_yield.get("material_quality", self.get_property("material_quality", {}))
                if selected_yield is not None
                else self.get_property("material_quality", {})
            )
            if isinstance(quality, dict):
                raw_score = quality.get("score", 0)
                score = int(raw_score) if isinstance(raw_score, int) and not isinstance(raw_score, bool) else 0
                if score > 0:
                    quality_id = str(quality.get("id", "refined")).strip() or "refined"
                    quality_label = str(quality.get("label", quality_id.replace("_", " ").title())).strip()
                    resource.properties["material_quality"] = quality_id
                    resource.properties["material_quality_label"] = quality_label
                    resource.properties["material_quality_score"] = score
                    resource.properties["material_source_id"] = self.obj_id
                    resource.properties["material_source_label"] = self.name
                    resource.stackable = False
                    resource.update_property("stackable", False)
            self.update_property("charges", charges - 1)
            if charges - 1 <= 0 and respawn_days > 0:
                self.update_property("depleted_day", day_number)
            player.inventory.add_item(resource)
            discovery = ""
            collection_manager = getattr(getattr(world, "game", None), "collection_manager", None)
            if collection_manager is not None:
                discovery = collection_manager.handle_collection_discovery(player, resource)
            discovery_manager = getattr(getattr(world, "game", None), "discovery_manager", None)
            journal_note = discovery_manager.handle_item_discovery(player, resource) if discovery_manager else ""
            quality_note = f" ({resource.get_property('material_quality_label')} quality)" if resource.get_property("material_quality_score", 0) else ""
            message = f"{FORMAT_SUCCESS}You gather {resource.name}{quality_note} from the {self.name}.{FORMAT_RESET} ({charges-1} remaining)"
            notes = [note for note in (discovery, journal_note) if note]
            return message + "\n" + "\n".join(notes) if notes else message
        
        return "You find nothing useful."

    def _day_number(self, world) -> int:
        time_manager = getattr(getattr(world, "game", None), "time_manager", None)
        return int(getattr(time_manager, "game_time", 0) // 86400) if time_manager else 0

    def available_charges(self, world) -> int:
        """Refresh and return charge state for gathering and inspection alike."""
        charges = int(self.get_property("charges", 0))
        respawn_days = int(self.get_property("respawn_days", 0))
        depleted_day = self.get_property("depleted_day")
        day_number = self._day_number(world)
        if charges <= 0 and respawn_days > 0 and depleted_day is not None and day_number - int(depleted_day) >= respawn_days:
            charges = int(self.get_property("max_charges", 1))
            self.update_property("charges", charges)
        return charges
