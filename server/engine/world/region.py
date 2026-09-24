# engine/world/region.py
from typing import Dict, List, Optional, Any
from engine.world.room import Room
from engine.game_object import GameObject

# What a room, district and region share: the atmosphere keys World.get_env_property
# resolves room -> district -> region, and safe_zone (World.is_location_safe).
ENV_PROPERTY_KINDS = {
    "dark": "boolean", "noisy": "boolean", "smell": "string", "temperature": "string",
    "outdoors": "boolean", "safe_zone": "boolean",
}
# A region's `properties` that something reads. `biome` and `region_type` are
# read only by the content validator's classification policy
# (ruleset.world.regions). test_room_property_vocabulary.py ties each to a reader.
REGION_PROPERTY_KINDS = {
    **ENV_PROPERTY_KINDS,
    "weather_profile": "string",   # WeatherManager
    "level_band": "object",        # Region.get_level_band
    "districts": "object",         # World.get_district
    "biome": "string", "region_type": "string",
}
# A district (region.properties.districts.<id>) the engine reads: its members
# (or the older `rooms`) and the atmosphere it overrides.
DISTRICT_PROPERTY_KINDS = {**ENV_PROPERTY_KINDS, "members": "array", "rooms": "array"}
# The world editor's own district fields (its generator and map); not read in play.
DISTRICT_EDITOR_KEYS = ("id", "name", "kind", "seed", "generator", "ports", "reroll_policy", "color", "shape")

class Region(GameObject):
    def __init__(self, name: str, description: str, obj_id: Optional[str] = None):
        region_obj_id = obj_id if obj_id else f"region_{name.lower().replace(' ', '_')}"
        super().__init__(obj_id=region_obj_id, name=name, description=description)
        self.rooms: Dict[str, Room] = {}
        self.spawner_config: Dict[str, Any] = {} # <<< ADDED: To hold spawn data

    def add_room(self, room_id: str, room: Room):
        self.rooms[room_id] = room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def get_level_band(self) -> Optional[tuple[int, int]]:
        """Return this region's authored progression band, when it has one.

        Regions intentionally own this data.  It is not inferred from graph
        distance to a particular start room, so a future content set can add
        another starting town without changing the runtime's idea of danger.
        """
        band = self.properties.get("level_band")
        if not isinstance(band, dict):
            return None
        minimum = band.get("min")
        maximum = band.get("max")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 1
            or maximum < minimum
        ):
            return None
        return minimum, maximum

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
