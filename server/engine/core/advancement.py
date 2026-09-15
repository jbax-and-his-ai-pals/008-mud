"""The advancement ledger: what a player has seen and done, and what it paid.

Replaces the old model where XP came from kills and quests and almost nothing
else. Every recognised activity records a first-time entry and grants authored
XP, across region entry, landmark rooms, creatures, materials, gems, recipes,
spells, named NPCs, relationship tiers, quests, and collection sets.

This generalises `DiscoveryManager`, which already had the right shape -- a set
of things found, recorded once, with a journal -- but only ever covered items
and paid nothing. Discoveries remain a *kind* of ledger entry rather than a
parallel system, so a player has one record of their travels and one place to
read it.

Design notes
------------
* **First time only.** A repeat pays nothing. That is what keeps progression
  from being a grind of the same content, and is the point of the whole model.
* **Authored, not implied.** Every entry key and every XP value comes from
  content. The engine records; content decides what is worth anything.
* **Never silently worth zero.** An entry that no rule matches still records
  (so the journal can show it) but grants nothing, and a malformed rule is
  reported rather than ignored.
* **Sources are independent.** A pacifist, a merchant, and a monster-hunter
  should each be able to advance, so no source is privileged in the engine.

Content shape (ruleset `advancement`, or a content `advancement.json`):

    {
      "curve": {"base": 100, "multiplier": 1.25},
      "grants": [
        {"id": "region_entry", "match": {"kind": "region_entry"},
         "xp": 120, "message": "You have not been here before."},
        {"id": "first_creature", "match": {"kind": "creature", "npc_tags": ["beast"]},
         "xp": 15},
        {"id": "first_gem", "match": {"kind": "item", "item_type": "Gem"},
         "xp": 15, "message": "A stone worth cataloguing."}
      ]
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET

# Entry-key prefixes. A single namespace keeps the "have I seen this?" check
# trivial and makes the journal readable.
KIND_REGION = "region"
KIND_LANDMARK = "landmark"
KIND_CREATURE = "creature"
KIND_ITEM = "item"
KIND_RECIPE = "recipe"
KIND_SPELL = "spell"
KIND_NPC = "npc"
KIND_RELATIONSHIP = "relationship"
KIND_QUEST = "quest"
KIND_COLLECTION = "collection"
KIND_DISCOVERY = "discovery"

KNOWN_ENTRY_KINDS = frozenset({
    KIND_REGION, KIND_LANDMARK, KIND_CREATURE, KIND_ITEM, KIND_RECIPE,
    KIND_SPELL, KIND_NPC, KIND_RELATIONSHIP, KIND_QUEST, KIND_COLLECTION,
    KIND_DISCOVERY,
})

# Defaults if a content set authors no curve at all. Chosen so that a world of
# a few dozen regions carries a player to roughly level 15 (WORLD_DESIGN §3.2),
# rather than the old x1.5 curve which needed hundreds of regions.
DEFAULT_CURVE_BASE = 100
DEFAULT_CURVE_MULTIPLIER = 1.25


def entry_key(kind: str, identifier: str) -> str:
    return "%s:%s" % (kind, identifier)


def parse_entry_key(key: str) -> Tuple[str, str]:
    kind, _, identifier = str(key).partition(":")
    return kind, identifier


@dataclass
class GrantRule:
    """One authored rule: which entries pay, and how much."""

    rule_id: str
    xp: int
    message: str = ""
    kinds: Tuple[str, ...] = ()
    # Optional narrowing
    region_id: str = ""
    npc_tags: Tuple[str, ...] = ()
    item_type: str = ""
    item_tags: Tuple[str, ...] = ()
    entry_ids: Tuple[str, ...] = ()
    once_per_kind: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def matches(self, kind: str, identifier: str, payload: Dict[str, Any]) -> bool:
        if self.kinds and kind not in self.kinds:
            return False
        if self.entry_ids and identifier not in self.entry_ids:
            return False
        if self.region_id and str(payload.get("region_id", "")) != self.region_id:
            return False
        if self.item_type and str(payload.get("item_type", "")) != self.item_type:
            return False
        for tag in self.npc_tags:
            if tag not in (payload.get("npc_tags") or ()):
                return False
        for tag in self.item_tags:
            if tag not in (payload.get("item_tags") or ()):
                return False
        return True


@dataclass
class AwardResult:
    """What one `record` call did."""

    recorded: bool = False
    xp: int = 0
    messages: List[str] = field(default_factory=list)
    leveled_up: bool = False
    level_up_message: str = ""

    def feedback(self) -> str:
        lines = [m for m in self.messages if m]
        if self.level_up_message:
            lines.append(self.level_up_message)
        return "\n".join(lines)


def award(player, kind: str, identifier: str, **kwargs: Any) -> str:
    """Record an activity for `player` and return any player-facing feedback.

    The one entry point gameplay code calls. It is deliberately total: it looks
    the manager up from the player's world, and returns an empty string rather
    than raising when there is no ledger (a bare unit-test player, a content set
    with no advancement config). Nothing in a movement or combat path should
    break because progression is absent.
    """
    if player is None or not identifier:
        return ""
    world = getattr(player, "world", None)
    manager = getattr(world, "advancement_manager", None) if world is not None else None
    if manager is None:
        server = getattr(world, "server", None) if world is not None else None
        manager = getattr(server, "advancement_manager", None) if server is not None else None
    if manager is None:
        return ""
    try:
        result = manager.record(player, kind, identifier, **kwargs)
    except Exception:
        # A ledger failure must never break the action that triggered it.
        return ""
    return result.feedback()


def seed_entry(player, kind: str, identifier: str) -> bool:
    """Record an activity the player *started* with, paying nothing for it.

    The counterpart to `award` for starting kits: a background's recipes and
    spells, and the region a character spawns in, belong in the journal (so the
    record is honest and a later encounter cannot pay for them) but are not
    achievements. Returns True when the entry was new.

    Module-level because both `Player.learn_recipe` and `Player.learn_spell`
    need it from the player layer, where importing the manager would be a
    circular import.
    """
    if player is None or not identifier:
        return False
    world = getattr(player, "world", None)
    manager = getattr(world, "advancement_manager", None) if world is not None else None
    if manager is None:
        server = getattr(world, "server", None) if world is not None else None
        manager = getattr(server, "advancement_manager", None) if server is not None else None
    if manager is None:
        return False
    try:
        return manager.seed(player, kind, identifier)
    except Exception:
        return False


def item_payload(item) -> Dict[str, Any]:
    """The facts an item-grant rule can match on."""
    properties = getattr(item, "properties", None)
    tags: List[str] = []
    if isinstance(properties, dict):
        raw = properties.get("loot_tags") or properties.get("item_tags") or []
        if isinstance(raw, (list, tuple)):
            tags = [str(t) for t in raw]
    return {
        "item_type": type(item).__name__,
        "item_tags": tags,
        "item_id": str(getattr(item, "obj_id", "") or ""),
    }


def npc_payload(npc) -> Dict[str, Any]:
    """The facts a creature-grant rule can match on."""
    properties = getattr(npc, "properties", None)
    tags: List[str] = []
    if isinstance(properties, dict):
        raw = properties.get("loot_tags") or []
        if isinstance(raw, (list, tuple)):
            tags = [str(t) for t in raw]
    return {
        "npc_tags": tags,
        "faction": str(getattr(npc, "faction", "") or ""),
        "level": int(getattr(npc, "level", 0) or 0),
        "region_id": str(getattr(npc, "current_region_id", "") or ""),
    }


class AdvancementManager:
    """Records first-time activity and pays authored XP for it."""

    def __init__(self, world):
        self.world = world
        self.content_root = getattr(world, "content_root", None)
        self.grants: List[GrantRule] = []
        self.curve_base = DEFAULT_CURVE_BASE
        self.curve_multiplier = DEFAULT_CURVE_MULTIPLIER
        self.issues: List[str] = []
        self._load()

    # -- loading ---------------------------------------------------------

    def _config(self) -> Dict[str, Any]:
        ruleset_getter = getattr(self.world, "ruleset_section", None)
        section: Dict[str, Any] = {}
        if callable(ruleset_getter):
            try:
                section = ruleset_getter("advancement") or {}
            except Exception:
                section = {}
        if not isinstance(section, dict):
            section = {}

        # A content set may keep a larger table in its own file; the ruleset
        # section wins for anything it defines.
        merged: Dict[str, Any] = {}
        path = os.path.join(str(self.content_root), "advancement.json") if self.content_root else ""
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as source:
                    payload = json.load(source)
                if isinstance(payload, dict):
                    merged.update(payload)
                else:
                    self.issues.append("advancement.json must contain an object")
            except (OSError, json.JSONDecodeError) as error:
                self.issues.append("could not read advancement.json: %s" % error)
        merged.update(section)
        return merged

    def _load(self) -> None:
        config = self._config()

        curve = config.get("curve")
        if isinstance(curve, dict):
            base = curve.get("base")
            multiplier = curve.get("multiplier")
            if isinstance(base, (int, float)) and not isinstance(base, bool) and base > 0:
                self.curve_base = int(base)
            else:
                if base is not None:
                    self.issues.append("advancement.curve.base must be a positive number")
            if isinstance(multiplier, (int, float)) and not isinstance(multiplier, bool) and multiplier > 1:
                self.curve_multiplier = float(multiplier)
            else:
                if multiplier is not None:
                    self.issues.append("advancement.curve.multiplier must be greater than 1")
        elif curve is not None:
            self.issues.append("advancement.curve must be an object")

        grants = config.get("grants", [])
        if not isinstance(grants, list):
            self.issues.append("advancement.grants must be an array")
            grants = []

        for index, raw in enumerate(grants):
            label = "advancement.grants[%d]" % index
            if not isinstance(raw, dict):
                self.issues.append("%s must be an object" % label)
                continue
            rule_id = str(raw.get("id", "")).strip() or label
            xp = raw.get("xp", 0)
            if isinstance(xp, bool) or not isinstance(xp, (int, float)):
                self.issues.append("%s (%s).xp must be a number" % (label, rule_id))
                continue
            match = raw.get("match", {})
            if not isinstance(match, dict):
                self.issues.append("%s (%s).match must be an object" % (label, rule_id))
                continue

            kinds: Tuple[str, ...] = ()
            raw_kind = match.get("kind")
            if isinstance(raw_kind, str) and raw_kind.strip():
                kinds = (raw_kind.strip(),)
            elif isinstance(raw_kind, list):
                kinds = tuple(str(k).strip() for k in raw_kind if str(k).strip())
            if not kinds:
                self.issues.append("%s (%s).match.kind is required" % (label, rule_id))
                continue
            unknown_kind = False
            for kind in kinds:
                if kind not in KNOWN_ENTRY_KINDS:
                    self.issues.append(
                        "%s (%s).match.kind %r is not a known entry kind" % (label, rule_id, kind)
                    )
                    unknown_kind = True
            if unknown_kind:
                # Skip the rule entirely: a grant that could never fire would
                # otherwise sit in the table looking live and silently pay
                # nothing, which is exactly the class of authoring mistake this
                # list is meant to surface.
                continue

            self.grants.append(GrantRule(
                rule_id=rule_id,
                xp=int(xp),
                message=str(raw.get("message", "") or ""),
                kinds=kinds,
                region_id=str(match.get("region_id", "") or ""),
                npc_tags=tuple(str(t) for t in (match.get("npc_tags") or [])),
                item_type=str(match.get("item_type", "") or ""),
                item_tags=tuple(str(t) for t in (match.get("item_tags") or [])),
                entry_ids=tuple(str(i) for i in (match.get("entry_ids") or [])),
                once_per_kind=bool(match.get("once_per_kind", False)),
                raw=raw,
            ))

    # -- curve -----------------------------------------------------------

    def xp_to_reach_level(self, level: int) -> int:
        """Cumulative XP needed to be `level`. Level 1 costs nothing."""
        level = max(1, int(level))
        total = 0.0
        step = float(self.curve_base)
        for _ in range(1, level):
            total += step
            step *= self.curve_multiplier
        return int(total)

    def xp_for_next_level(self, level: int) -> int:
        """XP required to advance from `level` to `level + 1`."""
        level = max(1, int(level))
        return int(self.curve_base * (self.curve_multiplier ** (level - 1)))

    # -- ledger ----------------------------------------------------------

    def ledger(self, player) -> Set[str]:
        """The player's recorded entries, created on first use."""
        existing = getattr(player, "advancement_entries", None)
        if isinstance(existing, set):
            return existing
        if isinstance(existing, (list, tuple)):
            converted = set(str(e) for e in existing)
            player.advancement_entries = converted
            return converted
        player.advancement_entries = set()
        return player.advancement_entries

    def has_entry(self, player, key: str) -> bool:
        return key in self.ledger(player)

    def seed(self, player, kind: str, identifier: str) -> bool:
        """Record an entry without paying for it. Returns True if it was new.

        For things a character *starts with* rather than achieves. The starting
        town is the case that matters: a new character has been there by
        definition, so it belongs in the journal and must never later pay out as
        a discovery -- but "you exist where you spawned" is not an achievement,
        and paying 90 XP for it handed every character most of their first level
        before they had done anything at all.
        """
        if player is None or not identifier:
            return False
        ledger = self.ledger(player)
        key = entry_key(kind, str(identifier))
        if key in ledger:
            return False
        ledger.add(key)
        return True

    def count(self, player) -> int:
        return len(self.ledger(player))

    def ingest_legacy_discoveries(self, player) -> int:
        """Fold pre-existing `player.discoveries` into the ledger.

        Discoveries were a separate record before this ledger existed. They are
        imported once, on load, so a player who had found things does not lose
        that history -- and so the `discovery` condition kind keeps working.
        """
        discoveries = getattr(player, "discoveries", None)
        if not isinstance(discoveries, dict) or not discoveries:
            return 0
        ledger = self.ledger(player)
        added = 0
        for discovery_id in discoveries:
            key = entry_key(KIND_DISCOVERY, str(discovery_id))
            if key not in ledger:
                ledger.add(key)
                added += 1
        return added

    def record(
        self,
        player,
        kind: str,
        identifier: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        announce: bool = True,
    ) -> AwardResult:
        """Record one activity. Grants XP only the first time.

        Returns an `AwardResult`; `feedback()` renders the player-facing lines.
        """
        result = AwardResult()
        if player is None or not identifier:
            return result

        key = entry_key(kind, str(identifier))
        ledger = self.ledger(player)
        if key in ledger:
            return result

        ledger.add(key)
        result.recorded = True

        payload = dict(payload or {})
        total_xp = 0
        for rule in self.grants:
            if not rule.matches(kind, str(identifier), payload):
                continue
            if rule.once_per_kind:
                marker = entry_key("%s_rule" % KIND_REGION, rule.rule_id)
                if marker in ledger:
                    continue
                ledger.add(marker)
            total_xp += rule.xp
            if announce and rule.message:
                result.messages.append(rule.message)

        if total_xp > 0:
            result.xp = total_xp
            self._grant_player_xp(player, result)

        return result

    def _grant_player_xp(self, player, result: AwardResult) -> None:
        progression = getattr(getattr(player, "runtime_state", None), "progression", None)
        if progression is None or not hasattr(player, "gain_experience"):
            return
        leveled, message = player.gain_experience(result.xp)
        result.leveled_up = bool(leveled)
        result.level_up_message = message or ""

    # -- reporting -------------------------------------------------------

    def status(self, player) -> str:
        ledger = self.ledger(player)
        if not ledger:
            return (
                "Your field journal is empty. Travel, gather, craft, and meet "
                "people -- the journal fills as you go."
            )
        by_kind: Dict[str, List[str]] = {}
        for key in sorted(ledger):
            kind, _, identifier = key.partition(":")
            if kind.endswith("_rule"):
                continue
            by_kind.setdefault(kind, []).append(identifier.replace("_", " "))

        lines = ["FIELD JOURNAL", "-" * 20]
        for kind in sorted(by_kind):
            entries = by_kind[kind]
            lines.append("%s (%d): %s" % (kind.capitalize(), len(entries), ", ".join(entries[:8])))
        lines.append("")
        lines.append("Recorded: %d" % sum(len(v) for v in by_kind.values()))
        return "\n".join(lines)
