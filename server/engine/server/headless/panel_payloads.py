"""Data for a client's side panels: the character sheet and the world clock.

The text `status` command and the thin `status` event carry a name, health and level. A client
that wants to show a proper character panel (attributes, what is worn, spells, skills, effects)
or the time and weather had to ask for text and read it back. Two events carry it as data:

* `character`: level, experience, gold, health, the ability pool, the set's declared stats,
  equipment by slot (with durability), known spells (with cooldowns), skills and active effects.
* `world`: the time, date, period of day, season, and the weather where the player stands.
* `room`: the text `look` would give, for a pane that always shows the current room.
* `cooldown`: the attack cooldown (`duration`, and `remaining` seconds when it was sent), sent when an
  attack is made rather than every tick; the client counts the bar down itself.

They are sent when they change, per session (`_panel_events`), on every tick and after a
character is created or resumed, so a panel is never stale and a quiet server sends nothing. The
same check keeps the existing `inventory` and `quests` events current without the player asking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from engine.contracts.resources import ability_noun

# What a status panel shows when the content set declares no stat order (the classic six).
FALLBACK_STATS = ("strength", "dexterity", "constitution", "agility", "intelligence", "wisdom")
SLOT_LABELS = {
    "main_hand": "Main hand", "off_hand": "Off hand", "head": "Head", "body": "Body",
    "hands": "Hands", "feet": "Feet", "neck": "Neck",
}


class PanelPayloadsMixin:
    def _panel_cache(self) -> Dict[str, Dict[str, str]]:
        cache = getattr(self, "_panel_payload_cache", None)
        if cache is None:
            cache = {}
            self._panel_payload_cache = cache
        return cache

    def _panel_events(self, session_id: str, *, force: bool = False) -> List[Dict[str, Any]]:
        """The `character` and `world` events whose content changed since this session last had them."""
        if self.get_player_for_session(session_id) is None:
            return []
        sent = self._panel_cache().setdefault(session_id, {})
        events: List[Dict[str, Any]] = []
        builders = [("character", self._build_character_payload), ("world", self._build_world_payload),
                    ("room", self._build_room_payload), ("inventory", self._build_inventory_payload),
                    ("cooldown", self._build_cooldown_payload)]
        if self.world.has_capability("quests"):
            builders.append(("quests", self._build_quests_payload))
        for kind, build in builders:
            try:
                payload = build(session_id)
            except Exception:  # noqa: BLE001 - a panel must never break a command
                continue
            if payload is None:
                continue
            # A payload may name what "changed" means (`_signature`), when part of it is just time
            # passing (a countdown) and must not be resent every tick.
            marker = payload.pop("_signature", None) if isinstance(payload, dict) else None
            signature = json.dumps(marker if marker is not None else payload, sort_keys=True, default=str)
            if force or sent.get(kind) != signature:
                sent[kind] = signature
                events.append(self._event(kind, session_id, payload))
        return events

    # -- the attack cooldown ---------------------------------------------------------------

    def _build_cooldown_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        """When the player's next attack is ready, so a client can draw a bar that counts down.

        Sent when an attack is made or the weapon changes the cooldown, not on every tick: the
        client counts the remaining seconds down itself.
        """
        player = self.get_player_for_session(session_id)
        if player is None or not hasattr(player, "get_effective_attack_cooldown"):
            return None
        now = float(self.world.clock.now())
        duration = float(player.get_effective_attack_cooldown())
        last = float(getattr(player, "last_attack_time", 0.0) or 0.0)
        remaining = max(0.0, duration - (now - last)) if last > 0 else 0.0
        return {
            "attack": {"duration": round(duration, 2), "remaining": round(remaining, 2)},
            "_signature": [round(last, 3), round(duration, 2)],
        }

    # -- the room ----------------------------------------------------------------------------

    def _build_room_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        """What `look` says, for a pane that always shows where the player is."""
        player = self.get_player_for_session(session_id)
        if player is None:
            return None
        return {"text": str(self.world.look(minimal=True, player=player))}

    # -- the world clock -------------------------------------------------------------------

    def _build_world_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        player = self.get_player_for_session(session_id)
        data = dict(getattr(self.time_manager, "time_data", {}) or {})
        if not data:
            return None
        weather = ""
        intensity = ""
        manager = getattr(self, "weather_manager", None)
        if manager is not None:
            region = self.world.get_region(player.current_region_id) if player else None
            room = region.get_room(player.current_room_id) if region is not None and player else None
            weather = str(manager.effective_weather(region, room) or "")
            intensity = str(getattr(manager, "current_intensity", "") or "")
        return {
            "time": str(data.get("time_str", "")),
            "date": str(data.get("date_str", "")),
            "period": str(data.get("time_period", "")),
            "season": str(data.get("season", "")),
            "weather": weather,
            "intensity": intensity,
        }

    # -- the character sheet ---------------------------------------------------------------

    def _build_character_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        from engine.contracts import stats as stats_contract

        player = self.get_player_for_session(session_id)
        if player is None:
            return None
        world = self.world
        state = player.runtime_state
        payload: Dict[str, Any] = {
            "name": str(player.name),
            "health": {"current": int(player.health), "max": int(player.max_health)},
            "alive": bool(player.is_alive),
        }
        if state.progression is not None:
            payload["level"] = int(state.progression.level)
            payload["experience"] = int(state.progression.experience)
            payload["experience_to_level"] = int(state.progression.experience_to_level)
            payload["class"] = str(state.progression.player_class or "")
        if state.gold is not None:
            payload["gold"] = int(state.gold)
            payload["currency"] = str(world.currency_name())
        if world.uses_abilities() and state.magic is not None:
            payload["ability_resource"] = self._ability_resource_payload(player)

        payload["stats"] = [
            {"id": stat, "label": str(short), "value": int(player.get_effective_stat(stat))}
            for stat, short in stats_contract.display_stats(world, FALLBACK_STATS)
        ]

        payload["equipment"] = [
            {
                "slot": slot,
                "label": SLOT_LABELS.get(slot, slot.replace("_", " ").capitalize()),
                "item": item.name if item is not None else "",
                "durability": self._durability_text(item),
            }
            for slot, item in player.equipment.items()
        ]

        spells: List[Dict[str, Any]] = []
        if state.magic is not None:
            from engine.contracts.equipment import ability_cost_text
            from engine.magic.spell_registry import get_spell

            now = world.clock.now()
            for spell_id in sorted(state.magic.known_spells):
                spell = get_spell(spell_id)
                if spell is None:
                    continue
                remaining = max(0.0, float(state.magic.cooldowns.get(spell_id, 0) or 0) - now)
                spells.append({
                    "id": spell_id, "name": str(spell.name), "cost": int(getattr(spell, "mana_cost", 0) or 0),
                    "cost_text": ability_cost_text(world, spell),
                    "cooldown": round(remaining, 1),
                })
        payload["spells"] = sorted(spells, key=lambda entry: entry["name"])
        payload["ability_noun"] = ability_noun(world)

        skills = []
        if state.progression is not None:
            for name, entry in sorted((state.progression.skills or {}).items()):
                level = entry.get("level", 0) if isinstance(entry, dict) else entry
                skills.append({"name": str(name).replace("_", " ").capitalize(), "level": int(level or 0)})
        payload["skills"] = skills

        effects = []
        for effect in getattr(player, "active_effects", []) or []:
            if not isinstance(effect, dict):
                continue
            effects.append({
                "name": str(effect.get("name", "Effect")),
                "type": str(effect.get("type", "")),
                "remaining": round(float(effect.get("duration_remaining", 0) or 0), 0),
                "per_tick": int(effect.get("damage_per_tick", effect.get("heal_per_tick", 0)) or 0),
            })
        payload["effects"] = effects
        return payload

    @staticmethod
    def _durability_text(item: Any) -> str:
        if item is None:
            return ""
        maximum = item.get_property("max_durability", 0)
        if not maximum:
            return ""
        return "%d/%d" % (int(item.get_property("durability", maximum)), int(maximum))
