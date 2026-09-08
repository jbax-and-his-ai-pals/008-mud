"""Deterministic long-form player journeys for headless regression testing.

This deliberately uses a small rules-based policy rather than an LLM.  A
failed run is therefore reproducible from its seed and command trace, and can
be promoted directly into a regression fixture.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import random
import re
import time
from typing import Any, Callable, Dict, Iterable, List, Protocol, Sequence


class JourneyPolicy(Protocol):
    """Chooses the next player command from authoritative runtime state."""

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        """Return one command to execute."""


class JourneyHook(Protocol):
    """Optional deterministic fault or observability hook for a journey."""

    def before_step(self, server: Any, session_id: str, index: int) -> str | None:
        """Apply a step-boundary action and return a trace label, if any."""


class JourneyOutcomeCheck(Protocol):
    """A post-journey assertion over authoritative state and the command trace.

    Invariants catch corrupted state while a run is in progress.  Outcome
    checks answer the complementary question: did this scripted player
    actually achieve the purpose of the route it was trying to play?
    """

    def evaluate(self, server: Any, session_id: str, steps: Sequence["JourneyStep"]) -> List[str]:
        """Return human-readable reasons this expected outcome was not met."""


class SessionReconnectFault:
    """Exercise authoritative disconnect/resume policy without a real socket."""

    def __init__(self, step_indices: Iterable[int]) -> None:
        self._step_indices = set(step_indices)

    def before_step(self, server: Any, session_id: str, index: int) -> str | None:
        if index not in self._step_indices:
            return None
        server.mark_session_disconnected(session_id)
        allowed, reason = server.validate_resume_session_target(session_id)
        if not allowed:
            raise RuntimeError(f"session resume fault rejected: {reason}")
        server.mark_session_connected(session_id)
        return "session_disconnect_resume"


class SimulatedCombatCadenceHook:
    """Make real-time player attack cooldowns match headless journey time."""

    def before_step(self, server: Any, session_id: str, index: int) -> str | None:
        del index
        player = server.get_player_for_session(session_id)
        if player is not None:
            player.last_attack_time = time.time() - player.get_effective_attack_cooldown()
        return None


class ExplorerPolicy:
    """A conservative explorer that alternates observation and traversal.

    It intentionally avoids combat and irreversible commands.  Those are
    added as separate policies once their explicit success criteria exist.
    """

    _OBSERVATION_COMMANDS = ("look", "nearby", "inventory", "status", "time", "weather")

    def __init__(self) -> None:
        self._visited_locations: set[tuple[str, str]] = set()
        self._talked_to: set[str] = set()
        self._turn = 0

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        self._turn += 1
        player = server.get_player_for_session(session_id)
        if player is None:
            return "look"
        room = server.world.get_current_room(player)
        if room is None:
            return "look"

        location = (str(player.current_region_id), str(player.current_room_id))
        first_visit = location not in self._visited_locations
        self._visited_locations.add(location)
        if first_visit:
            return "look"

        npcs = server.world.get_current_room_npcs(player)
        for npc in npcs:
            npc_id = str(getattr(npc, "obj_id", ""))
            if npc_id and npc_id not in self._talked_to:
                self._talked_to.add(npc_id)
                return f"talk {npc.name}"

        # Sample information regularly.  It makes the trace useful when a
        # movement or simulation failure is only visible in player feedback.
        if self._turn % 5 == 0:
            return self._OBSERVATION_COMMANDS[(self._turn // 5) % len(self._OBSERVATION_COMMANDS)]

        exits = sorted(str(direction) for direction in room.exits)
        if exits:
            return rng.choice(exits)
        return "look"


class CommandSequencePolicy:
    """Runs a prescribed command sequence, then delegates to an optional policy."""

    def __init__(self, commands: Iterable[str], fallback: JourneyPolicy | None = None) -> None:
        self._commands = [str(command).strip() for command in commands if str(command).strip()]
        self._index = 0
        self._fallback = fallback

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        if self._index < len(self._commands):
            command = self._commands[self._index]
            self._index += 1
            return command
        if self._fallback is not None:
            return self._fallback.next_command(server, session_id, rng)
        return "look"


class FantasyFrontierFirstSessionPolicy(CommandSequencePolicy):
    """Guides one player through the canonical opening and core system seams.

    It visits the authored quest board, starts a quest, crosses the town gate,
    attempts combat/healing, and reaches a real vendor.  Individual command
    outcomes remain in the trace; this policy's purpose is broad integration
    coverage rather than forcing a specific combat result.
    """

    COMMANDS = (
        "look",
        "talk Elder Thorne",
        "equip rusty dagger",
        "look board",
        "accept quest 1",
        "north",
        "north",
        "north",
        "nearby",
        "attack giant rat",
        "cast minor heal",
        "inventory",
        "south",
        "south",
        "south",
        "east",
        "east",
        "nearby",
        "trade talia",
        "inventory",
        "west",
        "west",
        "status",
    )

    def __init__(self) -> None:
        super().__init__(self.COMMANDS, fallback=ExplorerPolicy())


class FantasyFrontierSystemSweepPolicy(CommandSequencePolicy):
    """Exercise the authored first-session systems, including maker/social seams.

    The gathering sequence uses only player-facing content: the starter tool,
    authored resource nodes, the marketplace, no-station recipes, and NPC
    deliveries.  It deliberately avoids harness-only inventory provisioning.
    """

    COMMANDS = (
        "look",
        "look board",
        "accept quest 1",
        "recipes all",
        "west",
        "south",
        "gather herb bed",
        "gather herb bed",
        "craft tie_wildflower_posy",
        "north",
        "east",
        "give wildflower posy to Elder Thorne",
        "relationship Elder Thorne",
        "look board",
        "accept quest 1",
        "east",
        "east",
        "trade Talia",
        "orders",
        "buy hand axe",
        "east",
        "east",
        "east",
        "northwest",
        "west",
        "gather fallen bough",
        "gather fallen bough",
        "craft carve_riverside_charm",
        "east",
        "southeast",
        "west",
        "west",
        "west",
        "west",
        "west",
        "give carved riverside charm to Elder Thorne",
        "relationship Elder Thorne",
        "inventory",
    )

    def __init__(self) -> None:
        super().__init__(self.COMMANDS, fallback=ExplorerPolicy())


class FantasyFrontierFirstHourPolicy(FantasyFrontierSystemSweepPolicy):
    """A satisfying, deterministic first-hour route through the sample content.

    The route begins with an inexpensive gathered commission, turns its reward
    into a tool purchase, then uses that tool for a second crafted delivery.
    It is intentionally content-owned: the generic journey runner only knows
    how to evaluate outcomes supplied by a caller.
    """


class FantasyFrontierCombatRoutePolicy:
    """Resolve the content-authored low-risk forest-edge encounter and return."""

    _APPROACH = ("equip rusty dagger", "north", "north", "north", "nearby")

    def __init__(self) -> None:
        self._approach_index = 0
        self._returned = False
        self._fallback = ExplorerPolicy()

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        if self._approach_index < len(self._APPROACH):
            command = self._APPROACH[self._approach_index]
            self._approach_index += 1
            return command
        player = server.get_player_for_session(session_id)
        if player is None:
            return "look"
        location = (str(player.current_region_id), str(player.current_room_id))
        target = server.world.get_npc("forest_edge_lone_giant_rat")
        if location == ("forest", "forest_edge") and target is not None and target.is_alive:
            return "attack lone giant rat"
        if location in {("forest", "forest_edge"), ("town", "north_gate"), ("town", "north_gate_road")}:
            return "south"
        if location == ("town", "town_square") and not self._returned:
            self._returned = True
            return "status"
        return self._fallback.next_command(server, session_id, rng)


class FantasyFrontierPremiumMaterialPolicy:
    """Complete Riverside's trust-gated fine-material crafting loop.

    Unlike the older scripted routes, board positions are resolved from the
    live board immediately before accepting a commission.  Procedural notices
    can therefore come and go without turning this policy into a brittle
    numbered script, while the fantasy identifiers stay entirely in this
    content-side test policy rather than in the runner's generic machinery.
    """

    _WILDFLOWER_TEMPLATE = "quest_wildflower_commission"
    _PREMIUM_TEMPLATE = "quest_river_fine_token_commission"
    _COMMANDS = (
        "look board",
        "__accept_wildflower__",
        "west",
        "south",
        "gather herb bed",
        "gather herb bed",
        "craft tie_wildflower_posy",
        "north",
        "east",
        "give wildflower posy to Elder Thorne",
        "relationship Elder Thorne",
        "look board",
        "__accept_premium__",
        "north",
        "north",
        "north",
        "north",
        "north",
        "east",
        "down",
        "survey",
        "gather river clay bank",
        "gather river clay bank",
        "gather river clay bank",
        "gather river clay bank",
        "craft press_river_token",
        "craft press_river_token",
        "up",
        "west",
        "south",
        "south",
        "south",
        "south",
        "south",
        "east",
        "east",
        "trade Talia",
        "orders",
        "fulfill river_fine_token",
        "west",
        "west",
        "give river-clay token to Elder Thorne",
        "relationship Elder Thorne",
        "inventory",
    )

    def __init__(self) -> None:
        self._index = 0
        self._fallback = ExplorerPolicy()

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        if self._index >= len(self._COMMANDS):
            return self._fallback.next_command(server, session_id, rng)
        command = self._COMMANDS[self._index]
        self._index += 1
        if command == "__accept_wildflower__":
            return self._accept_board_template(server, self._WILDFLOWER_TEMPLATE)
        if command == "__accept_premium__":
            return self._accept_board_template(server, self._PREMIUM_TEMPLATE)
        return command

    @staticmethod
    def _accept_board_template(server: Any, template_id: str) -> str:
        for index, notice in enumerate(server.world.quest_board):
            if str(notice.get("template_id", "")) == template_id:
                return f"accept quest {index + 1}"
        # Keep the trace player-readable if authored availability regresses;
        # the corresponding outcome check will report the missing completion.
        return "look board"


class FantasyFrontierOpportunityPolicy(FantasyFrontierPremiumMaterialPolicy):
    """Choose successive social, economy, and crafting opportunities by state.

    The policy starts with the proven premium-material route.  It then spends
    its earned currency on a capability, seeks a new material, uses an
    authored preference to earn the required relationship access, and turns
    the remaining material into the commission's preferred resolution.  The
    decision markers inspect authoritative player/world state rather than
    relying on fixed board positions or inventory slot ordering.
    """

    _MUSEUM_TEMPLATE = "quest_museum_showcase_commission"
    _OPPORTUNITY_COMMANDS = (
        "east",
        "east",
        "trade Talia",
        "__choose_prospecting_tool__",
        "east",
        "east",
        "east",
        "north",
        "survey",
        "gather rose quartz seam",
        "gather rose quartz seam",
        "appraise rose quartz",
        "south",
        "west",
        "west",
        "west",
        "west",
        "west",
        "southeast",
        "in",
        "__choose_curator_gift__",
        "out",
        "northwest",
        "look board",
        "__accept_museum__",
        "southeast",
        "in",
        "__choose_museum_resolution__",
        "give faceted rose quartz to Curator Vane",
        "relationships",
    )

    def __init__(self) -> None:
        super().__init__()
        self._opportunity_index = 0

    def next_command(self, server: Any, session_id: str, rng: random.Random) -> str:
        if self._index < len(FantasyFrontierPremiumMaterialPolicy._COMMANDS):
            return super().next_command(server, session_id, rng)
        if self._opportunity_index >= len(self._OPPORTUNITY_COMMANDS):
            return self._fallback.next_command(server, session_id, rng)
        command = self._OPPORTUNITY_COMMANDS[self._opportunity_index]
        self._opportunity_index += 1
        player = server.get_player_for_session(session_id)
        if command == "__choose_prospecting_tool__":
            if player is not None and any(
                slot.item is not None and slot.item.get_property("tool_type") == "pickaxe"
                for slot in player.inventory.slots
            ):
                return "orders"
            return "buy prospector's pick"
        if command == "__choose_curator_gift__":
            if player is not None and player.inventory.find_item_by_id("item_rose_quartz") is not None:
                return "give rose quartz to Curator Vane"
            return "relationship Curator Vane"
        if command == "__accept_museum__":
            return self._accept_board_template(server, self._MUSEUM_TEMPLATE)
        if command == "__choose_museum_resolution__":
            if player is not None and self._has_active_template(player, self._MUSEUM_TEMPLATE):
                return "craft facet_rose_quartz"
            return "appraise rose quartz"
        return command

    @staticmethod
    def _has_active_template(player: Any, template_id: str) -> bool:
        active = getattr(getattr(player.runtime_state, "quests", None), "active", {})
        return any(str(quest.get("template_id", "")) == template_id for quest in active.values())


def fantasy_frontier_first_hour_outcome_checks() -> List[JourneyOutcomeCheck]:
    """Return content-level outcomes for the authored Riverside first-hour route.

    Keeping this alongside the content-specific policy lets the runner itself
    remain reusable by other settings: it only executes injected, generic
    checks, while this function chooses fantasy quest and item identifiers.
    """

    def completed_commissions(player: Any) -> bool:
        completed = getattr(getattr(player.runtime_state, "quests", None), "completed", {})
        completed_templates = {str(quest_id).rsplit("_", 1)[0] for quest_id in completed}
        return {"quest_wildflower_commission", "quest_riverside_charm_commission"}.issubset(completed_templates)

    def owns_hand_axe(player: Any) -> bool:
        return any(
            getattr(slot.item, "obj_id", "") == "item_hand_axe"
            for slot in player.inventory.slots
            if slot.item is not None
        )

    def earned_elder_trust(player: Any) -> bool:
        return max((int(value) for value in player.npc_relationships.values()), default=0) >= 10

    return [
        RequiredCommandsOutcome(
            (
                "gather herb bed",
                "craft tie_wildflower_posy",
                "give wildflower posy to Elder Thorne",
                "trade Talia",
                "orders",
                "buy hand axe",
                "gather fallen bough",
                "craft carve_riverside_charm",
                "give carved riverside charm to Elder Thorne",
            ),
            label="first-hour route actions",
        ),
        LocationVisitedOutcome("farmland", "orchard_west", label="maker route"),
        PlayerStateOutcome("first two commissions complete", completed_commissions),
        PlayerStateOutcome("merchant tool purchased", owns_hand_axe),
        PlayerStateOutcome("Elder Thorne trust earned", earned_elder_trust),
        TraceTextOutcome("learned the rhythm of tying", label="first craft familiarity"),
    ]


@dataclass(frozen=True)
class RequiredCommandsOutcome:
    """Require particular authored actions to have succeeded in the trace."""

    commands: Sequence[str]
    label: str = "required route actions"

    def evaluate(self, server: Any, session_id: str, steps: Sequence["JourneyStep"]) -> List[str]:
        del server, session_id
        failures: List[str] = []
        by_command = {step.command: step for step in steps}
        for command in self.commands:
            step = by_command.get(command)
            if step is None:
                failures.append(f"{self.label}: did not attempt '{command}'")
            elif step.error_messages or step.gameplay_failures:
                detail = "; ".join(step.error_messages + step.gameplay_failures)
                failures.append(f"{self.label}: '{command}' did not succeed ({detail})")
        return failures


@dataclass(frozen=True)
class LocationVisitedOutcome:
    """Require a route to reach a content-authored location at least once."""

    region_id: str
    room_id: str
    label: str = "route destination"

    def evaluate(self, server: Any, session_id: str, steps: Sequence["JourneyStep"]) -> List[str]:
        del server, session_id
        expected = (self.region_id, self.room_id)
        if any(step.location == expected for step in steps):
            return []
        return [f"{self.label}: never reached {self.region_id}/{self.room_id}"]


@dataclass(frozen=True)
class PlayerStateOutcome:
    """Adapt a focused state predicate into a named journey outcome."""

    label: str
    predicate: Callable[[Any], bool]

    def evaluate(self, server: Any, session_id: str, steps: Sequence["JourneyStep"]) -> List[str]:
        del steps
        player = server.get_player_for_session(session_id)
        if player is None:
            return [f"{self.label}: session no longer resolves to a player"]
        if self.predicate(player):
            return []
        return [f"{self.label}: expected player state was not reached"]


@dataclass(frozen=True)
class TraceTextOutcome:
    """Require a player-visible confirmation in a deterministic journey."""

    phrase: str
    label: str = "route feedback"

    def evaluate(self, server: Any, session_id: str, steps: Sequence["JourneyStep"]) -> List[str]:
        del server, session_id
        if any(self.phrase.lower() in message.lower() for step in steps for message in step.text_messages):
            return []
        return [f"{self.label}: did not report '{self.phrase}'"]


def fantasy_frontier_combat_route_outcome_checks() -> List[JourneyOutcomeCheck]:
    """Content-level outcomes for the sample's introductory combat route."""

    def survived_with_experience(player: Any) -> bool:
        progression = getattr(player.runtime_state, "progression", None)
        return bool(player.is_alive and progression is not None and progression.experience > 0)

    return [
        RequiredCommandsOutcome(("equip rusty dagger", "attack lone giant rat"), label="combat route actions"),
        LocationVisitedOutcome("forest", "forest_edge", label="combat route destination"),
        TraceTextOutcome("is defeated", label="combat route resolution"),
        PlayerStateOutcome("combat route survival and reward", survived_with_experience),
    ]


