"""Backgrounds: where a character begins, not what they may become.

Replaces the class system. The old `data/player/classes.json` described
Warrior/Rogue/Mage/Cleric -- mutually exclusive identities chosen once, with
different spells and gear and no way across. That is the wrong shape for a game
whose whole hook is that you advance by whatever you actually do.

A background is deliberately light:
  * a starting stat spread (small, so it flavours rather than decides),
  * a starting kit,
  * zero or more starting skills and recipes,
  * optionally a little coin.

It grants no exclusive content and no locked spell list. Identity that is
*earned* is a title (`engine/core/titles.py`); identity that is *chosen* is
this, and it is only a starting point.

Content shape (`data/player/backgrounds.json`):

    {
      "wanderer": {
        "name": "Wanderer",
        "description": "...",
        "stats": {"strength": 11, ...},
        "equipment": {"body": "item_leather_tunic"},
        "inventory": [{"item_id": "item_starter_dagger", "quantity": 1}],
        "spells": ["magic_missile"],
        "skills": {"crafting": 1},
        "recipes": ["tie_wildflower_posy"],
        "starting_gold": 0
      }
    }

Convention for the shipped content set: **weapons start in the pack, armour is
worn.** A new player's first `inventory` should show the weapon they own, and
drawing it is the first thing the game teaches; a kit that arrives pre-armed
hides the weapon from `inventory` and skips that lesson.

Keys beginning with `_` are treated as comments, matching the convention
already used for `discoveries.json` and `collections.json`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_BACKGROUNDS_FILE = os.path.join("player", "backgrounds.json")
# Used when a content set ships no backgrounds at all, so character creation
# still works in a minimal package.
FALLBACK_BACKGROUND_ID = "adventurer"


@dataclass
class Background:
    background_id: str
    name: str
    description: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    equipment: Dict[str, str] = field(default_factory=dict)
    inventory: List[Dict[str, Any]] = field(default_factory=list)
    spells: List[str] = field(default_factory=list)
    skills: Dict[str, int] = field(default_factory=dict)
    recipes: List[str] = field(default_factory=list)
    starting_gold: int = 0


def _learn_without_paying(player, method_name: str, identifier: str):
    """Grant a starting-kit recipe or spell without paying advancement XP.

    The kit is where a character begins, so its entries are seeded rather than
    awarded -- recorded in the field journal, worth nothing. Paying them made a
    fresh character start at level 1 with 50 XP banked from two recipes nobody
    had taught them.

    Falls back to the plain call for players whose methods predate the `award`
    parameter (test doubles, mostly).
    """
    method = getattr(player, method_name, None)
    if not callable(method):
        return False, "unsupported"
    try:
        return method(identifier, award=False)
    except TypeError:
        return method(identifier)


class BackgroundManager:
    def __init__(self, world):
        self.world = world
        self.content_root = getattr(world, "content_root", None)
        self.backgrounds: Dict[str, Background] = {}
        self.issues: List[str] = []
        self.default_id: str = ""
        self._load()

    def _load(self) -> None:
        if not self.content_root:
            return
        path = os.path.join(str(self.content_root), DEFAULT_BACKGROUNDS_FILE)
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as source:
                payload = json.load(source)
        except (OSError, json.JSONDecodeError) as error:
            self.issues.append("could not read backgrounds.json: %s" % error)
            return
        if not isinstance(payload, dict):
            self.issues.append("backgrounds.json must contain an object")
            return

        declared_default = ""
        for background_id, raw in payload.items():
            key = str(background_id)
            if key.startswith("_"):
                # `_default` names the one used when nothing is chosen.
                if key == "_default" and isinstance(raw, str):
                    declared_default = raw.strip()
                continue
            if not isinstance(raw, dict):
                self.issues.append("background '%s' must be an object" % key)
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                self.issues.append("background '%s' requires a name" % key)
                continue

            stats = raw.get("stats", {})
            if not isinstance(stats, dict):
                self.issues.append("background '%s'.stats must be an object" % key)
                stats = {}
            equipment = raw.get("equipment", {})
            if not isinstance(equipment, dict):
                self.issues.append("background '%s'.equipment must be an object" % key)
                equipment = {}
            inventory = raw.get("inventory", [])
            if not isinstance(inventory, list):
                self.issues.append("background '%s'.inventory must be an array" % key)
                inventory = []
            spells = raw.get("spells", [])
            if not isinstance(spells, list):
                self.issues.append("background '%s'.spells must be an array" % key)
                spells = []
            skills = raw.get("skills", {})
            if not isinstance(skills, dict):
                self.issues.append("background '%s'.skills must be an object" % key)
                skills = {}
            recipes = raw.get("recipes", [])
            if not isinstance(recipes, list):
                self.issues.append("background '%s'.recipes must be an array" % key)
                recipes = []

            gold = raw.get("starting_gold", 0)
            if isinstance(gold, bool) or not isinstance(gold, (int, float)) or gold < 0:
                self.issues.append("background '%s'.starting_gold must be a non-negative number" % key)
                gold = 0

            self.backgrounds[key] = Background(
                background_id=key,
                name=name,
                description=str(raw.get("description", "") or ""),
                stats=dict(stats),
                equipment={str(k): str(v) for k, v in equipment.items()},
                inventory=[e for e in inventory if isinstance(e, dict)],
                spells=[str(s) for s in spells],
                skills={str(k): int(v) for k, v in skills.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
                recipes=[str(r) for r in recipes],
                starting_gold=int(gold),
            )

        if declared_default and declared_default in self.backgrounds:
            self.default_id = declared_default
        elif self.backgrounds:
            # Deterministic: alphabetical first, so two runs agree.
            self.default_id = sorted(self.backgrounds)[0]

    # -- lookup ----------------------------------------------------------

    def available(self) -> List[Background]:
        return [self.backgrounds[k] for k in sorted(self.backgrounds)]

    def get(self, background_id: str) -> Optional[Background]:
        if not background_id:
            return None
        return self.backgrounds.get(str(background_id).strip().lower())

    def resolve(self, query: str) -> Optional[Background]:
        """Find a background by id or display name, the way a player types it."""
        if not query:
            return None
        exact = self.get(query)
        if exact is not None:
            return exact
        from engine.naming import resolve_best
        return resolve_best(
            query,
            self.available(),
            name_of=lambda b: b.name,
            id_of=lambda b: b.background_id,
        )

    def default_background(self) -> Background:
        chosen = self.get(self.default_id)
        if chosen is not None:
            return chosen
        return Background(
            background_id=FALLBACK_BACKGROUND_ID,
            name="Adventurer",
            description="Nothing in particular yet.",
        )

    # -- application -----------------------------------------------------

    def apply(self, player, background: Background) -> List[str]:
        """Give the player a background. Returns human-readable notes."""
        notes: List[str] = []
        if player is None or background is None:
            return notes

        player.background_id = background.background_id

        stats = getattr(player, "stats", None)
        if isinstance(stats, dict):
            for stat, value in background.stats.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    stats[str(stat)] = int(value)
            # Health and ability-pool ceilings are derived from stats, exactly as
            # the legacy class template did -- one formula, one place it is
            # applied. Which stat drives health, and which drives the pool, come
            # from the content set's `stats` and `resources` contracts.
            from engine.config import (
                PLAYER_BASE_HEALTH,
                PLAYER_CON_HEALTH_MULTIPLIER,
                PLAYER_DEFAULT_STATS,
            )
            from engine.contracts import stats as stats_contract
            from engine.contracts.resources import pool_for

            world = getattr(player, "world", None)
            health_stat = stats_contract.stat_name(world, "health")
            player.max_health = (
                PLAYER_BASE_HEALTH
                + stats_contract.stat_value(stats, health_stat, PLAYER_DEFAULT_STATS)
                * PLAYER_CON_HEALTH_MULTIPLIER
            )
            player.health = player.max_health
            magic = getattr(getattr(player, "runtime_state", None), "magic", None)
            if magic is not None:
                magic.max_mana = pool_for(world, stats)
                magic.mana = magic.max_mana

        progression = getattr(getattr(player, "runtime_state", None), "progression", None)
        if progression is not None:
            progression.player_class = background.name
            for skill, level in background.skills.items():
                existing = progression.skills.get(skill)
                if isinstance(existing, dict):
                    existing["level"] = max(int(existing.get("level", 0)), level)
                else:
                    progression.skills[skill] = {"level": level, "xp": 0}

        from engine.items.item_factory import ItemFactory
        equipment = getattr(player, "equipment", None)
        if isinstance(equipment, dict):
            for slot, item_id in background.equipment.items():
                if slot not in equipment:
                    self.issues.append(
                        "background '%s' equips unknown slot '%s'" % (background.background_id, slot)
                    )
                    continue
                item = ItemFactory.create_item_from_template(item_id, getattr(player, "world", None))
                if item is None:
                    self.issues.append(
                        "background '%s' equips missing item '%s'" % (background.background_id, item_id)
                    )
                    continue
                equipment[slot] = item

        inventory = getattr(player, "inventory", None)
        if inventory is not None:
            for entry in background.inventory:
                item_id = str(entry.get("item_id", "") or "")
                quantity = entry.get("quantity", 1)
                try:
                    quantity = max(1, int(quantity))
                except (TypeError, ValueError):
                    quantity = 1
                item = ItemFactory.create_item_from_template(item_id, getattr(player, "world", None))
                if item is None:
                    self.issues.append(
                        "background '%s' carries missing item '%s'" % (background.background_id, item_id)
                    )
                    continue
                if getattr(item, "stackable", False):
                    # One stack of `quantity`, exactly as the ruleset's starter
                    # inventory does it. add_item() merges by template id.
                    inventory.add_item(item, quantity)
                else:
                    # Separate instances: add_item(item, n) on a non-stackable
                    # would put the *same* object in n slots, so using one
                    # lockpick would quietly change the others.
                    inventory.add_item(item)
                    for _ in range(quantity - 1):
                        extra = ItemFactory.create_item_from_template(
                            item_id, getattr(player, "world", None)
                        )
                        if extra is None:
                            break
                        inventory.add_item(extra)

        for spell_id in background.spells:
            if hasattr(player, "learn_spell"):
                learned, message = _learn_without_paying(player, "learn_spell", spell_id)
                if not learned and message:
                    self.issues.append(
                        "background '%s' could not learn spell '%s': %s"
                        % (background.background_id, spell_id, message)
                    )

        for recipe_id in background.recipes:
            # learn_recipe validates against the crafting manager and refuses
            # unknown ids, so a typo in content surfaces here rather than
            # silently granting nothing.
            if hasattr(player, "learn_recipe"):
                learned, message = _learn_without_paying(player, "learn_recipe", recipe_id)
                if not learned and "already know" not in str(message):
                    self.issues.append(
                        "background '%s' could not learn recipe '%s': %s"
                        % (background.background_id, recipe_id, message)
                    )

        if background.starting_gold:
            gold = getattr(getattr(player, "runtime_state", None), "gold", None)
            if gold is not None:
                player.runtime_state.gold = int(gold) + background.starting_gold

        return notes

    # -- reporting -------------------------------------------------------

    def status(self, player) -> str:
        from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE
        chosen = self.get(getattr(player, "background_id", "") or "")
        if chosen is None:
            return "You began with nothing in particular."
        lines = [FORMAT_TITLE + "BACKGROUND" + FORMAT_RESET, "-" * 20]
        lines.append("%s%s%s" % (FORMAT_HIGHLIGHT, chosen.name, FORMAT_RESET))
        if chosen.description:
            lines.append(chosen.description)
        return "\n".join(lines)

    def _item_label(self, item_id: str, quantity=1) -> str:
        templates = getattr(self.world, "item_templates", None) or {}
        template = templates.get(item_id) if isinstance(templates, dict) else None
        name = str(template.get("name", "")).strip() if isinstance(template, dict) else ""
        name = name or item_id.removeprefix("item_").replace("_", " ")
        count = quantity if isinstance(quantity, int) and not isinstance(quantity, bool) else 1
        return "%s x%d" % (name, count) if count > 1 else name

    def listing(self) -> str:
        from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE
        if not self.backgrounds:
            return "This world does not define starting backgrounds."
        lines = [FORMAT_TITLE + "BACKGROUNDS" + FORMAT_RESET, "-" * 20]
        lines.append("Where you begin. Any background can go anywhere from here.")
        lines.append("")
        for background in self.available():
            lines.append("%s%s%s" % (FORMAT_HIGHLIGHT, background.name, FORMAT_RESET))
            if background.description:
                lines.append("  " + background.description)
            # Item names, not template ids: this is the screen a new player
            # reads to choose, and it used to list `item_padded_tunic`.
            kit = ", ".join(sorted(self._item_label(item_id) for item_id in background.equipment.values()) + [
                self._item_label(str(e.get("item_id", "")), e.get("quantity", 1)) for e in background.inventory
            ])
            if kit:
                lines.append("  Starts with: " + kit)
            if background.skills:
                lines.append("  Skills: " + ", ".join(
                    "%s %d" % (k, v) for k, v in sorted(background.skills.items())
                ))
        lines.append("")
        lines.append("Use 'char create <name> as <background>' to choose one.")
        return "\n".join(lines)
