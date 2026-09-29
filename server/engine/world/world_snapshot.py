# engine/world/world_snapshot.py
"""The world's changes since it was built from content, in one serialiser.

Three things have to put a world back the way it was: the desktop `SaveManager`, the
finite-adventure baseline (`adventure reset`), and a restarted headless server. Each
grew its own copy of "what to keep", and each kept a different subset: the save file
never carried a room's exits or properties, so a lever, a picked lock or a
`reveal_exit` was lost on every load; the finite baseline kept properties but
re-linked `properties["exits"]` to the *live* exits, so `adventure reset` never closed
a lever-opened door either.

This module is that one copy.

**A snapshot is a set of changes, not a copy of the world.** Static rooms and regions
are rebuilt from content on every boot, so what a snapshot holds for them is what
differs from that build (`record_baseline` remembers it, once, while the world is
still pristine). Restoring first puts every static room back to the baseline and then
applies the saved changes on top, which is what makes a reset really reset, and what
lets a same-version edit to content show through in rooms nothing changed.
Everything the game creates or moves as it runs (NPCs, dynamic and instance regions)
is saved whole.

**Declared, not inferred.** `RESTORED` names every section a snapshot carries and
`DROPPED` names what deliberately does not travel, with the reason.
`test_save_declares_restored_keys.py` holds the two against `capture`, so a section
cannot be added or forgotten silently.

**Time.** A deadline that is an absolute clock reading (a respawn, an NPC's spell
cooldown) means nothing after a restart, because a simulated clock starts over and a
wall clock has kept running while the server was stopped. A snapshot stores each as
time *remaining*, and restoring turns it back into a reading on the new clock.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.npcs.ai import initialize_npc_schedules
from engine.npcs.npc_factory import NPCFactory
from engine.utils.logger import Logger
from engine.utils.utils import _serialize_item_reference
from engine.world.region import Region

SNAPSHOT_FORMAT = 1

# `properties` keys on a room that are the very same object as a live attribute
# (`Room.__init__` and `Room.from_dict` put one dict in both places), so they must be
# changed in place and are saved as the attribute, never as properties. `visited` is
# not one of them: `properties["visited"]` is a copy the engine only sometimes keeps
# in step, so it is ordinary data and travels as such.
_LINKED_PROPERTY_KEYS = ("exits", "time_descriptions", "env_properties")

# Every top-level key `capture` writes.
RESTORED = (
    "format", "clock", "regions", "rooms", "room_items", "npcs", "respawn_queue",
    "quest_board", "dynamic_regions", "time", "weather", "world_state",
)

# What a snapshot deliberately leaves out, and why. Nothing is dropped by accident.
DROPPED = {
    "summoned NPCs": "a summon belongs to one running game and expires; the player's summon ledger is dropped with them",
    "room hazard tick clocks": "per-entity timers of a room the player has left; they start again on the next visit",
    "ambient field cells": "kept in their own table (`world_cells`) by the field heartbeat, not in the snapshot",
    "the player": "owned by `Player.to_dict`, which knows what a player is",
    "static content": "rooms, items and NPC templates are rebuilt from the content set; only differences travel",
}


@dataclass
class RestoreReport:
    """What a restore did, and what it could not."""

    rooms_changed: int = 0
    npcs_restored: int = 0
    skipped_rooms: List[str] = field(default_factory=list)
    skipped_regions: List[str] = field(default_factory=list)
    skipped_npcs: List[str] = field(default_factory=list)
    reverted_to_baseline: bool = False

    @property
    def clean(self) -> bool:
        return not (self.skipped_rooms or self.skipped_regions or self.skipped_npcs)


# -- small helpers ---------------------------------------------------------------------


def _is_dynamic(region_id: Any) -> bool:
    return str(region_id).startswith(("dynamic_", "instance_"))


def _delta(base: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """What must be set and unset on `base` to make it `current`. Empty when equal."""
    base = base or {}
    changed = {key: copy.deepcopy(value) for key, value in current.items() if key not in base or base[key] != value}
    removed = [key for key in base if key not in current]
    out: Dict[str, Any] = {}
    if changed:
        out["set"] = changed
    if removed:
        out["unset"] = removed
    return out


def _apply_delta(target: Dict[str, Any], delta: Any) -> None:
    if not isinstance(delta, dict):
        return
    for key, value in (delta.get("set") or {}).items():
        target[key] = copy.deepcopy(value)
    for key in delta.get("unset") or []:
        target.pop(key, None)


def _replace_in_place(target: Dict[str, Any], content: Dict[str, Any]) -> None:
    """Make `target` equal `content` without replacing the object, so links to it hold."""
    target.clear()
    target.update(copy.deepcopy(content))


def _room_view(room: Any) -> Dict[str, Any]:
    return {
        "exits": copy.deepcopy(dict(room.exits)),
        "properties": {k: copy.deepcopy(v) for k, v in room.properties.items() if k not in _LINKED_PROPERTY_KEYS},
        "env_properties": copy.deepcopy(dict(room.env_properties)),
        "time_descriptions": copy.deepcopy(dict(room.time_descriptions)),
        "visited": bool(room.visited),
    }


def _item_refs(room: Any, world: Any) -> List[Dict[str, Any]]:
    return [_serialize_item_reference(item, 1, world) for item in getattr(room, "items", []) if item]


def _now(world: Any) -> float:
    return float(world.clock.now())


# -- the baseline ------------------------------------------------------------------------


def record_baseline(world: Any) -> None:
    """Remember what content built, once. Later calls do nothing.

    Called at the end of `initialize_new_world`, the first time, while static rooms
    have not yet been touched. `initialize_new_world` runs again on a reset or a failed
    load, when the rooms *have* been touched, which is why this must not overwrite.
    """
    if getattr(world, "_content_baseline", None) is not None:
        return
    regions: Dict[str, Any] = {}
    rooms: Dict[str, Any] = {}
    for region_id, region in world.regions.items():
        if not region or _is_dynamic(region_id):
            continue
        regions[str(region_id)] = copy.deepcopy(region.properties)
        for room_id, room in region.rooms.items():
            if room:
                rooms["%s:%s" % (region_id, room_id)] = {"view": _room_view(room), "items": _item_refs(room, world)}
    world._content_baseline = {"regions": regions, "rooms": rooms}


# -- capture -----------------------------------------------------------------------------


def capture(world: Any, *, time_manager: Any = None, weather_manager: Any = None) -> Dict[str, Any]:
    """The world's changes since it was built, as JSON-safe data."""
    now = _now(world)
    baseline = getattr(world, "_content_baseline", None) or {"regions": {}, "rooms": {}}

    regions: Dict[str, Any] = {}
    rooms: Dict[str, Any] = {}
    room_items: Dict[str, Any] = {}
    dynamic_regions: List[Dict[str, Any]] = []

    for region_id, region in world.regions.items():
        if not region:
            continue
        if _is_dynamic(region_id):
            dynamic_regions.append(copy.deepcopy(region.to_dict()))
            for room_id, room in region.rooms.items():
                refs = _item_refs(room, world) if room else []
                if refs:
                    room_items["%s:%s" % (region_id, room_id)] = refs
            continue

        region_delta = _delta(baseline["regions"].get(str(region_id)), region.properties)
        if region_delta:
            regions[str(region_id)] = region_delta

        for room_id, room in region.rooms.items():
            if not room:
                continue
            key = "%s:%s" % (region_id, room_id)
            base = baseline["rooms"].get(key)
            base_view = base["view"] if base else {}
            view = _room_view(room)
            entry: Dict[str, Any] = {}
            for name in ("exits", "properties", "env_properties", "time_descriptions"):
                delta = _delta(base_view.get(name), view[name])
                if delta:
                    entry[name] = delta
            if view["visited"] != base_view.get("visited", False):
                entry["visited"] = view["visited"]
            if room.active_env_effects:
                entry["active_env_effects"] = copy.deepcopy(room.active_env_effects)
            if entry:
                rooms[key] = entry
            refs = _item_refs(room, world)
            if refs != (base["items"] if base else []):
                room_items[key] = refs

    npcs: Dict[str, Any] = {}
    for instance_id, npc in world.npcs.items():
        if not npc or npc.properties.get("is_summoned", False):
            continue
        state = copy.deepcopy(npc.to_dict())
        cooldowns = state.get("spell_cooldowns") or {}
        state["spell_cooldowns"] = {spell: max(0.0, float(until) - now) for spell, until in cooldowns.items()}
        npcs[str(instance_id)] = state

    queue: List[Dict[str, Any]] = []
    for entry in world.respawn_manager.respawn_queue:
        item = copy.deepcopy(entry)
        if "respawn_time" in item:
            item["remaining"] = max(0.0, float(item.pop("respawn_time")) - now)
        queue.append(item)

    return {
        "format": SNAPSHOT_FORMAT,
        "clock": {"now": now},
        "regions": regions,
        "rooms": rooms,
        "room_items": {"mode": "delta", "rooms": room_items},
        "npcs": npcs,
        "respawn_queue": queue,
        "quest_board": copy.deepcopy(world.quest_board),
        "dynamic_regions": dynamic_regions,
        "time": time_manager.get_time_state_for_save() if time_manager is not None else None,
        "weather": weather_manager.get_weather_state_for_save() if weather_manager is not None else None,
        "world_state": copy.deepcopy(getattr(world, "world_state", {})),
    }