def fantasy_frontier_premium_material_outcome_checks() -> List[JourneyOutcomeCheck]:
    """Content outcomes for Riverside's fine-material gathering route."""

    def completed_premium_commission(player: Any) -> bool:
        completed = getattr(getattr(player.runtime_state, "quests", None), "completed", {})
        return any(str(quest_id).rsplit("_", 1)[0] == "quest_river_fine_token_commission" for quest_id in completed)

    def completed_premium_order(player: Any) -> bool:
        completed = getattr(player, "vendor_orders_completed", {})
        return "river_fine_token" in completed.get("merchant", [])

    def retained_trust(player: Any) -> bool:
        return int(player.npc_relationships.get("village_elder", 0)) >= 12

    return [
        RequiredCommandsOutcome(
            (
                "gather river clay bank",
                "craft press_river_token",
                "trade Talia",
                "fulfill river_fine_token",
                "give river-clay token to Elder Thorne",
            ),
            label="premium material route actions",
        ),
        LocationVisitedOutcome("forest", "stream_crossing", label="premium material source"),
        TraceTextOutcome("Craft quality: River Fine.", label="premium crafting result"),
        PlayerStateOutcome("premium commission complete", completed_premium_commission),
        PlayerStateOutcome("premium merchant order complete", completed_premium_order),
        PlayerStateOutcome("Elder Thorne premium trust earned", retained_trust),
    ]


