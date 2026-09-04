# engine/items/resource_node.py
from typing import Optional
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
        charges = self.get_property("charges")
        if charges <= 0:
            return f"The {self.name} has been depleted."
            
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
        resource = ItemFactory.create_item_from_template(resource_id, world)
        
        if resource:
            self.update_property("charges", charges - 1)
            player.inventory.add_item(resource)
            return f"{FORMAT_SUCCESS}You gather {resource.name} from the {self.name}.{FORMAT_RESET} ({charges-1} remaining)"
        
        return "You find nothing useful."