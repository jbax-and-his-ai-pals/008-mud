"""Earned titles: identity a player takes on rather than picks at creation.

Replaces the class system. A background decides where you *begin*; a title is
what you have *become*, earned by meeting authored conditions and then applied
by the player if they want it.

Titles are:
  * **gated** -- authored conditions, evaluated by `engine/conditions.py`;
  * **self-applied** -- earning one entitles you to it, nothing is forced;
  * **mechanically inert** -- a title grants no stats, no spells, no access.
    It is identity and social signal, which is exactly what a class was doing
    badly;
  * **revocable** -- if the conditions stop holding (a falling-out with a
    guild), you lose the right to wear the name.

A guild-like construct confers titles. It is just a named group with entry
conditions and the titles it can grant; content decides whether that group is
called a guild, an order, a college, a crew, or a lodge.

Content shape (`data/titles.json`):

    {
      "cleric": {
        "name": "Cleric",
        "description": "Sworn to a healing order.",
        "conferred_by": {"name": "The Order of the Dawn", "guild_id": "order_of_dawn"},
        "condition": {"kind": "skill_at_least", "skill": "ministry", "value": 3},
        "requirements": [
          {"kind": "spell_known", "spell_id": "minor_heal"},
          {"kind": "relationship_at_least", "npc_id": "healer", "value": 20}
        ]
      }
    }

`condition` and `requirements` are combined as `all`, so an author can use
whichever reads more naturally.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from engine.conditions import Evaluation, evaluate
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE

DEFAULT_TITLES_FILE = "titles.json"


@dataclass
class Title:
    title_id: str
    name: str
    description: str = ""
    guild_name: str = ""
    guild_id: str = ""
    guild_place: str = ""
    condition: Any = None
    requirements: List[Any] = field(default_factory=list)

    def full_condition(self) -> Any:
        clauses = [c for c in ([self.condition] if self.condition else []) + list(self.requirements) if c]
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"all": clauses}


class TitleManager:
    def __init__(self, world):
        self.world = world
        self.content_root = getattr(world, "content_root", None)
        self.titles: Dict[str, Title] = {}
        self.issues: List[str] = []
        self._load()

    def _load(self) -> None:
        if not self.content_root:
            return
        path = os.path.join(str(self.content_root), DEFAULT_TITLES_FILE)
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as source:
                payload = json.load(source)
        except (OSError, json.JSONDecodeError) as error:
            self.issues.append("could not read %s: %s" % (DEFAULT_TITLES_FILE, error))
            return
        if not isinstance(payload, dict):
            self.issues.append("%s must contain an object" % DEFAULT_TITLES_FILE)
            return

        guilds = payload.get("_guilds", {})
        if not isinstance(guilds, dict):
            self.issues.append("_guilds must be an object")
            guilds = {}

        for title_id, raw in payload.items():
            if str(title_id).startswith("_"):
                continue
            if not isinstance(raw, dict):
                self.issues.append("title '%s' must be an object" % title_id)
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                self.issues.append("title '%s' requires a name" % title_id)
                continue
            conferred = raw.get("conferred_by")
            guild_name = guild_id = ""
            if isinstance(conferred, str):
                guild_name = conferred
            elif isinstance(conferred, dict):
                guild_name = str(conferred.get("name", "") or "")
                guild_id = str(conferred.get("guild_id", "") or "")
            guild_place = ""
            guild = guilds.get(guild_id)
            if isinstance(guild, dict):
                guild_place = str(guild.get("place", "") or "")
            requirements = raw.get("requirements", [])
            if not isinstance(requirements, list):
                self.issues.append("title '%s'.requirements must be an array" % title_id)
                requirements = []
            self.titles[str(title_id)] = Title(
                title_id=str(title_id),
                name=name,
                description=str(raw.get("description", "") or ""),
                guild_name=guild_name,
                guild_id=guild_id,
                guild_place=guild_place,
                condition=raw.get("condition"),
                requirements=[r for r in requirements if r],
            )

    # -- evaluation ------------------------------------------------------

    def evaluate(self, title_id: str, player) -> Evaluation:
        title = self.titles.get(title_id)
        if title is None:
            return Evaluation(False, ["unknown title %r" % title_id])
        return evaluate(title.full_condition(), player)

    def has_earned(self, title_id: str, player) -> bool:
        return self.evaluate(title_id, player).satisfied

    def earned(self, player) -> List[Title]:
        return [t for t in self._ordered() if self.has_earned(t.title_id, player)]

    def _ordered(self) -> List[Title]:
        return [self.titles[k] for k in sorted(self.titles, key=lambda k: self.titles[k].name)]

    # -- player state ----------------------------------------------------

    def sync(self, player) -> List[str]:
        """Recompute which titles the player is entitled to.

        Returns the ids newly earned. Also **revokes**: a title whose
        conditions have stopped holding is removed from the entitled set and
        from the worn title, because a falling-out with a guild should cost you
        the name.
        """
        if player is None:
            return []
        earned = getattr(player, "earned_titles", None)
        if not isinstance(earned, set):
            earned = set(str(t) for t in (earned or []))
            player.earned_titles = earned

        newly: List[str] = []
        for title_id in list(self.titles):
            if self.has_earned(title_id, player):
                if title_id not in earned:
                    earned.add(title_id)
                    newly.append(title_id)
            elif title_id in earned:
                earned.discard(title_id)
                if getattr(player, "active_title", "") == title_id:
                    player.active_title = ""
        return newly

    # -- reporting -------------------------------------------------------

    def display_name(self, player) -> str:
        """The title a player is wearing, or empty."""
        active = str(getattr(player, "active_title", "") or "")
        title = self.titles.get(active)
        return title.name if title else ""

    def status(self, player) -> str:
        earned = set(getattr(player, "earned_titles", None) or [])
        active = str(getattr(player, "active_title", "") or "")

        if not self.titles:
            return "This world does not keep titles."

        lines = [FORMAT_TITLE + "TITLES" + FORMAT_RESET, "-" * 20]
        if active and active in self.titles:
            lines.append("You are known as: %s%s%s" % (FORMAT_HIGHLIGHT, self.titles[active].name, FORMAT_RESET))
            lines.append("")

        if earned:
            lines.append("Earned:")
            for title in self._ordered():
                if title.title_id in earned:
                    marker = " (worn)" if title.title_id == active else ""
                    source = " — %s" % title.guild_name if title.guild_name else ""
                    place = " at %s" % title.guild_place.replace(":", ", ") if title.guild_place else ""
                    lines.append("  %s%s%s%s%s%s" % (FORMAT_HIGHLIGHT, title.name, FORMAT_RESET, marker, source, place))
            lines.append("")

        unearned = [t for t in self._ordered() if t.title_id not in earned]
        if unearned:
            # In player mode a title the player has not earned is simply not
            # offered yet -- the same rule the quest board follows. Numeric
            # thresholds and the raw reason are test-mode detail.
            from engine.presentation import is_player_mode
            player_world = getattr(player, "world", None) or self.world
            if is_player_mode({"world": player_world, "player": player}):
                lines.append("Not yet yours: %s" % ", ".join(t.name for t in unearned))
            else:
                lines.append("Within reach:")
                for title in unearned:
                    result = self.evaluate(title.title_id, player)
                    reason = result.reasons[0] if result.reasons else "requirements not met"
                    source = " (%s)" % title.guild_name if title.guild_name else ""
                    lines.append("  %s%s: %s" % (title.name, source, reason))

        if len(lines) <= 2:
            return "No titles are available to you yet."
        lines.append("")
        lines.append("Use 'title <name>' to wear one, or 'title none' to go without.")
        return "\n".join(lines)

    def set_active(self, player, wanted: str) -> str:
        """Wear a title the player has earned, or clear it."""
        if player is None:
            return FORMAT_ERROR + "No character." + FORMAT_RESET

        if not wanted or wanted.strip().lower() in {"none", "off", "clear", "nothing"}:
            player.active_title = ""
            return "You go without a title."

        self.sync(player)
        earned = set(getattr(player, "earned_titles", None) or [])

        # Resolve by id or display name, using the shared resolver's rules.
        from engine.naming import resolve_best
        candidates = [self.titles[t] for t in sorted(self.titles)]
        chosen: Optional[Title] = None
        key = wanted.strip().lower()
        for title in candidates:
            if title.title_id.lower() == key or title.name.lower() == key:
                chosen = title
                break
        if chosen is None:
            chosen = resolve_best(wanted, candidates, name_of=lambda t: t.name, id_of=lambda t: t.title_id)

        if chosen is None:
            return "%sYou have not heard of a title like '%s'.%s" % (FORMAT_ERROR, wanted, FORMAT_RESET)
        if chosen.title_id not in earned:
            result = self.evaluate(chosen.title_id, player)
            reason = result.reasons[0] if result.reasons else "you have not earned it"
            return "%sYou cannot claim '%s' yet: %s.%s" % (FORMAT_ERROR, chosen.name, reason, FORMAT_RESET)

        player.active_title = chosen.title_id
        return "You are now known as %s%s%s." % (FORMAT_HIGHLIGHT, chosen.name, FORMAT_RESET)
