"""Capability-scoped Player state boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MagicState:
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
    active_campaigns: dict[str, Any] = field(default_factory=dict)
    completed_campaigns: dict[str, Any] = field(default_factory=dict)
    finite_adventure: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerRuntimeState:
    """Canonical composed state for optional game systems."""
    magic: MagicState | None = field(default_factory=MagicState)
    combat: CombatState | None = field(default_factory=CombatState)
    progression: ProgressionState | None = field(default_factory=ProgressionState)
    quests: QuestState | None = field(default_factory=QuestState)
    gold: int | None = 0


@dataclass(frozen=True)
class PlayerGameAspects:
    """The enabled optional Player aspects for one loaded game contract."""

    magic: bool = True
    combat: bool = True
    progression: bool = True
    economy: bool = True
    quests: bool = True

    @classmethod
    def from_world(cls, world: Any) -> "PlayerGameAspects":
        return cls(
            magic=world.has_capability("magic"),
            combat=world.has_capability("combat"),
            progression=world.ruleset_system_enabled("progression"),
            economy=world.ruleset_system_enabled("economy"),
            quests=world.has_capability("quests"),
        )

    def normalize(self, player: Any) -> None:
        if not self.magic:
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
