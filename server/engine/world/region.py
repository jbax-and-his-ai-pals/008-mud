# engine/world/region.py
from typing import Dict, List, Optional, Any
from engine.world.room import Room
from engine.game_object import GameObject

class Region(GameObject):
    def __init__(self, name: str, description: str, obj_id: Optional[str] = None):
        region_obj_id = obj_id if obj_id else f"region_{name.lower().replace(' ', '_')}"
        super().__init__(obj_id=region_obj_id, name=name, description=description)
        self.rooms: Dict[str, Room] = {}
        self.spawner_config: Dict[str, Any] = {} # <<< ADDED: To hold spawn data
        self.properties.setdefault("indoors", False)

    def add_room(self, room_id: str, room: Room):
        self.rooms[room_id] = room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize region definition."""
        data = super().to_dict()
        data["rooms"] = {room_id: room.to_dict() for room_id, room in self.rooms.items()}
        data["spawner"] = self.spawner_config
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Region':
        """Deserialize region definition."""
        region = cls(
            name=data.get("name", "Unknown Region"),
            description=data.get("description", "No description"),
            obj_id=data.get("obj_id") or data.get("id")
        )

        for room_id, room_data in data.get("rooms", {}).items():
            try:
                room_data['obj_id'] = room_data.get('obj_id', room_id)
                room = Room.from_dict(room_data)
                region.add_room(room_id, room)
            except Exception as e:
                print(f"Warning: Failed to load room '{room_id}' in region '{region.name}': {e}")

        region.properties = data.get("properties", {})
        region.spawner_config = data.get("spawner", {}) # <<< ADDED: Load spawn data
        
        return region