def fantasy_frontier_opportunity_route_outcome_checks() -> List[JourneyOutcomeCheck]:
    """Outcomes for the setting-specific state-driven opportunity route."""

    def completed_museum_commission(player: Any) -> bool:
        completed = getattr(getattr(player.runtime_state, "quests", None), "completed", {})
        return any(str(quest_id).rsplit("_", 1)[0] == "quest_museum_showcase_commission" for quest_id in completed)

    def owns_prospecting_tool(player: Any) -> bool:
        return any(
            slot.item is not None and slot.item.get_property("tool_type") == "pickaxe"
            for slot in player.inventory.slots
        )

    def earned_curator_access(player: Any) -> bool:
        return int(player.npc_relationships.get("curator", 0)) >= 13

    return [
        RequiredCommandsOutcome(
            (
                "buy prospector's pick",
                "gather rose quartz seam",
                "appraise rose quartz",
                "give rose quartz to Curator Vane",
                "craft facet_rose_quartz",
                "give faceted rose quartz to Curator Vane",
            ),
            label="opportunity route actions",
        ),
        LocationVisitedOutcome("foothills", "rocky_outcrop", label="prospecting opportunity"),
        LocationVisitedOutcome("town", "museum_interior", label="museum opportunity"),
        TraceTextOutcome("Material grade:", label="material appraisal"),
        PlayerStateOutcome("prospecting capability acquired", owns_prospecting_tool),
        PlayerStateOutcome("museum commission complete", completed_museum_commission),
        PlayerStateOutcome("Curator Vane access earned", earned_curator_access),
    ]


