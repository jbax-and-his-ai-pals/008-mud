# engine/items/interactive.py
from typing import Optional, Dict, Any
from engine.items.item import Item
from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS

class Interactive(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown",
                 description: str = "An interactive object.",
                 interaction_type: str = "toggle", # toggle, trigger
                 state: str = "off", # off, on
                 linked_target_id: Optional[str] = None, # Room ID or Item ID to affect
                 linked_action: Optional[str] = None, # "toggle_exit:north", "unlock"
                 interaction_message: str = "You use the object.",
                 weight: Optional[float] = None,
                 **kwargs):
        
        if 'stackable' in kwargs:
             kwargs.pop('stackable')
        
        final_weight = weight if weight is not None else 9999
        
        super().__init__(obj_id, name, description, weight=final_weight, stackable=False, **kwargs)
        
        self.update_property("type", "Interactive")
        self.update_property("can_take", False)
        self.update_property("interaction_type", interaction_type)
        self.update_property("state", state)
        self.update_property("linked_target_id", linked_target_id)
        self.update_property("linked_action", linked_action)
        self.update_property("interaction_message", interaction_message)

    def interact(self, user, world) -> str:
        current_state = self.get_property("state")
        new_state = "on" if current_state == "off" else "off"
        
        self.update_property("state", new_state)
        
        action_result = ""
        linked_action = self.get_property("linked_action")
        target_id = self.get_property("linked_target_id")
        
        if linked_action and target_id:
            if linked_action.startswith("toggle_exit:"):
                direction = linked_action.split(":")[1]
                
                room = None
                if ":" in target_id:
                    reg_id, rm_id = target_id.split(":")
                    region = world.get_region(reg_id)
                    room = region.get_room(rm_id) if region else None
                else:
                    region = world.get_current_region()
                    room = region.get_room(target_id) if region else None
                    
                if room:
                    hidden_exits = room.properties.get("hidden_exits", {})
                    
                    if new_state == "on":
                        if direction in hidden_exits:
                            room.exits[direction] = hidden_exits[direction]
                            action_result = f" You hear a heavy grinding sound from the {direction}."
                    else:
                        if direction in room.exits and direction in hidden_exits:
                            del room.exits[direction]
                            action_result = f" The passage to the {direction} seals shut."

        base_msg = self.get_property("interaction_message")
        state_color = FORMAT_SUCCESS if new_state == "on" else FORMAT_HIGHLIGHT
        return f"{base_msg}{action_result} (State: {state_color}{new_state.upper()}{FORMAT_RESET})"