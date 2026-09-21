# engine/world/room.py
from typing import Dict, List, Optional, Any
import uuid
import copy
from engine.config import FORMAT_CATEGORY, FORMAT_RESET, FORMAT_HIGHLIGHT
from engine.game_object import GameObject
from engine.items.item import Item

class Room(GameObject):
    def __init__(self, name: str, description: str, exits: Optional[Dict[str, str]] = None, obj_id: Optional[str] = None):
        room_obj_id = obj_id if obj_id else f"room_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:4]}"
        
        super().__init__(obj_id=room_obj_id, name=name, description=description)

        self.exits = exits or {}
        self.items: List[Item] = []
        self.initial_item_refs: List[Dict[str, Any]] = []
        self.initial_npc_refs: List[Dict[str, Any]] = []
        self.visited = False
        self.time_descriptions = {"dawn": "", "day": "", "dusk": "", "night": ""}
        self.env_properties = {"dark": False, "outdoors": False, "has_windows": False, "noisy": False, "smell": "", "temperature": "normal"}
        
        # New: Store active environmental modifications [ {type, original_value, time_remaining, key...} ]
        self.active_env_effects: List[Dict[str, Any]] = []
        self._hazard_last_tick_by_entity: Dict[str, float] = {}
        
        self.update_property("exits", self.exits)
        self.update_property("visited", self.visited)
        self.update_property("time_descriptions", self.time_descriptions)
        self.update_property("env_properties", self.env_properties)

    def update(self, dt: float) -> List[str]:
        """Called every tick to handle temporary environmental effects."""
        messages = []
        if not self.active_env_effects: return messages

        remaining_effects = []
        for effect in self.active_env_effects:
            effect["time_remaining"] -= dt
            if effect["time_remaining"] <= 0:
                # Revert
                action = effect["action"]
                if action == "modify_exit_req":
                    direction = effect["direction"]
                    original = effect["original_value"]
                    reqs = self.properties.get("exit_requirements", {})
                    if original is None:
                        # It didn't exist before? (Unlikely for this use case, but handle safety)
                        if direction in reqs: del reqs[direction]
                    else:
                        reqs[direction] = original
                    self.update_property("exit_requirements", reqs)
                    messages.append(f"{FORMAT_HIGHLIGHT}The environment returns to normal (Path {direction}).{FORMAT_RESET}")

                elif action == "suppress_hazard":
                    self.update_property("hazard_type", effect["original_value"])
                    messages.append(f"{FORMAT_HIGHLIGHT}The environmental hazard returns!{FORMAT_RESET}")

            else:
                remaining_effects.append(effect)
        
        self.active_env_effects = remaining_effects
        return messages

    def apply_elemental_interaction(self, damage_type: str) -> Optional[str]:
        """
        Check if the room reacts to a specific element (e.g. Ice freezes water).
        """
        interactions = self.properties.get("env_interactions", {})
        reaction = interactions.get(damage_type)
        
        if not reaction: return None
        
        action = reaction.get("type")
        duration = reaction.get("duration", 10.0)
        msg = reaction.get("message", "The environment shifts.")

        if action == "clear_exit_req":
            direction = reaction.get("direction")
            reqs = self.properties.get("exit_requirements", {})
            if direction and direction in reqs:
                # Store original for revert
                original = copy.deepcopy(reqs[direction])
                
                # Apply change (Remove requirement)
                del reqs[direction]
                self.update_property("exit_requirements", reqs)
                
                self.active_env_effects.append({
                    "action": "modify_exit_req",
                    "direction": direction,
                    "original_value": original,
                    "time_remaining": duration
                })
                return f"{FORMAT_HIGHLIGHT}{msg}{FORMAT_RESET}"
        
        elif action == "suppress_hazard":
            current_hazard = self.properties.get("hazard_type")
            if current_hazard:
                self.update_property("hazard_type", None)
                self.active_env_effects.append({
                    "action": "suppress_hazard",
                    "original_value": current_hazard,
                    "time_remaining": duration
                })
                return f"{FORMAT_HIGHLIGHT}{msg}{FORMAT_RESET}"

        return None

    def apply_hazards(self, entity, current_time: float) -> Optional[str]:
        """Damage `entity` for this room's hazard, in this room's own words.

        The reading lives in `engine/world/environment.py` -- one declaration
        resolved once -- and this is the delegation `Room` owns, because the tick
        cache is per-room state. The lookup that used to be here read a channel
        map and a channel-keyed sentence; see that module for what replaced it.
        """
        from engine.world import environment

        world = getattr(entity, "world", None)
        return environment.apply(
            world, self, entity, current_time, self._hazard_last_tick_by_entity
        )

    # ... (get_full_description, to_dict, from_dict etc. remain same) ...
    def get_full_description(self, time_period: str = "day", weather: str = "clear", is_outdoors: bool = True,
                              is_dark=None, is_noisy=None, smell=None, temperature=None) -> str:
        desc = self.description
        time_desc = self.time_descriptions.get(time_period)
        if not time_desc:
            if time_period in ["morning", "afternoon"]:
                time_desc = self.time_descriptions.get("day")
        if time_desc: desc += f"\n\n{time_desc}"
        if weather and is_outdoors: desc += f"\n\nThe weather is {weather}."

        # A caller that knows this room's region/district (description_
        # generator) resolves these through World.get_env_property's room ->
        # district -> region deviation chain and passes the result in. A
        # caller that doesn't (a bare Room, as in tests) falls back to this
        # room's own properties only, exactly as before.
        if is_dark is None: is_dark = self.properties.get("dark") or self.env_properties.get("dark")
        if is_noisy is None: is_noisy = self.properties.get("noisy") or self.env_properties.get("noisy")
        if smell is None: smell = self.properties.get("smell")
        if temperature is None: temperature = self.properties.get("temperature", "normal")

        if is_dark: desc += "\n\nIt is very dark here."
        if is_noisy: desc += "\n\nThe area is filled with noise."

        if smell: desc += f"\n\nYou detect a {smell} smell."
        if temperature == "cold": desc += "\n\nIt's noticeably cold in here."
        elif temperature == "hot": desc += "\n\nThe air is stiflingly hot."
        exits_list = sorted(list(self.exits.keys()))
        exit_desc = ", ".join(exits_list) if exits_list else "none"
        desc += f"\n\n{FORMAT_CATEGORY}Exits:{FORMAT_RESET} {exit_desc}"
        return desc
    
    def get_exit(self, direction: str) -> Optional[str]: return self.exits.get(direction.lower())
    def add_item(self, item: Item) -> None: self.items.append(item)
    def remove_item(self, obj_id: str) -> Optional[Item]:
        for i, item in enumerate(self.items):
            if item.obj_id == obj_id: return self.items.pop(i)
        return None
    def get_item(self, obj_id: str) -> Optional[Item]:
        for item in self.items:
            if item.obj_id == obj_id: return item
        return None

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["exits"] = self.exits
        data["initial_items"] = self.initial_item_refs
        data["initial_npcs"] = self.initial_npc_refs
        data["visited"] = self.visited
        data["time_descriptions"] = self.time_descriptions
        data["env_properties"] = self.env_properties
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Room':
        room = cls(
            name=data.get("name", "Unknown Room"),
            description=data.get("description", "No description"),
            obj_id=data.get("obj_id") or data.get("id"),
            exits=data.get("exits", {})
        )
        room.properties = data.get("properties", {})
        room.is_alive = data.get("is_alive", True)
        room.visited = data.get("visited", False)
        room.time_descriptions = data.get("time_descriptions", {"dawn":"", "day":"", "dusk":"", "night":""})
        room.env_properties = data.get("env_properties", {})
        room.initial_item_refs = data.get("initial_items", [])
        if not room.initial_item_refs and "items" in data: room.initial_item_refs = data.get("items", [])
        room.initial_npc_refs = data.get("initial_npcs", [])
        room.items = []
        room._hazard_last_tick_by_entity = {}
        room.update_property("exits", room.exits)
        room.update_property("visited", room.visited)
        room.update_property("time_descriptions", room.time_descriptions)
        room.update_property("env_properties", room.env_properties)
        return room