@dataclass
class JourneyStep:
    index: int
    command: str
    event_types: List[str]
    error_messages: List[str]
    location: tuple[str, str] | None
    health: int | None
    inventory_slots_used: int | None
    text_messages: List[str] = field(default_factory=list)
    gameplay_failures: List[str] = field(default_factory=list)
    faults: List[str] = field(default_factory=list)
    invariant_errors: List[str] = field(default_factory=list)


@dataclass
class JourneyReport:
    seed: int
    player_name: str
    action_interval_s: float
    requested_duration_s: float
    simulated_duration_s: float
    steps: List[JourneyStep]
    invariant_errors: List[str]
    outcome_errors: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.invariant_errors and not self.outcome_errors

    @property
    def error_event_count(self) -> int:
        return sum(len(step.error_messages) for step in self.steps)

    @property
    def gameplay_failure_count(self) -> int:
        return sum(len(step.gameplay_failures) for step in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "passed": self.passed,
            "step_count": len(self.steps),
            "error_event_count": self.error_event_count,
            "gameplay_failure_count": self.gameplay_failure_count,
        }

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class MultiJourneyReport:
    """Interleaved reports for several player-like agents in one world."""

    seed: int
    action_interval_s: float
    requested_duration_s: float
    agents: Dict[str, List[JourneyStep]]
    invariant_errors: List[str]

    @property
    def passed(self) -> bool:
        return not self.invariant_errors

    @property
    def error_event_count(self) -> int:
        return sum(len(step.error_messages) for steps in self.agents.values() for step in steps)

    @property
    def gameplay_failure_count(self) -> int:
        return sum(len(step.gameplay_failures) for steps in self.agents.values() for step in steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "passed": self.passed,
            "agent_count": len(self.agents),
            "steps_per_agent": {agent_id: len(steps) for agent_id, steps in self.agents.items()},
            "error_event_count": self.error_event_count,
            "gameplay_failure_count": self.gameplay_failure_count,
        }

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class JourneyRunner:
    """Runs and records a seeded player journey against ``HeadlessServer``."""

    def __init__(
        self,
        server: Any,
        *,
        seed: int = 1,
        player_name: str = "Journey Tester",
        action_interval_s: float = 5.0,
        policy: JourneyPolicy | None = None,
        hooks: Sequence[JourneyHook] = (),
        outcome_checks: Sequence[JourneyOutcomeCheck] = (),
    ) -> None:
        if action_interval_s <= 0:
            raise ValueError("action_interval_s must be positive")
        self.server = server
        self.seed = seed
        self.player_name = player_name
        self.action_interval_s = action_interval_s
        self.policy = policy or ExplorerPolicy()
        self.hooks = list(hooks)
        self.outcome_checks = list(outcome_checks)
        self.rng = random.Random(seed)

    def run(self, duration_s: float) -> JourneyReport:
        if duration_s <= 0:
            raise ValueError("duration_s must be positive")

        # HeadlessServer uses tick_dt for deterministic runs.  Giving one
        # action a stable simulated interval lets a 30-minute journey finish
        # quickly while preserving an explicit, replayable time budget.
        step_count = int(duration_s // self.action_interval_s)
        if step_count == 0:
            step_count = 1
        self.server.tick_dt = self.action_interval_s
        session = self.server.create_session(player_id=f"journey_{self.seed}")
        self.server.execute_command(session.session_id, f"char create {self.player_name}")
        steps: List[JourneyStep] = []
        all_invariant_errors: List[str] = []
        for index in range(step_count):
            faults = self._run_hooks(session.session_id, index)
            command = self.policy.next_command(self.server, session.session_id, self.rng)
            events = self.server.execute_command(session.session_id, command)
            invariant_errors = validate_player_state(self.server, session.session_id)
            all_invariant_errors.extend(f"step {index}: {message}" for message in invariant_errors)
            steps.append(record_journey_step(self.server, index, command, events, invariant_errors, session.session_id, faults))
            if invariant_errors:
                break
        outcome_errors = self._evaluate_outcomes(session.session_id, steps)
        return JourneyReport(
            seed=self.seed,
            player_name=self.player_name,
            action_interval_s=self.action_interval_s,
            requested_duration_s=duration_s,
            simulated_duration_s=len(steps) * self.action_interval_s,
            steps=steps,
            invariant_errors=all_invariant_errors,
            outcome_errors=outcome_errors,
        )

    def run_commands(
        self,
        commands: Sequence[str],
        *,
        requested_duration_s: float | None = None,
    ) -> JourneyReport:
        """Execute an exact command trace, used for replay and minimization."""
        self.server.tick_dt = self.action_interval_s
        session = self.server.create_session(player_id=f"journey_{self.seed}")
        self.server.execute_command(session.session_id, f"char create {self.player_name}")

        steps: List[JourneyStep] = []
        all_invariant_errors: List[str] = []

        for index, command in enumerate(commands):
            faults = self._run_hooks(session.session_id, index)
            events = self.server.execute_command(session.session_id, command)
            invariant_errors = validate_player_state(self.server, session.session_id)
            all_invariant_errors.extend(f"step {index}: {message}" for message in invariant_errors)
            steps.append(record_journey_step(self.server, index, command, events, invariant_errors, session.session_id, faults))
            if invariant_errors:
                break

        outcome_errors = self._evaluate_outcomes(session.session_id, steps)
        return JourneyReport(
            seed=self.seed,
            player_name=self.player_name,
            action_interval_s=self.action_interval_s,
            requested_duration_s=requested_duration_s if requested_duration_s is not None else len(commands) * self.action_interval_s,
            simulated_duration_s=len(steps) * self.action_interval_s,
            steps=steps,
            invariant_errors=all_invariant_errors,
            outcome_errors=outcome_errors,
        )

    def _run_hooks(self, session_id: str, index: int) -> List[str]:
        labels: List[str] = []
        for hook in self.hooks:
            label = hook.before_step(self.server, session_id, index)
            if label:
                labels.append(label)
        return labels

    def _evaluate_outcomes(self, session_id: str, steps: Sequence[JourneyStep]) -> List[str]:
        errors: List[str] = []
        for check in self.outcome_checks:
            errors.extend(check.evaluate(self.server, session_id, steps))
        return errors


def record_journey_step(
    server: Any,
    index: int,
    command: str,
    events: List[Dict[str, Any]],
    invariant_errors: List[str],
    session_id: str,
    faults: List[str],
) -> JourneyStep:
    """Capture a normalized trace row without coupling it to a runner type."""
    player = server.get_player_for_session(session_id)
    location = None
    health = None
    slots_used = None
    if player is not None:
        location = (str(player.current_region_id), str(player.current_room_id))
        health = int(player.health)
        slots_used = sum(1 for slot in player.inventory.slots if slot.item is not None)
    text_messages = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
    gameplay_failures = [message for message in text_messages if _is_gameplay_failure(message)]
    return JourneyStep(
        index=index,
        command=command,
        event_types=[str(event.get("type", "")) for event in events],
        error_messages=[str(event.get("payload", "")) for event in events if event.get("type") == "error"],
        text_messages=text_messages,
        gameplay_failures=gameplay_failures,
        location=location,
        health=health,
        inventory_slots_used=slots_used,
        faults=faults,
        invariant_errors=list(invariant_errors),
    )


_GAMEPLAY_FAILURE_PATTERN = re.compile(
    r"\b(unknown command|not found|you don't have|you need |cannot |failed|not ready|invalid |doesn't sell|don't see|unavailable)\b",
    re.IGNORECASE,
)


def _is_gameplay_failure(message: str) -> bool:
    """Conservative response classifier for player-visible unsuccessful actions."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", message)
    return bool(_GAMEPLAY_FAILURE_PATTERN.search(plain))

def validate_player_state(server: Any, session_id: str) -> List[str]:
    """Invariant checks shared by solo and multi-agent journeys."""
    player = server.get_player_for_session(session_id)
    if player is None:
        return ["session no longer resolves to a player"]

    errors: List[str] = []
    if player.health > player.max_health:
        errors.append(f"health {player.health} exceeds maximum {player.max_health}")
    if player.health < 0:
        errors.append(f"health {player.health} is negative")
    room = server.world.get_current_room(player)
    if room is None:
        errors.append("player location does not resolve to a room")
    for slot_index, slot in enumerate(player.inventory.slots):
        if slot.quantity < 0:
            errors.append(f"inventory slot {slot_index} has negative quantity")
        if slot.item is None and slot.quantity != 0:
            errors.append(f"empty inventory slot {slot_index} has quantity {slot.quantity}")
        if slot.item is not None and slot.quantity <= 0:
            errors.append(f"occupied inventory slot {slot_index} has quantity {slot.quantity}")
    return errors


class MultiJourneyRunner:
    """Runs several deterministic player policies against one shared world.

    This is intentionally an interleaved simulation, not a concurrency claim:
    it gives deterministic ordering while exercising cross-player state,
    NPC reactions, room presence, and future party/loot policies.
    """

    def __init__(
        self,
        server: Any,
        *,
        agent_count: int = 2,
        seed: int = 1,
        action_interval_s: float = 5.0,
        policy_factory: Callable[[], JourneyPolicy] = ExplorerPolicy,
        agent_policy_factories: Sequence[Callable[[], JourneyPolicy]] | None = None,
        hooks: Sequence[JourneyHook] = (),
    ) -> None:
        if agent_count < 2:
            raise ValueError("MultiJourneyRunner requires at least two agents")
        if action_interval_s <= 0:
            raise ValueError("action_interval_s must be positive")
        if agent_policy_factories is not None and len(agent_policy_factories) != agent_count:
            raise ValueError("agent_policy_factories must provide exactly one policy factory per agent")
        self.server = server
        self.agent_count = agent_count
        self.seed = seed
        self.action_interval_s = action_interval_s
        self.policy_factory = policy_factory
        self.agent_policy_factories = list(agent_policy_factories) if agent_policy_factories is not None else None
        self.hooks = list(hooks)
        self.rng = random.Random(seed)

    def run(self, duration_s: float) -> MultiJourneyReport:
        if duration_s <= 0:
            raise ValueError("duration_s must be positive")
        rounds = max(1, int(duration_s // self.action_interval_s))
        # A full round represents one action interval; divide the server tick
        # across agents so adding agents does not accelerate world time.
        self.server.tick_dt = self.action_interval_s / self.agent_count
        sessions: Dict[str, Any] = {}
        policies: Dict[str, JourneyPolicy] = {}
        traces: Dict[str, List[JourneyStep]] = {}
        invariant_errors: List[str] = []
        for index in range(self.agent_count):
            agent_id = f"agent_{index + 1}"
            session = self.server.create_session(player_id=f"multi_{self.seed}_{agent_id}")
            self.server.execute_command(session.session_id, f"char create Playtester {index + 1}")
            sessions[agent_id] = session
            factory = self.agent_policy_factories[index] if self.agent_policy_factories is not None else self.policy_factory
            policies[agent_id] = factory()
            traces[agent_id] = []

        for round_index in range(rounds):
            for agent_id, session in sessions.items():
                faults: List[str] = []
                for hook in self.hooks:
                    label = hook.before_step(self.server, session.session_id, round_index)
                    if label:
                        faults.append(label)
                command = policies[agent_id].next_command(self.server, session.session_id, self.rng)
                events = self.server.execute_command(session.session_id, command)
                errors = validate_player_state(self.server, session.session_id)
                invariant_errors.extend(f"{agent_id} step {round_index}: {error}" for error in errors)
                traces[agent_id].append(record_journey_step(self.server, round_index, command, events, errors, session.session_id, faults))
                if errors:
                    return MultiJourneyReport(self.seed, self.action_interval_s, duration_s, traces, invariant_errors)
        return MultiJourneyReport(self.seed, self.action_interval_s, duration_s, traces, invariant_errors)


def commands_from_trace(trace: JourneyReport | Dict[str, Any] | str | Path) -> List[str]:
    """Extract replay commands from an in-memory report, JSON payload, or path."""
    if isinstance(trace, JourneyReport):
        return [step.command for step in trace.steps]
    if isinstance(trace, (str, Path)):
        trace = json.loads(Path(trace).read_text(encoding="utf-8"))
    steps = trace.get("steps", []) if isinstance(trace, dict) else []
    return [str(step.get("command", "")).strip() for step in steps if isinstance(step, dict) and str(step.get("command", "")).strip()]


def minimize_failing_commands(
    commands: Sequence[str],
    still_fails: Callable[[List[str]], bool],
) -> List[str]:
    """Delta-debug a failing trace while preserving its failure predicate.

    ``still_fails`` should create a fresh server and return true only when the
    reproduced trace still shows the bug/invariant violation under test.
    """
    candidate = list(commands)
    if not candidate or not still_fails(candidate):
        raise ValueError("commands must reproduce the failure before minimization")

    granularity = 2
    while len(candidate) >= 2:
        chunk_size = max(1, (len(candidate) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(candidate), chunk_size):
            trial = candidate[:start] + candidate[start + chunk_size :]
            if trial and still_fails(trial):
                candidate = trial
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if not reduced:
            if granularity >= len(candidate):
                break
            granularity = min(len(candidate), granularity * 2)
    return candidate
