"""Defines the canonical data model for a spell."""

from typing import Any, Dict, List

# The target types the cast path resolves (commands/magic.py cast_handler,
# player/magic.py cast_spell, npcs/combat.py). Any other value falls through to
# "cast it on yourself".
ABILITY_TARGET_TYPES = ("self", "friendly", "enemy", "all_enemies", "item")

# The effect types apply_spell_effect (magic/effects.py) executes, and the keys
# each one reads besides `type` and `damage_type` (every effect's `damage_type`
# is read when the ability is cast at a room). Any other type does nothing.
ABILITY_EFFECT_FIELDS = {
    "damage": ("value",),
    "heal": ("value",),
    "revive": ("value",),
    "percent_damage": ("value",),
    "steal": (),
    "life_tap": ("value",),
    "apply_dot": ("dot_name", "dot_duration", "dot_damage_per_tick", "dot_tick_interval", "dot_damage_type", "effect_data"),
    "apply_effect": ("effect_data", "dot_duration", "base_duration"),
    "cleanse": ("effect_data",),
    "remove_curse": (),
    "summon": ("summon_template_id", "summon_duration", "max_summons"),
    "unlock": (),
    "lock": (),
}

# The names each message is formatted with. The cast and remove-curse messages
# are formatted unguarded, so any other placeholder raises mid-cast.
ABILITY_MESSAGE_PLACEHOLDERS = {
    "cast_message": ("caster_name", "spell_name"),
    "hit_message": ("caster_name", "target_name", "spell_name", "value", "damage_type"),
    "heal_message": ("caster_name", "target_name", "spell_name", "value"),
    "self_heal_message": ("caster_name", "target_name", "spell_name", "value"),
    "remove_curse_item_message": ("target_name",),
    "remove_curse_equipment_message": ("target_name", "value"),
}


class Spell:
    def __init__(
        self,
        spell_id: str,
        name: str,
        description: str,
        effects: List[Dict[str, Any]] | None = None,
        mana_cost: int = 10,
        cooldown: float = 5.0,
        target_type: str = "enemy",
        cast_message: str = "You cast {spell_name}!",
        hit_message: str = "{caster_name} hits {target_name} with {spell_name} for {value} {damage_type} points!",
        heal_message: str = "{caster_name} heals {target_name} with {spell_name} for {value} points!",
        self_heal_message: str = "You heal yourself for {value} health!",
        remove_curse_item_message: str = "The curse on {target_name} is lifted.",
        remove_curse_equipment_message: str = "{value} cursed item(s) removed from {target_name}.",
        level_required: int = 1,
        health_cost_fraction: float = 0.0,
        windup: Dict[str, Any] | None = None,
        requires_ally: List[str] | None = None,
        sacrifice: bool = False,
    ):
        if not effects or not all(isinstance(effect, dict) and effect.get("type") for effect in effects):
            raise ValueError(f"Spell '{spell_id}' requires a non-empty effects array with typed effects.")
        self.spell_id = spell_id
        self.name = name
        self.description = description
        self.effects = effects
        self.mana_cost = mana_cost
        self.cooldown = cooldown
        self.target_type = target_type
        self.cast_message = cast_message
        self.hit_message = hit_message
        self.heal_message = heal_message
        self.self_heal_message = self_heal_message
        self.remove_curse_item_message = remove_curse_item_message
        self.remove_curse_equipment_message = remove_curse_equipment_message
        self.level_required = level_required
        # Part of the caster's own maximum health, paid on every cast on top of `mana_cost`
        # (0 = none). 0.125 is an eighth.
        self.health_cost_fraction = health_cost_fraction
        # `{seconds, leave_message, land_message}`: the caster leaves the fight and comes down on the target (magic/windup.py).
        self.windup = windup
        # NPC template ids that must be standing in the room, alive, for this to be cast (a twin spell needs the other twin).
        self.requires_ally = requires_ally
        # The caster gives everything to it and does not survive the cast (a creature or a companion; the effects fall first).
        self.sacrifice = sacrifice

    def health_cost(self, max_health: float) -> int:
        """The health this ability costs a caster whose maximum is `max_health`: at least 1 when it costs any."""
        if not self.health_cost_fraction or self.health_cost_fraction <= 0:
            return 0
        return max(1, int(float(max_health) * float(self.health_cost_fraction) + 0.5))   # half rounds up

    @classmethod
    def from_dict(cls, spell_id: str, data: Dict[str, Any]) -> "Spell":
        return cls(spell_id=spell_id, **data)

    def can_cast(self, caster: Any) -> bool:
        runtime_state = getattr(caster, "runtime_state", None)
        caster_level = runtime_state.progression.level if runtime_state is not None else getattr(caster, "level", 1)
        return caster_level >= self.level_required

    def format_cast_message(self, caster: Any) -> str:
        return self.cast_message.format(caster_name=getattr(caster, "name", "Someone"), spell_name=self.name)

    def ally_requirement(self, caster: Any) -> str:
        """"" when `requires_ally` is met (or there is none), else what is missing: every named ally must be standing in the
        caster's room, alive and able to act (not fallen, asleep, in the air or turned to stone)."""
        if not self.requires_ally:
            return ""
        world = getattr(caster, "world", None)
        here = (getattr(caster, "current_region_id", None), getattr(caster, "current_room_id", None))
        if world is None:
            return ""
        present = []
        for npc in world.get_npcs_in_room(*here):
            if npc is caster or not npc.is_alive:
                continue
            props = getattr(npc, "properties", {}) or {}
            if props.get("fallen") is True or any(npc.has_effect_tag(tag) for tag in ("sleep", "airborne", "petrify")):
                continue
            present.append(npc.template_id)
        missing = [name for name in self.requires_ally if name not in present]
        if not missing:
            return ""
        names = []
        for template_id in missing:
            template = getattr(world, "npc_templates", {}).get(template_id) if hasattr(world, "npc_templates") else None
            names.append(str(template.get("name", template_id)) if isinstance(template, dict) else template_id)
        return "%s needs %s beside %s." % (self.name, " and ".join(names), "them" if getattr(caster, "runtime_state", None) is None else "you")

    def has_effect_type(self, type_name: str) -> bool:
        return any(effect.get("type") == type_name for effect in self.effects)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spell_id": self.spell_id,
            "name": self.name,
            "description": self.description,
            "mana_cost": self.mana_cost,
            "cooldown": self.cooldown,
            "target_type": self.target_type,
            "effects": self.effects,
            "level_required": self.level_required,
            "health_cost_fraction": self.health_cost_fraction,
            "windup": self.windup,
            "requires_ally": self.requires_ally,
            "sacrifice": self.sacrifice,
            "cast_message": self.cast_message,
            "hit_message": self.hit_message,
        }