# -- restore -----------------------------------------------------------------------------


def _revert_to_baseline(world: Any, baseline: Dict[str, Any]) -> None:
    """Put every static room and region back the way content built it."""
    for region_id, region in world.regions.items():
        if not region or _is_dynamic(region_id):
            continue
        if str(region_id) in baseline["regions"]:
            _replace_in_place(region.properties, baseline["regions"][str(region_id)])
        for room_id, room in region.rooms.items():
            base = baseline["rooms"].get("%s:%s" % (region_id, room_id))
            if not room or not base:
                continue
            view = base["view"]
            _replace_in_place(room.exits, view["exits"])
            for key in [k for k in room.properties if k not in _LINKED_PROPERTY_KEYS]:
                del room.properties[key]
            room.properties.update(copy.deepcopy(view["properties"]))
            _replace_in_place(room.env_properties, view["env_properties"])
            _replace_in_place(room.time_descriptions, view["time_descriptions"])
            room.visited = view["visited"]
            room.active_env_effects = []
            room._hazard_last_tick_by_entity = {}
            room.items = []
    world._load_room_items_from_save({key: base["items"] for key, base in baseline["rooms"].items() if base["items"]})


def restore(world: Any, snapshot: Dict[str, Any], *, time_manager: Any = None, weather_manager: Any = None) -> RestoreReport:
    """Put the world back the way `snapshot` says it was.

    A room, region or NPC the snapshot names that the content no longer has is skipped
    and reported, never a crash: content is edited between runs, and one missing room
    must not cost a player the rest of their world.
    """
    report = RestoreReport()
    if not isinstance(snapshot, dict):
        return report
    now = _now(world)
    relative = isinstance(snapshot.get("clock"), dict)

    baseline = getattr(world, "_content_baseline", None)
    if baseline:
        _revert_to_baseline(world, baseline)
        report.reverted_to_baseline = True

    # Dynamic and instance regions are saved whole: drop what is there, add what was saved.
    for region_id in [rid for rid in world.regions if _is_dynamic(rid)]:
        world.regions.pop(region_id, None)
    for region_data in snapshot.get("dynamic_regions") or []:
        if not isinstance(region_data, dict):
            continue
        try:
            region = Region.from_dict(copy.deepcopy(region_data))
            world.add_region(region.obj_id, region)
            # A dynamic region's door onto a permanent room lives in that permanent
            # room's exits, which were just rebuilt: replay the wiring or it is lost.
            world.instance_manager.apply_entry_exit(region)
        except Exception as error:
            report.skipped_regions.append(str(region_data.get("obj_id") or region_data.get("id") or "?"))
            Logger.error("WorldSnapshot", "could not restore dynamic region: %s" % error)

    for region_id, delta in (snapshot.get("regions") or {}).items():
        region = world.regions.get(region_id)
        if not region:
            report.skipped_regions.append(str(region_id))
            continue
        _apply_delta(region.properties, delta)

    for key, entry in (snapshot.get("rooms") or {}).items():
        region_id, _, room_id = str(key).partition(":")
        region = world.regions.get(region_id)
        room = region.get_room(room_id) if region else None
        if not room or not isinstance(entry, dict):
            report.skipped_rooms.append(str(key))
            continue
        _apply_delta(room.exits, entry.get("exits"))
        if isinstance(entry.get("properties"), dict):
            _apply_delta(room.properties, entry["properties"])
        _apply_delta(room.env_properties, entry.get("env_properties"))
        _apply_delta(room.time_descriptions, entry.get("time_descriptions"))
        if "visited" in entry:
            room.visited = bool(entry["visited"])
        room.active_env_effects = copy.deepcopy(entry.get("active_env_effects") or [])
        report.rooms_changed += 1

    items = snapshot.get("room_items") or {}
    saved_items = items.get("rooms") if isinstance(items, dict) else {}
    if isinstance(items, dict) and items.get("mode") == "full":
        for region in world.regions.values():
            for room in (region.rooms.values() if region else []):
                if room:
                    room.items = []
    else:
        for key in saved_items or {}:
            region_id, _, room_id = str(key).partition(":")
            region = world.regions.get(region_id)
            room = region.get_room(room_id) if region else None
            if room:
                room.items = []
    world._load_room_items_from_save(copy.deepcopy(saved_items or {}))

    world.npcs = {}
    for instance_id, state in (snapshot.get("npcs") or {}).items():
        template_id = state.get("template_id") if isinstance(state, dict) else None
        if not template_id:
            report.skipped_npcs.append(str(instance_id))
            continue
        overrides = copy.deepcopy(state)
        overrides.pop("template_id", None)
        cooldowns = overrides.get("spell_cooldowns") or {}
        if relative:
            overrides["spell_cooldowns"] = {spell: now + float(left) for spell, left in cooldowns.items()}
        npc = NPCFactory.create_npc_from_template(template_id, world, instance_id, **overrides)
        if npc:
            world.add_npc(npc)
            report.npcs_restored += 1
        else:
            report.skipped_npcs.append(str(instance_id))
    initialize_npc_schedules(world)

    queue: List[Dict[str, Any]] = []
    for entry in snapshot.get("respawn_queue") or []:
        item = copy.deepcopy(entry)
        if "remaining" in item:
            item["respawn_time"] = now + float(item.pop("remaining"))
        queue.append(item)
    world.respawn_manager.respawn_queue = queue

    world.quest_board = copy.deepcopy(snapshot.get("quest_board") or [])
    world.world_state = copy.deepcopy(snapshot.get("world_state") or {})
    if time_manager is not None and snapshot.get("time") is not None:
        time_manager.apply_loaded_time_state(copy.deepcopy(snapshot["time"]))
    if weather_manager is not None and snapshot.get("weather") is not None:
        weather_manager.apply_loaded_weather_state(copy.deepcopy(snapshot["weather"]))
    return report
