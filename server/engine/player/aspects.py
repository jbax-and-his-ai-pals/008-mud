"""Capability-scoped Player state boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MagicState:
    """The ability pool and what a player has learned to do with it.

    Named for mana because that is the first content set's word for the pool and
    the name its saves use. Which resource the pool *is*, what it is called, and
    which stat drives it are content decisions now
    (`engine/contracts/resources.py`); this object is the storage.
    """

    mana: int = 0
    max_mana: int = 0
    regen_rate: float = 0.0
    known_spells: set[str] = field(default_factory=set)
    cooldowns: dict[str, float] = field(default_factory=dict)
    summons: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class CombatState:
    attack_power: int = 0
    defense: int = 0
    in_combat: bool = False
    target: Any = None
    targets: set[Any] = field(default_factory=set)


@dataclass
class ProgressionState:
    player_class: str = ""
    level: int = 0
    experience: int = 0
    experience_to_level: int = 0
    skills: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class QuestState:
    active: dict[str, Any] = field(default_factory=dict)
    completed: dict[str, Any] = field(default_factory=dict)
    archived: dict[str, Any] = field(default_factory=dict)
    # Board-task availability is deliberately per player: a notice that has
    # just been completed should not immediately return for that same person,
    # while it can remain useful to somebody else in a shared world.  Values
    # are clock timestamps keyed by authored quest template id.
    repeatable_available_at: dict[str, float] = field(default_factory=dict)
    active_campaigns: dict[str, Any] = field(default_factory=dict)
    completed_campaigns: dict[str, Any] = field(default_factory=dict)
    finite_adventure: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkState:
    """Timed jobs this player has started and not yet collected.

    A job is the four fields `engine/contracts/work.py` reads and nothing else.
    They are *absolute* numbers, which is what makes a save exact: the job a
    player left running finishes on the world clock whether or not they were
    logged in, and a restart does not reset it. A "seconds remaining" would not
    survive either.
    """

    jobs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PlayerRuntimeState:
    """Canonical composed state for optional game systems."""
    magic: MagicState | None = field(default_factory=MagicState)
    combat: CombatState | None = field(default_factory=CombatState)
    progression: ProgressionState | None = field(default_factory=ProgressionState)
    quests: QuestState | None = field(default_factory=QuestState)
    work: WorkState | None = field(default_factory=WorkState)
    gold: int | None = 0


@dataclass(frozen=True)
class PlayerGameAspects:
    """The enabled optional Player aspects for one loaded game contract."""

    abilities: bool = True
    combat: bool = True
    progression: bool = True
    economy: bool = True
    quests: bool = True
    # Work that takes time is presented with the crafting system, which is the
    # capability that owns stations and materials today. A set that wants timed
    # work *without* crafting wants its own capability, and that is a manifest
    # change rather than something to guess at here.
    work: bool = True

    @classmethod
    def from_world(cls, world: Any) -> "PlayerGameAspects":
        return cls(
            # Using abilities is its own capability. `magic` is a content set
            # saying its abilities are spells -- a flavour, not a mechanism --
            # and every set that declares it has abilities, so it implies them.
            # A set that declares `abilities` alone gets the pool, the cooldowns
            # and the ability commands without inheriting a spell school.
            abilities=world.has_capability("abilities") or world.has_capability("magic"),
            combat=world.has_capability("combat"),
            progression=world.ruleset_system_enabled("progression"),
            economy=world.ruleset_system_enabled("economy"),
            quests=world.has_capability("quests"),
            work=world.has_capability("crafting"),
        )

    def normalize(self, player: Any) -> None:
        if not self.abilities:
            player.runtime_state.magic = None
            player.max_total_summons = 0
        if not self.combat:
            player.runtime_state.combat = None
        if not self.progression:
            player.runtime_state.progression = None
        if not self.economy:
            player.runtime_state.gold = None
        if not self.quests:
            player.runtime_state.quests = None
        if not self.work:
            player.runtime_state.work = None
