"""The versioned contract registry: what content may declare, and what it means.

The problem this exists for is in `docs/design/cross_theme_engine_contracts.md`:
the engine branches on genre words. `ItemFactory` maps `"Gem"` to the `Gem`
class, and a sci-fi content set used to inherit mana, spells and gem-cutting
because those were engine nouns rather than content declarations.

The registry replaces the branch with a declaration. Content says what a thing
*is* —

    {"id": "rose_quartz", "type": "Gem", "item_family": "collectible_stone"}

— and the family says what the engine does with it:

    {"id": "collectible_stone", "item_class": "Gem", "capabilities": ["collectible"],
     "generation_profile": "faceted_stone"}

Nothing in the engine has to know the word "gem". A sci-fi set declares
`energy_cell` under `consumable` and `alloy_plate` under `equipment`, and the
same resolution runs.

Versioning is deliberate and fails closed: a contracts file must state
`schema_version`, and a version this engine does not know is an error rather
than a best-effort read. An old content set should say so out loud.

Where the engine still needs a default — an undeclared gem template still has to
roll a size — the defaults here are **neutral** (rarity ranks, size bands,
quality bands). They are not fantasy vocabulary, and content may override every
one of them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from engine.contracts.schema import validate_fields, validate_list

CONTRACTS_DIRECTORY = "contracts"
CONTRACTS_FILENAME = "world_contracts.json"

# Bump when a change to the schemas below would make existing content mean
# something different. Content states the version it was written for.
SCHEMA_VERSION = 1

# --- what a contract file may contain ---------------------------------------

ITEM_FAMILY_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "description": {"type": "string"},
    # The engine class this family instantiates. This is the contract: content
    # names a family, the family names the behaviour.
    "item_class": {"type": "string", "required": True},
    "capabilities": {"type": "list_of", "of": "string"},
    "generation_profile": {"type": "string"},
    "attack_profile": {"type": "string"},
    "defense_profile": {"type": "string"},
    # How this family is drawn. Content decides presentation; the UI maps a
    # style to a drawing and never branches on a genre word or a class name.
    "icon_style": {"type": "string"},
    "resource": {"type": "string"},
    "debug_only": {"type": "bool"},
}

TIER_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "score": {"type": "int", "min": 1},
    "weight": {"type": "float", "min": 0},
    "value_multiplier": {"type": "float", "min": 0},
    "weight_multiplier": {"type": "float", "min": 0},
    "rank": {"type": "int", "min": 1},
}

GENERATION_PROFILE_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "item_family": {"type": "string", "required": True},
    "rarity_tiers": {"type": "list_of", "of": {"type": "object", "fields": TIER_FIELDS}},
    "size_tiers": {"type": "list_of", "of": {"type": "object", "fields": TIER_FIELDS}},
    "quality_tiers": {"type": "list_of", "of": {"type": "object", "fields": TIER_FIELDS}},
    "size_bias": {"type": "float"},
    "quality_bias": {"type": "float"},
    # How a rolled instance is named, from `{base}` (the template's own name) and
    # the bands it rolled: `{quality}`, `{size}`, `{rarity}`, `{profile}`. Bands
    # a set does not use render empty and the gaps close up, so "standard" size
    # never leaves a double space. Absent = "{quality} {size} {base}".
    "name_template": {"type": "string"},
    # A content set that already reads its own family of keys for rolled
    # instances (pre-P9 content reads `gem_size`) declares the prefix here and
    # the resolver writes it, without the engine knowing what it means.
    "property_prefix": {"type": "string"},
}

RESOURCE_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string", "required": True},
    # The compact form a status line has room for. Absent = the label's first
    # three letters, upper-cased.
    "short": {"type": "string"},
    "kind": {"type": "enum", "values": ("vital", "ability", "currency", "other")},
    "regenerates": {"type": "bool"},
    "regeneration_stat": {"type": "string"},
    "max_stat": {"type": "string"},
}

ATTACK_PROFILE_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    # The damage channel (physical, fire, arcane ...) that resistance maths uses.
    "damage_type": {"type": "string", "required": True},
    # The material-interaction type compared against a defender's armour material
    # by WEAPON_VS_ARMOR_MULTIPLIERS. A separate axis from the channel above,
    # which is why both exist.
    "weapon_damage_type": {"type": "string"},
    "damage": {"type": "float", "min": 0},
    "cooldown": {"type": "float", "min": 0},
    "resource_cost": {"type": "object", "fields": {"resource": {"type": "string"}, "amount": {"type": "float", "min": 0}}},
    "tags": {"type": "list_of", "of": "string"},
}

DEFENSE_PROFILE_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "defense": {"type": "float", "min": 0},
    "resistances": {"type": "map", "of": {"type": "float", "min": 0}},
    "material": {"type": "string"},
    "tags": {"type": "list_of", "of": "string"},
}

ABILITY_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "description": {"type": "string"},
    "effect_packet": {"type": "string", "required": True},
    "cost": {"type": "object", "fields": {"resource": {"type": "string"}, "amount": {"type": "float", "min": 0}}},
    "cooldown": {"type": "float", "min": 0},
    "target_type": {"type": "enum", "values": ("self", "ally", "enemy", "room", "item", "area")},
    "level_required": {"type": "int", "min": 0},
}

EFFECT_PACKET_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string"},
    "description": {"type": "string"},
    "resource": {"type": "string"},
    # What the packet is *for*, in neutral terms. `damage`, `restore`, `teach`,
    # `apply_effect`, `grant_item` -- a content set may add kinds, but the kind
    # decides no behaviour by itself; the payload does.
    "kind": {"type": "string", "required": True},
    "value": {"type": "float"},
    "duration": {"type": "float", "min": 0},
    "tags": {"type": "list_of", "of": "string"},
    "payload": {"type": "map"},
}

# Work that takes time. A declaration says what the work *is*; the engine's only
# job is to start it, evaluate it on read, and complete it. Everything that makes
# one work different from another -- a skill gate, a yield, a by-product -- is a
# field here rather than a branch in a manager, which is the whole point of the
# section existing.
#
# `duration_days` rather than seconds because that is the unit authors already
# think in (`ResourceNode`'s `respawn_days` is the existing precedent, and the
# only world-anchored duration the engine had before this).
WORK_FIELDS = {
    "id": {"type": "string", "required": True},
    "label": {"type": "string", "required": True},
    "description": {"type": "string"},
    # How long the work takes. Absent means instant: work with no duration is a
    # recipe, and a set that declares no `work` at all behaves exactly as it did
    # before this section existed.
    "duration_days": {"type": "float", "min": 0},
    "inputs": {"type": "list_of", "of": {"type": "object", "fields": {
        "item_id": {"type": "string", "required": True},
        "quantity": {"type": "int", "min": 1},
    }}},
    "outputs": {"type": "list_of", "of": {"type": "object", "fields": {
        "item_id": {"type": "string", "required": True},
        "quantity": {"type": "int", "min": 1},
    }}},
    # The check rolled when the work is *collected*, so a long job is not decided
    # at the moment it starts. Both optional: work that always succeeds is work
    # with no gate, which is a legitimate kind.
    "skill": {"type": "string"},
    "difficulty": {"type": "int", "min": 0},
    # What the work needs to be standing at, by the station type a nearby item
    # declares (`crafting_station_type`). Optional, and a name rather than a
    # location: the engine asks the room what is in it and compares strings, so
    # nothing here knows what a forge is.
    "station": {"type": "string"},
    "tags": {"type": "list_of", "of": "string"},
}

CONTRACT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "item_families": ITEM_FAMILY_FIELDS,
    "generation_profiles": GENERATION_PROFILE_FIELDS,
    "resources": RESOURCE_FIELDS,
    "attack_profiles": ATTACK_PROFILE_FIELDS,
    "defense_profiles": DEFENSE_PROFILE_FIELDS,
    "abilities": ABILITY_FIELDS,
    "effect_packets": EFFECT_PACKET_FIELDS,
    "work": WORK_FIELDS,
}

TOP_LEVEL_FIELDS = {
    "schema_version": {"type": "int", "required": True},
    "label": {"type": "string"},
    "description": {"type": "string"},
    # The one section that is an object rather than a list of `id` entries: it
    # is a mapping from role to stat, not a family of things.
    "stats": {"type": "object", "fields": {
        "roles": {"type": "map", "of": {"type": "string"}},
        "short": {"type": "map", "of": {"type": "string"}},
        "order": {"type": "list_of", "of": "string"},
    }},
    **{name: {"type": "list_of", "of": {"type": "object", "fields": fields}}
       for name, fields in CONTRACT_SCHEMAS.items()},
}

# What each role means, checked so a typo'd role is reported rather than read as
# an undeclared one (which would silently take the engine default).
STAT_ROLE_NAMES = (
    "health", "attack", "defence", "evasion", "regeneration",
    "power", "ability_power", "resistance",
)

# --- engine defaults ---------------------------------------------------------

# A generation profile the engine can fall back to when content declares none.
# Deliberately neutral: ranks and bands, no genre words. Content overrides it by
# declaring a profile of its own.
DEFAULT_GENERATION_PROFILE: Dict[str, Any] = {
    "id": "default_generated",
    "label": "Default generated item",
    "item_family": "",
    "name_template": "{quality} {size} {base}",
    "rarity_tiers": [
        {"id": "common", "rank": 1, "weight": 80},
        {"id": "uncommon", "rank": 2, "weight": 28},
        {"id": "rare", "rank": 3, "weight": 8},
        {"id": "legendary", "rank": 4, "weight": 2},
    ],
    "size_tiers": [
        {"id": "tiny", "label": "tiny", "score": 1, "value_multiplier": 0.45, "weight_multiplier": 0.35},
        {"id": "small", "label": "small", "score": 2, "value_multiplier": 0.7, "weight_multiplier": 0.65},
        {"id": "standard", "label": "", "score": 3, "value_multiplier": 1.0, "weight_multiplier": 1.0},
        {"id": "large", "label": "large", "score": 4, "value_multiplier": 1.65, "weight_multiplier": 1.7},
        {"id": "magnificent", "label": "magnificent", "score": 5, "value_multiplier": 3.0, "weight_multiplier": 3.0},
    ],
    "quality_tiers": [
        {"id": "flawed", "label": "Flawed", "score": 1, "value_multiplier": 0.45},
        {"id": "rough", "label": "Rough", "score": 2, "value_multiplier": 0.7},
        {"id": "fine", "label": "Fine", "score": 3, "value_multiplier": 1.0},
        {"id": "exceptional", "label": "Exceptional", "score": 4, "value_multiplier": 1.6},
        {"id": "perfect", "label": "Perfect", "score": 5, "value_multiplier": 2.8},
    ],
}


def registry_for(world: Any) -> Optional[ContractRegistry]:
    """The registry a world carries, if it has one."""
    return getattr(world, "contract_registry", None) if world is not None else None


def item_class_for_template(world: Any, template: Any) -> str:
    """The engine class a template resolves to: its family first, then `type`.

    One function because two callers must agree. `ItemFactory` decides what to
    instantiate and `GemGenerator` decides whether a template is a stone worth
    rolling; if they resolved differently, a template could be generated as one
    class and checked as another.

    Content that declares `item_family` goes through the contract. Content that
    predates contracts still resolves through `type`, which is what lets the
    migration happen one family at a time instead of as a flag day.
    """
    if not isinstance(template, dict):
        return ""
    registry = registry_for(world)
    if registry is not None:
        family_id = str(template.get("item_family", "") or "")
        if family_id:
            resolved = registry.item_class_for_family(family_id)
            if resolved:
                return resolved
    return str(template.get("type", "") or "")


def generation_profile_for_template(world: Any, template: Any) -> str:
    """A template's generation profile: its own, else its family's."""
    if not isinstance(template, dict):
        return ""
    authored = str(template.get("generation_profile", "") or "")
    if authored:
        return authored
    registry = registry_for(world)
    if registry is None:
        return ""
    family_id = str(template.get("item_family", "") or "")
    family = registry.family(family_id) if family_id else None
    return str(family.get("generation_profile", "") or "") if family else ""


@dataclass
class ContractRegistry:
    """Every contract a content set declares, validated and resolvable."""

    schema_version: int = SCHEMA_VERSION
    declared_version: int = 0
    source: str = ""
    item_families: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    generation_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    resources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    attack_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    defense_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    abilities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    effect_packets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Work that takes time. Declared here and evaluated on read; see
    # `engine/contracts/work.py` for the three things the engine does with one.
    work: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Not a family of entries with ids: one mapping from role to stat. See
    # `engine/contracts/stats.py` for what each role means.
    stats: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, content_root: Optional[str]) -> "ContractRegistry":
        registry = cls()
        if not content_root:
            return registry
        path = os.path.join(str(content_root), CONTRACTS_DIRECTORY, CONTRACTS_FILENAME)
        if not os.path.isfile(path):
            return registry
        registry.source = path
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            registry.issues.append("%s could not be read: %s" % (CONTRACTS_FILENAME, error))
            return registry
        registry.ingest(payload)
        return registry

    def ingest(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            self.issues.append("%s must contain an object" % CONTRACTS_FILENAME)
            return

        # Version first: reading content written for a different schema is how
        # fields silently come to mean something else.
        declared = payload.get("schema_version")
        if not isinstance(declared, int) or isinstance(declared, bool):
            self.issues.append(
                "%s must declare an integer schema_version (this engine speaks %d)"
                % (CONTRACTS_FILENAME, SCHEMA_VERSION)
            )
            return
        self.declared_version = declared
        if declared != SCHEMA_VERSION:
            self.issues.append(
                "%s declares schema_version %d but this engine implements %d; "
                "refusing to read it" % (CONTRACTS_FILENAME, declared, SCHEMA_VERSION)
            )
            return

        validate_fields(payload, TOP_LEVEL_FIELDS, "", self.issues, allow_extra=())
        if any("schema_version" in issue for issue in self.issues):
            return

        for name, fields in CONTRACT_SCHEMAS.items():
            entries = payload.get(name)
            if entries is None:
                continue
            before = len(self.issues)
            validate_list(entries, fields, name, self.issues)
            if len(self.issues) != before:
                # Structurally broken: do not register half of it.
                continue
            bucket = getattr(self, name)
            for entry in entries:
                bucket[str(entry["id"])] = entry

        self._ingest_stats(payload.get("stats"))

        self._resolve_references()

    def _ingest_stats(self, declared: Any) -> None:
        """The role-to-stat mapping, which no list validator can express."""
        if declared is None:
            return
        if not isinstance(declared, dict):
            self.issues.append("stats must be an object")
            return
        roles = declared.get("roles")
        if roles is None:
            self.stats = {key: value for key, value in declared.items() if key != "roles"}
            return
        if not isinstance(roles, dict):
            self.issues.append("stats.roles must be an object mapping role to stat")
            return
        unknown = sorted(
            str(role) for role in roles
            if str(role) not in STAT_ROLE_NAMES and not str(role).startswith("_")
        )
        if unknown:
            self.issues.append(
                "stats.roles names %s, which the engine has no role for (roles: %s)"
                % (", ".join("'%s'" % role for role in unknown), ", ".join(STAT_ROLE_NAMES))
            )
            return
        self.stats = {key: value for key, value in declared.items() if key != "roles"}
        self.stats["roles"] = {
            str(role): str(stat).strip()
            for role, stat in roles.items()
            if isinstance(stat, str) and stat.strip()
        }

    def stat_for_role(self, role: str) -> str:
        roles = self.stats.get("roles") if isinstance(self.stats, dict) else None
        if not isinstance(roles, dict):
            return ""
        return str(roles.get(str(role), "") or "")

    def _resolve_references(self) -> None:
        """Every reference a contract makes must land somewhere."""
        for family_id, family in self.item_families.items():
            profile = str(family.get("generation_profile", "") or "")
            if profile and profile not in self.generation_profiles:
                self.issues.append(
                    "item_families.%s references missing generation profile '%s'"
                    % (family_id, profile)
                )
            resource = str(family.get("resource", "") or "")
            if resource and resource not in self.resources:
                self.issues.append(
                    "item_families.%s references missing resource '%s'" % (family_id, resource)
                )

        for profile_id, profile in self.generation_profiles.items():
            family = str(profile.get("item_family", "") or "")
            if family and family not in self.item_families:
                self.issues.append(
                    "generation_profiles.%s references missing item family '%s'"
                    % (profile_id, family)
                )

        for ability_id, ability in self.abilities.items():
            packet = str(ability.get("effect_packet", "") or "")
            if packet and packet not in self.effect_packets:
                self.issues.append(
                    "abilities.%s references missing effect packet '%s'" % (ability_id, packet)
                )
            cost = ability.get("cost")
            if isinstance(cost, dict):
                resource = str(cost.get("resource", "") or "")
                if resource and resource not in self.resources:
                    self.issues.append(
                        "abilities.%s costs missing resource '%s'" % (ability_id, resource)
                    )

        for profile_id, profile in self.attack_profiles.items():
            cost = profile.get("resource_cost")
            if isinstance(cost, dict):
                resource = str(cost.get("resource", "") or "")
                if resource and resource not in self.resources:
                    self.issues.append(
                        "attack_profiles.%s costs missing resource '%s'" % (profile_id, resource)
                    )

        for packet_id, packet in self.effect_packets.items():
            resource = str(packet.get("resource", "") or "")
            if resource and resource not in self.resources:
                self.issues.append(
                    "effect_packets.%s references missing resource '%s'" % (packet_id, resource)
                )

    # -- lookups ----------------------------------------------------------

    def family(self, family_id: str) -> Optional[Dict[str, Any]]:
        return self.item_families.get(str(family_id or ""))

    def generation_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        return self.generation_profiles.get(str(profile_id or ""))

    def resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        return self.resources.get(str(resource_id or ""))

    def ability(self, ability_id: str) -> Optional[Dict[str, Any]]:
        return self.abilities.get(str(ability_id or ""))

    def effect_packet(self, packet_id: str) -> Optional[Dict[str, Any]]:
        return self.effect_packets.get(str(packet_id or ""))

    def work_declaration(self, work_id: str) -> Optional[Dict[str, Any]]:
        """The declared work an id names, or None.

        Named `work_declaration` rather than `work` so it does not shadow the
        section it reads from -- `registry.work` is the whole mapping, and a
        lookup method of the same name would make one of the two unreachable.
        """
        return self.work.get(str(work_id or ""))

    def item_class_for_family(self, family_id: str) -> str:
        family = self.family(family_id)
        return str(family.get("item_class", "") or "") if family else ""

    def family_has_capability(self, family_id: str, capability: str) -> bool:
        family = self.family(family_id)
        if not family:
            return False
        return capability in (family.get("capabilities") or [])

    def tiers(self, profile_id: str, tier_kind: str) -> Sequence[Dict[str, Any]]:
        """Tiers of one kind from a profile, falling back to the neutral default."""
        profile = self.generation_profile(profile_id) or {}
        tiers = profile.get(tier_kind)
        if isinstance(tiers, list) and tiers:
            return tiers
        return DEFAULT_GENERATION_PROFILE.get(tier_kind, ())

    def tier(self, profile_id: str, tier_kind: str, tier_id: str) -> Optional[Dict[str, Any]]:
        for entry in self.tiers(profile_id, tier_kind):
            if str(entry.get("id", "")) == str(tier_id):
                return entry
        return None

    # -- reporting --------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not (self.item_families or self.generation_profiles or self.resources
                    or self.attack_profiles or self.defense_profiles
                    or self.abilities or self.effect_packets or self.work or self.stats)

    def status(self) -> str:
        from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE

        if self.is_empty:
            return "This content set declares no contracts."
        lines = [
            "%sCONTRACTS%s (schema %d%s)"
            % (FORMAT_TITLE, FORMAT_RESET, self.schema_version,
               ", declared %d" % self.declared_version if self.declared_version else ""),
            "-" * 26,
        ]
        for name in CONTRACT_SCHEMAS:
            entries = getattr(self, name)
            if entries:
                lines.append(
                    "%s%s%s (%d): %s"
                    % (FORMAT_HIGHLIGHT, name.replace("_", " "), FORMAT_RESET, len(entries),
                       ", ".join(sorted(entries)))
                )
        if self.issues:
            lines.append("")
            lines.append("Issues: %d" % len(self.issues))
        return "\n".join(lines)
